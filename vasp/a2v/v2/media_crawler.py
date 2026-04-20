from __future__ import annotations

import csv
import os
import random
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests


SAFE_LICENSES = {"cc0", "pdm", "by", "by-sa"}
FUNNY_WORDS = ["funny", "meme", "reaction", "humor", "comedy", "silly", "cartoon"]
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".webm", ".ogv", ".ogg"}
ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "video/mp4",
    "video/webm",
    "video/ogg",
    "application/ogg",
}
DEFAULT_USER_AGENT = "VASP-SafeMediaCrawler/1.0"
GIPHY_SEARCH_URL = "https://api.giphy.com/v1/gifs/search"


def clean_name(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", text).strip("_").lower()[:80] or "media"


def ext_from_url(url: str, fallback: str = ".jpg") -> str:
    path = urlparse(url).path
    ext = os.path.splitext(path)[1].lower()
    return ext if ext in ALLOWED_EXTENSIONS else fallback


def is_probably_nsfw(text: str) -> bool:
    bad = [
        "nude",
        "nudity",
        "sex",
        "porn",
        "xxx",
        "erotic",
        "fetish",
        "blood",
        "gore",
        "violence",
        "weapon",
        "kill",
    ]
    t = (text or "").lower()
    return any(w in t for w in bad)


def _read_dotenv_value(key: str, env_path: str | Path = ".env") -> str:
    value = os.environ.get(key)
    if value:
        return value.strip()
    path = Path(env_path)
    if not path.exists():
        return ""
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            name, raw = stripped.split("=", 1)
            if name.strip() == key:
                return raw.strip().strip('"').strip("'")
    except Exception:
        return ""
    return ""


def _content_type_ok(content_type: str) -> bool:
    ct = (content_type or "").split(";")[0].strip().lower()
    return ct in ALLOWED_CONTENT_TYPES


def _fallback_ext_for_content_type(content_type: str, fallback: str) -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "video/mp4": ".mp4",
        "video/webm": ".webm",
        "video/ogg": ".ogv",
        "application/ogg": ".ogv",
    }.get(ct, fallback)


def download_file(
    url: str,
    out_path: str | Path,
    timeout: int = 30,
    max_bytes: int = 20 * 1024 * 1024,
) -> bool:
    out = Path(out_path)
    try:
        with requests.get(
            url,
            stream=True,
            timeout=timeout,
            headers={"User-Agent": DEFAULT_USER_AGENT},
        ) as resp:
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "").lower()
            if "html" in content_type or not _content_type_ok(content_type):
                return False
            expected_size = int(resp.headers.get("content-length") or 0)
            if expected_size > max_bytes:
                return False

            written = 0
            out.parent.mkdir(parents=True, exist_ok=True)
            with out.open("wb") as f:
                for chunk in resp.iter_content(8192):
                    if not chunk:
                        continue
                    written += len(chunk)
                    if written > max_bytes:
                        return False
                    f.write(chunk)

        return out.exists() and out.stat().st_size > 1024
    except Exception:
        return False


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    idx = 2
    while True:
        candidate = parent / f"{stem}_{idx}{suffix}"
        if not candidate.exists():
            return candidate
        idx += 1


def search_openverse(query: str, limit: int = 20) -> list[dict[str, Any]]:
    url = "https://api.openverse.engineering/v1/images/"
    params = {
        "q": query,
        "page_size": min(max(1, limit), 20),
        "license": ",".join(sorted(SAFE_LICENSES)),
        "mature": "false",
    }
    try:
        resp = requests.get(url, params=params, timeout=30, headers={"User-Agent": DEFAULT_USER_AGENT})
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    results: list[dict[str, Any]] = []
    for item in data.get("results", []):
        title = item.get("title") or query
        license_name = str(item.get("license") or "").lower()
        image_url = item.get("url")
        about = f"{title}. Topic: {query}. Source: Openverse. License: {license_name}."
        if not image_url or is_probably_nsfw(about) or license_name not in SAFE_LICENSES:
            continue
        results.append(
            {
                "url": image_url,
                "about": about,
                "source": "openverse",
                "license": license_name,
                "type": "image",
            }
        )
    return results


def _wikimedia_license_allowed(license_short: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "-", (license_short or "").lower()).strip("-")
    return (
        normalized in SAFE_LICENSES
        or normalized.startswith("cc-by")
        or normalized in {"public-domain", "public-domain-mark", "pd"}
    ) and "nc" not in normalized and "nd" not in normalized


def search_wikimedia(query: str, limit: int = 20) -> list[dict[str, Any]]:
    endpoint = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f"file:{query}",
        "gsrnamespace": 6,
        "gsrlimit": min(max(1, limit), 20),
        "prop": "imageinfo",
        "iiprop": "url|mime|extmetadata",
        "format": "json",
    }
    try:
        resp = requests.get(endpoint, params=params, timeout=30, headers={"User-Agent": DEFAULT_USER_AGENT})
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    pages = data.get("query", {}).get("pages", {})
    results: list[dict[str, Any]] = []
    for page in pages.values():
        title = page.get("title", "")
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        url = info.get("url")
        mime = str(info.get("mime") or "")
        license_short = str(meta.get("LicenseShortName", {}).get("value", "") or "")
        object_name = meta.get("ObjectName", {}).get("value", title)
        description = meta.get("ImageDescription", {}).get("value", "")
        clean_desc = re.sub("<.*?>", "", f"{object_name}. {description}")
        about = f"{clean_desc}. Topic: {query}. Source: Wikimedia Commons. License: {license_short}."
        if not url or is_probably_nsfw(about) or not _wikimedia_license_allowed(license_short):
            continue
        media_type = "image"
        if "gif" in mime:
            media_type = "gif"
        elif "video" in mime or str(url).lower().endswith((".webm", ".mp4", ".ogv")):
            media_type = "video"
        results.append(
            {
                "url": url,
                "about": about,
                "source": "wikimedia",
                "license": license_short,
                "type": media_type,
            }
        )
    return results


