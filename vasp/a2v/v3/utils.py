from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import httpx


VISUAL_TYPES = {"image", "video", "gif", "sticker"}


def read_text(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8").strip()


def write_text(path: str | Path, text: str) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def write_json(path: str | Path, obj: Any) -> Path:
    return write_text(path, json.dumps(obj, ensure_ascii=False, indent=2))


def safe_name(name: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in (name or "edit"))
    while "__" in safe:
        safe = safe.replace("__", "_")
    return safe.strip("_") or "edit"


def extract_balanced_json(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    begin = -1
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                begin = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and begin >= 0:
                return text[begin : i + 1]
    return None


def extract_balanced_json_objects(text: str) -> list[str]:
    objects: list[str] = []
    depth = 0
    in_str = False
    esc = False
    begin = -1
    for i, ch in enumerate(text or ""):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                begin = i
            depth += 1
        elif ch == "}":
            if depth <= 0:
                continue
            depth -= 1
            if depth == 0 and begin >= 0:
                objects.append(text[begin : i + 1])
                begin = -1
    return objects


def parse_jsonish(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, flags=re.IGNORECASE)
    if m:
        try:
            obj = json.loads(m.group(1).strip())
            return obj if isinstance(obj, dict) else None
        except Exception:
            pass
    for candidate in extract_balanced_json_objects(raw):
        try:
            obj = json.loads(candidate)
            return obj if isinstance(obj, dict) else None
        except Exception:
            continue
    balanced = extract_balanced_json(raw)
    if balanced:
        try:
            obj = json.loads(balanced)
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None
    # Planner V3 models sometimes repeat the object and hit max tokens after
    # closing unmatched_text but before writing warnings/outer brace. Recover
    # the latest complete-enough planner payload instead of discarding matches.
    marker = '{"planner_version"'
    starts = [m.start() for m in re.finditer(re.escape(marker), raw)]
    for start in reversed(starts):
        candidate = raw[start:].strip()
        for suffix in ("", "}", ', "warnings": []}'):
            try:
                obj = json.loads(candidate + suffix)
                return obj if isinstance(obj, dict) else None
            except Exception:
                continue
    return None


def parse_jsonish_file(path: str | Path) -> dict[str, Any] | None:
    return parse_jsonish(Path(path).read_text(encoding="utf-8", errors="ignore"))


def call_llm_endpoint(endpoint: str, prompt: str, *, temperature: float = 0.0, max_tokens: int = 2400) -> str:
    resp = httpx.post(
        endpoint,
        json={"prompt": prompt, "temperature": temperature, "max_tokens": max_tokens},
        timeout=420.0,
    )
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        body = resp.text.strip()
        if "ERR_NGROK_8012" in body or "failed to establish a connection to the upstream web service" in body:
            body = (
                "ngrok tunnel is online, but the Colab Flask server is not reachable behind it. "
                "Restart/rerun the Colab serving cell and make sure its local /health check passes "
                "before running the VASP pipeline."
            )
        if len(body) > 4000:
            body = body[:4000] + "... [truncated]"
        raise httpx.HTTPStatusError(
            f"{exc}; response body: {body}",
            request=exc.request,
            response=exc.response,
        ) from exc
    payload = resp.json()
    if isinstance(payload, dict):
        return str(payload.get("response", "")).strip()
    return str(payload).strip()


def media_inputs(media_json: dict[str, Any]) -> list[dict[str, Any]]:
    return ((media_json.get("media_context") or {}).get("inputs") or [])


def media_probe(media_json: dict[str, Any]) -> dict[str, Any]:
    probe = ((media_json.get("media_context") or {}).get("probe") or {})
    return probe if isinstance(probe, dict) else {}


def media_by_id(media_json: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in media_inputs(media_json):
        if isinstance(row, dict) and row.get("id"):
            out[str(row["id"])] = row
    return out


def media_type(row: dict[str, Any]) -> str:
    return str(row.get("media_type") or row.get("type") or "").strip().lower()


def is_visual_media(row: dict[str, Any]) -> bool:
    mt = media_type(row)
    return any(t in mt for t in VISUAL_TYPES)


def is_audio_media(row: dict[str, Any]) -> bool:
    return "audio" in media_type(row) or media_type(row) in {"music", "sfx"}


def is_video_media(row: dict[str, Any]) -> bool:
    mt = media_type(row)
    return "video" in mt or mt in {"mp4", "mov", "m4v", "webm"}


def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (s or "").lower())).strip()


def extract_transcript(media_json: dict[str, Any]) -> str:
    analysis = ((media_json.get("media_context") or {}).get("analysis") or {})
    if isinstance(analysis, dict):
        for block in analysis.values():
            if not isinstance(block, dict):
                continue
            transcript = block.get("transcript")
            if isinstance(transcript, dict):
                text = transcript.get("full_text") or transcript.get("text")
                if text:
                    return str(text).strip()
    return str(((media_json.get("media_context") or {}).get("transcript") or "")).strip()


def extract_caption_groups(media_json: dict[str, Any]) -> list[dict[str, Any]]:
    analysis = ((media_json.get("media_context") or {}).get("analysis") or {})
    if isinstance(analysis, dict):
        for block in analysis.values():
            if not isinstance(block, dict):
                continue
            transcript = block.get("transcript")
            if not isinstance(transcript, dict):
                continue
            groups = transcript.get("caption_groups")
            if isinstance(groups, list):
                out: list[dict[str, Any]] = []
                for i, g in enumerate(groups):
                    if not isinstance(g, dict):
                        continue
                    try:
                        s = float(g.get("start"))
                        e = float(g.get("end"))
                    except Exception:
                        continue
                    txt = str(g.get("text", "")).strip()
                    if txt and e > s:
                        out.append({"index": int(g.get("index", i)), "start": round(s, 3), "end": round(e, 3), "text": txt})
                if out:
                    return out
    return []


def extract_word_map(media_json: dict[str, Any]) -> list[dict[str, Any]]:
    analysis = ((media_json.get("media_context") or {}).get("analysis") or {})
    if isinstance(analysis, dict):
        for block in analysis.values():
            if not isinstance(block, dict):
                continue
            transcript = block.get("transcript")
            if not isinstance(transcript, dict):
                continue
            words = transcript.get("word_timing_map") or transcript.get("words") or []
            if isinstance(words, list):
                out: list[dict[str, Any]] = []
                for w in words:
                    if not isinstance(w, dict):
                        continue
                    try:
                        s = float(w.get("start"))
                        e = float(w.get("end"))
                    except Exception:
                        continue
                    text = str(w.get("text", "")).strip()
                    if text and e >= s:
                        out.append({"text": text, "start": round(s, 3), "end": round(e, 3)})
                if out:
                    return out
    return []


def main_audio(media_json: dict[str, Any]) -> tuple[str | None, str | None, float]:
    probe = media_probe(media_json)
    for row in media_inputs(media_json):
        if isinstance(row, dict) and row.get("id") and is_audio_media(row):
            eid = str(row["id"])
            dur = 0.0
            if isinstance(probe.get(eid), dict):
                try:
                    dur = float(probe[eid].get("duration") or 0.0)
                except Exception:
                    dur = 0.0
            path = str(row.get("path") or "")
            probed = _probe_media_duration(path)
            if probed > 0:
                dur = probed
            return eid, path, round(dur, 3)
    return None, None, 0.0


def main_video(media_json: dict[str, Any]) -> tuple[str | None, str | None, float]:
    probe = media_probe(media_json)
    best: tuple[str | None, str | None, float, int, int] = (None, None, 0.0, -1, 10**9)
    markers = ("main video", "main visual", "extract speech", "extract captions", "speech captions", "caption source")
    for row in media_inputs(media_json):
        if not isinstance(row, dict) or not row.get("id") or not is_video_media(row):
            continue
        eid = str(row["id"])
        path = str(row.get("path") or "")
        text = " ".join(str(row.get(k) or "") for k in ("role", "aim", "about", "tags")).lower()
        priority = 1 if any(marker in text for marker in markers) else 0
        try:
            order = int(eid.split("_", 1)[1]) if eid.startswith("media_") else 10**6
        except Exception:
            order = 10**6
        dur = 0.0
        if isinstance(probe.get(eid), dict):
            try:
                dur = float(probe[eid].get("duration") or 0.0)
            except Exception:
                dur = 0.0
        probed = _probe_media_duration(path)
        if probed > 0:
            dur = probed
        if priority > best[3] or (priority == best[3] and order < best[4]) or (best[0] is None):
            best = (eid, path, round(dur, 3), priority, order)
    return best[0], best[1], best[2]


def _probe_media_duration(path: str | Path) -> float:
    src = Path(path)
    if not src.exists():
        return 0.0
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(src),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if result.returncode != 0:
            return 0.0
        return max(0.0, float((result.stdout or "").strip() or 0.0))
    except Exception:
        return 0.0


def json_md(title: str, obj: Any) -> str:
    return f"# {title}\n\n```json\n{json.dumps(obj, ensure_ascii=False, indent=2)}\n```\n"
