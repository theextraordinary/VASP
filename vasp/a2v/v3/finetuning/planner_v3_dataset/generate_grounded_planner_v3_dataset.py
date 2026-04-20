from __future__ import annotations

import argparse
import json
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vasp.a2v.v3.finetuning.planner_v3_dataset.validate_planner_v3_dataset import validate_jsonl, validate_planner_v3_example


ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "output"
TRANSCRIPTS_PATH = OUT_DIR / "transcripts.md"
MEDIA_PATH_CANDIDATES = [OUT_DIR / "media_skill.md", OUT_DIR / "media_files.md"]
PROMPT_DIR = ROOT.parents[1] / "v3" / "prompts"


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "how",
    "in",
    "into",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "our",
    "that",
    "the",
    "their",
    "this",
    "through",
    "to",
    "with",
}


SYNONYMS: dict[str, set[str]] = {
    "ai": {"artificial", "intelligence", "machine", "learning", "deep", "neural", "automation", "robot", "robotics"},
    "artificial": {"ai", "intelligence", "machine", "learning", "neural", "robot"},
    "robot": {"robotics", "automation", "machines", "ai", "engineering"},
    "code": {"coding", "programming", "python", "javascript", "html", "css", "backend", "software", "debugging", "terminal"},
    "programmer": {"programming", "coding", "python", "software", "debugging", "backend"},
    "cybersecurity": {"security", "passwords", "authentication", "hackers", "privacy", "digital", "threats"},
    "cloud": {"computing", "online", "services", "servers", "storage", "scalable"},
    "server": {"backend", "databases", "cloud", "requests", "processing"},
    "social": {"media", "platforms", "notifications", "audiences", "creators", "trends"},
    "internet": {"online", "websites", "connects", "global", "digital", "wifi"},
    "data": {"analytics", "graphs", "statistics", "predictions", "information", "dashboard"},
    "graph": {"graphs", "statistics", "analytics", "charts", "market", "prices"},
    "money": {"financial", "saving", "investing", "wealth", "budgeting", "coins", "market"},
    "space": {"astronauts", "telescopes", "mars", "satellites", "galaxies", "orbit", "planets", "rocket"},
    "astronaut": {"astronauts", "space", "mars", "missions", "simulator"},
    "telescope": {"telescopes", "space", "galaxies", "stars", "astronomy"},
    "satellite": {"satellites", "gps", "orbiting", "communication", "navigation"},
    "rocket": {"space", "launch", "exploration", "mars"},
    "earth": {"world", "global", "climate", "planet", "space"},
    "solar": {"sunlight", "electricity", "renewable", "energy", "panels"},
    "wind": {"turbines", "renewable", "energy", "power", "moving"},
    "electric": {"electricity", "vehicles", "energy", "charging", "battery", "current"},
    "battery": {"batteries", "energy", "charging", "electric"},
    "recycling": {"recycle", "environmental", "waste", "sustainable"},
    "climate": {"environment", "agriculture", "biodiversity", "sustainable", "renewable"},
    "brain": {"memory", "sleep", "mental", "emotional", "thinking", "neural"},
    "sleep": {"memory", "dreaming", "health", "brain"},
    "health": {"exercise", "nutrition", "water", "stress", "mental", "therapy", "medical"},
    "dna": {"genetic", "biology", "cells", "biotechnology"},
    "cell": {"cells", "biology", "organisms", "microscope"},
    "chemistry": {"chemical", "reactions", "atoms", "molecules", "experiment"},
    "atom": {"atoms", "molecules", "matter", "chemistry", "physics"},
    "physics": {"matter", "energy", "motion", "gravity", "electricity", "sound", "light"},
    "math": {"mathematics", "algebra", "geometry", "calculus", "statistics", "probability", "equations"},
    "teacher": {"teachers", "teaching", "classroom", "students", "education", "learning"},
    "student": {"students", "learning", "education", "courses", "classroom", "practice"},
    "book": {"books", "reading", "library", "learning", "knowledge"},
    "team": {"teamwork", "collaboration", "communication", "meeting", "ideas"},
    "speaker": {"speaking", "public", "audience", "communication", "stage"},
    "design": {"graphic", "typography", "interfaces", "visual", "creative"},
    "camera": {"photography", "photos", "visuals", "creator", "vlog"},
    "video": {"editing", "films", "storytelling", "creator", "captions", "pacing"},
    "gaming": {"game", "games", "competitive", "streaming", "challenge"},
    "vr": {"virtual", "reality", "immersive", "gaming"},
    "ar": {"augmented", "reality", "digital", "physical"},
    "drone": {"drones", "photography", "logistics", "flying"},
    "startup": {"entrepreneurs", "businesses", "innovation", "customers", "pitch"},
    "idea": {"creativity", "innovation", "inspiration", "question", "unexpected"},
    "motivation": {"discipline", "success", "habits", "goals", "achievement"},
    "meditation": {"stress", "emotional", "awareness", "mindfulness", "mental"},
    "sound": {"audio", "music", "waves", "hearing"},
    "wifi": {"internet", "connection", "online", "digital"},
}