def search_giphy(query: str, limit: int = 20, rating: str = "g") -> list[dict[str, Any]]:
    api_key = _read_dotenv_value("GIPHY_API_KEY")
    if not api_key:
        return []
    params = {
        "api_key": api_key,
        "q": query,
        "limit": min(max(1, limit), 50),
        "rating": rating if rating in {"g", "pg"} else "g",
        "lang": "en",
    }
    try:
        resp = requests.get(GIPHY_SEARCH_URL, params=params, timeout=30, headers={"User-Agent": DEFAULT_USER_AGENT})
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    results: list[dict[str, Any]] = []
    for item in data.get("data", []):
        title = str(item.get("title") or query).strip() or query
        images = item.get("images") if isinstance(item.get("images"), dict) else {}
        original = images.get("original") if isinstance(images.get("original"), dict) else {}
        gif_url = str(original.get("url") or "").strip()
        about = f"{title}. Topic: {query}. Source: GIPHY. Rating: {params['rating']}."
        if not gif_url or is_probably_nsfw(about):
            continue
        results.append(
            {
                "url": gif_url,
                "about": about,
                "source": "giphy",
                "license": "giphy",
                "type": "gif",
            }
        )
    return results


def build_queries(topic: str, total: int, funny_percent: int) -> list[str]:
    funny_percent = max(0, min(100, int(funny_percent)))
    funny_count = round(total * funny_percent / 100)
    normal_count = max(0, total - funny_count)
    queries = [topic] * normal_count
    queries.extend(f"{random.choice(FUNNY_WORDS)} {topic}" for _ in range(funny_count))
    random.shuffle(queries)
    return queries


def crawl_media(
    topic: str,
    total: int,
    funny_percent: int,
    output_dir: str | Path,
    *,
    delay_s: float = 0.25,
    max_bytes: int = 20 * 1024 * 1024,
    filename_prefix: str = "",
) -> list[dict[str, Any]]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    captions_path = out_dir / "captions.txt"
    collected: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    queries = build_queries(topic, max(total * 2, total), funny_percent)
    idx = 1
    for query in queries:
        if len(collected) >= total:
            break
        candidates = search_openverse(query, limit=10) + search_wikimedia(query, limit=10) + search_giphy(query, limit=10)
        random.shuffle(candidates)
        for item in candidates:
            if len(collected) >= total:
                break
            url = str(item.get("url") or "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            ext = ext_from_url(url)
            filename = f"{filename_prefix}media_{idx}_{item.get('type', 'image')}_{clean_name(query)}{ext}"
            out_path = _unique_path(out_dir / filename)
            ok = download_file(url, out_path, max_bytes=max_bytes)
            if not ok:
                out_path.unlink(missing_ok=True)
                continue
            # If the URL extension was weak, keep the downloaded file extension
            # conservative rather than guessing from random pages.
            collected.append(
                {
                    "media_name": out_path.name,
                    "file": out_path.name,
                    "path": str(out_path).replace("\\", "/"),
                    "about": item.get("about", ""),
                    "source": item.get("source", ""),
                    "license": item.get("license", ""),
                    "type": item.get("type", "image"),
                    "url": url,
                }
            )
            idx += 1
            if delay_s > 0:
                time.sleep(delay_s)

    with captions_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["media_name", "about", "source", "license", "type", "url"])
        for row in collected:
            writer.writerow([row["media_name"], row["about"], row["source"], row["license"], row["type"], row["url"]])
    return collected


def crawl_one_gif_one_image(
    query: str,
    output_dir: str | Path,
    *,
    filename_prefix: str = "",
    delay_s: float = 0.25,
    max_bytes: int = 20 * 1024 * 1024,
) -> list[dict[str, Any]]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    collected: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    source_groups = [
        ("gif", search_giphy(query, limit=12)),
        ("image", search_openverse(query, limit=12) + search_wikimedia(query, limit=12)),
    ]
    for target_type, candidates in source_groups:
        random.shuffle(candidates)
        for item in candidates:
            item_type = str(item.get("type") or "").lower()
            if target_type == "gif" and item_type != "gif":
                continue
            if target_type == "image" and item_type != "image":
                continue
            url = str(item.get("url") or "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            ext = ".gif" if target_type == "gif" else ext_from_url(url)
            filename = f"{filename_prefix}{target_type}_{clean_name(query)}{ext}"
            out_path = _unique_path(out_dir / filename)
            ok = download_file(url, out_path, max_bytes=max_bytes)
            if not ok:
                out_path.unlink(missing_ok=True)
                continue
            collected.append(
                {
                    "media_name": out_path.name,
                    "file": out_path.name,
                    "path": str(out_path).replace("\\", "/"),
                    "about": item.get("about", ""),
                    "source": item.get("source", ""),
                    "license": item.get("license", ""),
                    "type": target_type,
                    "url": url,
                }
            )
            if delay_s > 0:
                time.sleep(delay_s)
            break
    return collected