REASON_BY_STYLE = {
    "literal": [
        "Direct visual match for the spoken concept.",
        "Clear object match that anchors the phrase.",
        "Specific media fits the exact topic being mentioned.",
    ],
    "contextual": [
        "Contextual support that makes the idea easier to understand.",
        "Useful background visual for the broader explanation.",
        "Supporting visual that reinforces the narration.",
    ],
    "cinematic": [
        "Cinematic beat that makes the key idea feel bigger.",
        "Strong visual moment for the main payoff phrase.",
        "Editor-style hero visual for the most important concept.",
    ],
    "emotional": [
        "Emotional visual fit for the human moment.",
        "Adds feeling to the narration without changing the meaning.",
        "Reaction-like emotional support for this phrase.",
    ],
    "humorous": [
        "Humorous visual that makes the beat more engaging.",
        "Meme-style match for the playful moment.",
        "Comic timing visual for a lighter phrase.",
    ],
    "reaction": [
        "Reaction-style visual for the surprise or emphasis.",
        "Expressive reaction beat that helps the moment land.",
        "Fast reaction visual for the emotional payoff.",
    ],
    "transition": [
        "Transition visual that connects two ideas cleanly.",
        "Bridge visual for the shift in topic.",
        "Pacing visual that helps the edit move forward.",
    ],
    "fallback": [
        "Mandatory fallback placed on the closest usable phrase.",
        "Closest available phrase for required media coverage.",
        "Low-strength fallback because no stronger exact phrase exists.",
    ],
}

BAD_EDGE_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "become",
    "between",
    "by",
    "changes",
    "combines",
    "connect",
    "connects",
    "digital",
    "empowers",
    "encourages",
    "for",
    "from",
    "improves",
    "in",
    "into",
    "involves",
    "is",
    "of",
    "one",
    "on",
    "or",
    "scalable",
    "reflects",
    "requires",
    "supports",
    "the",
    "to",
    "uses",
    "with",
}


@dataclass(frozen=True)
class MediaItem:
    media_id: str
    media_type: str
    about: str
    aim: str
    tokens: frozenset[str]


@dataclass(frozen=True)
class Candidate:
    media: MediaItem
    sentence_index: int
    sentence: str
    span: str
    score: float
    style: str
    strength: str


def _normalize_words(text: str) -> list[str]:
    return [
        w
        for w in re.findall(r"[a-zA-Z][a-zA-Z0-9]+", text.lower())
        if len(w) > 2 and w not in STOPWORDS
    ]


def _expanded_tokens(text: str) -> set[str]:
    out = set(_normalize_words(text))
    for word in list(out):
        out.update(SYNONYMS.get(word, set()))
    return out


def _read_prompt_file(name: str, fallback: str) -> str:
    path = PROMPT_DIR / name
    return path.read_text(encoding="utf-8").strip() if path.exists() else fallback.strip()


def _load_transcript_sentences(path: Path = TRANSCRIPTS_PATH) -> list[str]:
    sentences: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*\d+\.\s*(.+?)\s*$", line)
        if m:
            sentences.append(m.group(1).strip())
    if not sentences:
        raise ValueError(f"No numbered transcript lines found in {path}")
    return sentences


def _load_media(path: Path | None = None) -> list[MediaItem]:
    media_path = path or next((p for p in MEDIA_PATH_CANDIDATES if p.exists()), None)
    if media_path is None:
        raise FileNotFoundError("Expected output/media_skill.md or output/media_files.md")
    items: list[MediaItem] = []
    for line in media_path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*(media_\d+)\s*\|\s*([^|]+)\|\s*about:\s*(.+?)\s*$", line)
        if not m:
            continue
        media_id, media_type, about = m.group(1), m.group(2).strip(), m.group(3).strip()
        aim = "show when relevant caption topic is spoken"
        items.append(MediaItem(media_id, media_type, about, aim, frozenset(_expanded_tokens(about))))
    if not items:
        raise ValueError(f"No media rows found in {media_path}")
    return items


def _media_line(item: MediaItem) -> str:
    return f"{item.media_id} | {item.media_type} | about: {item.about} | aim: {item.aim}"


def _build_prompt(user_instruction: str, transcript: str, mandatory: list[MediaItem], optional: list[MediaItem]) -> str:
    planner_sp = _read_prompt_file(
        "planner_sp.md",
        "You are Media-Transcript Matching Planner.\nReturn valid JSON only.",
    )
    planner_os = _read_prompt_file("planner_os.md", "Planner output schema:")
    planner_body_template = _read_prompt_file(
        "planner_prompt.md",
        "USER INSTRUCTION:\n{user_instruction}\n\nFULL TRANSCRIPT:\n{full_transcript}\n\nMANDATORY MEDIA:\n{mandatory_media}\n\nOPTIONAL MEDIA:\n{optional_media}",
    )
    planner_body = planner_body_template.format(
        user_instruction=user_instruction,
        full_transcript=transcript,
        mandatory_media="\n".join(_media_line(x) for x in mandatory),
        optional_media="\n".join(_media_line(x) for x in optional) if optional else "(none)",
    )
    return "\n\n".join([planner_sp, planner_body, planner_os])


def _find_word_spans(sentence: str) -> list[tuple[str, int, int]]:
    return [(m.group(0), m.start(), m.end()) for m in re.finditer(r"[A-Za-z][A-Za-z0-9]*(?:[-'][A-Za-z0-9]+)?", sentence)]


def _choose_span(sentence: str, media: MediaItem, sentence_tokens: set[str]) -> str:
    words = _find_word_spans(sentence)
    if not words:
        return sentence
    best: tuple[float, int, str] | None = None
    max_len = min(10, len(words))
    for left in range(len(words)):
        for right in range(left + 1, min(len(words), left + max_len) + 1):
            chunk_words = [w[0] for w in words[left:right]]
            norm_words = [w.lower() for w in chunk_words]
            if len(norm_words) < 2:
                continue
            if norm_words[0] in BAD_EDGE_WORDS or norm_words[-1] in BAD_EDGE_WORDS:
                continue
            phrase = sentence[words[left][1] : words[right - 1][2]].strip(" ,.;:")
            phrase_tokens = _expanded_tokens(phrase)
            overlap = phrase_tokens & media.tokens
            if not overlap:
                continue
            exact_overlap = set(_normalize_words(phrase)) & set(_normalize_words(media.about))
            score = len(overlap) * 3.0 + len(exact_overlap) * 1.5
            # Editor-friendly phrase length: compact, but not clipped.
            phrase_len = len(_normalize_words(phrase))
            if 2 <= phrase_len <= 5:
                score += 1.25
            elif phrase_len > 6:
                score -= 0.4 * (phrase_len - 6)
            if any(w in {"ai", "artificial", "python", "cloud", "space", "gaming", "teacher", "student"} for w in norm_words):
                score += 0.75
            if best is None or score > best[0]:
                best = (score, phrase_len, phrase)
    if best:
        return best[2]
    # If no clean phrase survived, use the full short sentence rather than a broken fragment.
    if len(_normalize_words(sentence)) <= 9:
        return sentence.strip(" ,.;:")
    return sentence


def _style_for(media: MediaItem, span: str, score: float) -> str:
    text = f"{media.about} {span}".lower()
    if any(k in text for k in ("celebrating", "happy", "success", "motivation", "dreaming", "peacefully")):
        return "emotional"
    if media.media_type.lower() in {"gif", "sticker"} and any(k in text for k in ("funny", "rapidly", "fast", "victory", "reaction")):
        return "humorous"
    if media.media_type.lower() in {"gif", "sticker"} and any(k in text for k in ("question", "shocked", "notifications", "thinking", "progress")):
        return "reaction"
    if media.media_type.lower() == "video" and score >= 4:
        return "cinematic"
    if score <= 1.5:
        return "fallback"
    return "literal" if score >= 3 else "contextual"


def _candidate_for(media: MediaItem, sentence: str, sentence_index: int) -> Candidate | None:
    sentence_tokens = _expanded_tokens(sentence)
    overlap = media.tokens & sentence_tokens
    if not overlap:
        return None
    important = overlap - STOPWORDS
    score = float(len(important))
    # Reward exact media words found in the sentence.
    about_words = set(_normalize_words(media.about))
    sentence_words = set(_normalize_words(sentence))
    score += 0.75 * len(about_words & sentence_words)
    if score < 2.5:
        return None
    span = _choose_span(sentence, media, sentence_tokens)
    if len(_normalize_words(span)) < 2:
        return None
    style = _style_for(media, span, score)
    strength = "high" if score >= 4 else "medium" if score >= 2.5 else "low"
    if style == "fallback":
        strength = "low"
    return Candidate(media, sentence_index, sentence, span, score, style, strength)


def _collect_candidates(sentences: list[str], media_items: list[MediaItem], start: int, size: int) -> list[Candidate]:
    out: list[Candidate] = []
    for local_i, sentence in enumerate(sentences[start : start + size]):
        for item in media_items:
            cand = _candidate_for(item, sentence, local_i)
            if cand:
                out.append(cand)
    out.sort(key=lambda c: (-c.score, c.sentence_index, c.media.media_id))
    return out


def _non_overlapping(selected: list[Candidate], cand: Candidate, transcript: str) -> bool:
    span = transcript.find(cand.span)
    if span < 0:
        return False
    rng = (span, span + len(cand.span))
    for old in selected:
        old_span = transcript.find(old.span)
        if old_span < 0:
            continue
        old_rng = (old_span, old_span + len(old.span))
        if rng[0] < old_rng[1] and old_rng[0] < rng[1]:
            return False
    return True


def _make_example(index: int, rng: random.Random, sentences: list[str], media_items: list[MediaItem]) -> dict[str, Any] | None:
    window_size = rng.randint(7, 12)
    start = rng.randint(0, max(0, len(sentences) - window_size))
    transcript = " ".join(sentences[start : start + window_size])
    candidates = _collect_candidates(sentences, media_items, start, window_size)
    if len(candidates) < 4:
        return None

    selected: list[Candidate] = []
    used_media: set[str] = set()
    for cand in candidates:
        if cand.media.media_id in used_media:
            continue
        if not _non_overlapping(selected, cand, transcript):
            continue
        selected.append(cand)
        used_media.add(cand.media.media_id)
        if len(selected) >= rng.randint(4, 8):
            break
    if len(selected) < 4:
        return None

    selected.sort(key=lambda c: transcript.find(c.span))
    mandatory = [c.media for c in selected]
    optional_pool = [
        c.media
        for c in candidates
        if c.media.media_id not in used_media and c.score >= 2.5
    ]
    optional: list[MediaItem] = []
    seen_optional: set[str] = set()
    for item in optional_pool:
        if item.media_id in seen_optional:
            continue
        optional.append(item)
        seen_optional.add(item.media_id)
        if len(optional) >= rng.randint(0, 3):
            break

    instruction = rng.choice(
        [
            "Create a clean engaging short-form video with synced captions.",
            "Make the visuals feel like a sharp educational Shorts edit.",
            "Match each media asset to the strongest spoken visual beat.",
            "Use accurate media-text matching with concise editor-style spans.",
        ]
    )
    prompt = _build_prompt(instruction, transcript, mandatory, optional)
    matches = []
    for i, cand in enumerate(selected, start=1):
        style = cand.style
        reason = rng.choice(REASON_BY_STYLE[style])
        matches.append(
            {
                "match_id": f"match_{i:03d}",
                "text": cand.span,
                "media_id": cand.media.media_id,
                "match_strength": cand.strength,
                "match_style": style,
                "match_reason": reason,
                "mandatory_media": True,
            }
        )

    output = {
        "planner_version": "v3_media_text_matching",
        "matches": matches,
        "unmatched_text": [],
        "warnings": [],
    }
    row = {"messages": [{"role": "user", "content": prompt}, {"role": "assistant", "content": json.dumps(output, ensure_ascii=False)}]}
    errors = validate_planner_v3_example(prompt, row["messages"][1]["content"])
    return None if errors else row


def _write_sample_txt(rows: list[dict[str, Any]], path: Path, count: int = 5) -> None:
    blocks: list[str] = []
    for idx, row in enumerate(rows[:count], start=1):
        user = row["messages"][0]["content"]
        assistant = json.loads(row["messages"][1]["content"])
        transcript = re.search(r"FULL TRANSCRIPT:\n(.+?)\n\nMANDATORY MEDIA:", user, flags=re.S)
        mandatory = re.search(r"MANDATORY MEDIA:\n(.+?)\n\nOPTIONAL MEDIA:", user, flags=re.S)
        blocks.append(
            "\n".join(
                [
                    f"EXAMPLE {idx}",
                    "FULL TRANSCRIPT:",
                    transcript.group(1).strip() if transcript else "",
                    "",
                    "MANDATORY MEDIA:",
                    mandatory.group(1).strip() if mandatory else "",
                    "",
                    "GOLD OUTPUT:",
                    json.dumps(assistant, ensure_ascii=False, indent=2),
                ]
            )
        )
    path.write_text("\n\n" + ("=" * 80 + "\n\n").join(blocks), encoding="utf-8")


def generate(count: int, out: str | Path, seed: int = 20260513) -> dict[str, Any]:
    rng = random.Random(seed)
    sentences = _load_transcript_sentences()
    media_items = _load_media()
    rows: list[dict[str, Any]] = []
    seen_pairs: set[str] = set()
    attempts = 0
    while len(rows) < count and attempts < count * 80:
        attempts += 1
        row = _make_example(attempts, rng, sentences, media_items)
        if row is None:
            continue
        signature = row["messages"][0]["content"].split("FULL TRANSCRIPT:\n", 1)[1].split("\n\nMANDATORY MEDIA:", 1)[0]
        signature += row["messages"][1]["content"]
        if signature in seen_pairs:
            continue
        seen_pairs.add(signature)
        rows.append(row)
    if len(rows) < count:
        raise RuntimeError(f"Could only generate {len(rows)} valid examples after {attempts} attempts")

    out_path = Path(out)
    if not out_path.is_absolute():
        out_path = ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    pretty_path = OUT_DIR / "planner_v3_grounded_examples_pretty.json"
    pretty_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    sample_path = OUT_DIR / "planner_v3_grounded_5_examples.txt"
    _write_sample_txt(rows, sample_path)
    report = validate_jsonl(out_path)
    report_path = OUT_DIR / "grounded_validation_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "output": str(out_path),
        "pretty": str(pretty_path),
        "sample": str(sample_path),
        "report": str(report_path),
        **report,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=500)
    parser.add_argument("--out", default="output/planner_v3_grounded_500_examples.jsonl")
    parser.add_argument("--seed", type=int, default=20260513)
    args = parser.parse_args()
    result = generate(args.count, args.out, args.seed)
    print(json.dumps({k: result[k] for k in ("rows", "passed", "failed", "output", "sample")}, indent=2))
    return 0 if result["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
