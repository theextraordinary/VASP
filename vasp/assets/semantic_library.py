from __future__ import annotations

from pathlib import Path


_SFX_MAP = {
    "whoosh_hit": "assets/inputs/sfx_whoosh_hit.wav",
    "dramatic_impact": "assets/inputs/sfx_dramatic_impact.wav",
    "calendar_flip": "assets/inputs/sfx_calendar_flip.wav",
    "dark_whoosh": "assets/inputs/sfx_dark_whoosh.wav",
    "stone_break": "assets/inputs/sfx_stone_break.wav",
    "epic_riser": "assets/inputs/sfx_epic_riser.wav",
    "paper_map_whoosh": "assets/inputs/sfx_paper_map_whoosh.wav",
    "soft_spark": "assets/inputs/sfx_soft_spark.wav",
    "soft_twinkle": "assets/inputs/sfx_soft_twinkle.wav",
    "gentle_whoosh": "assets/inputs/sfx_gentle_whoosh.wav",
    "science_ping": "assets/inputs/sfx_science_ping.wav",
    "crowd_cheer": "assets/inputs/sfx_crowd_cheer.wav",
    "comedic_hit": "assets/inputs/sfx_comedic_hit.wav",
    "record_scratch": "assets/inputs/sfx_record_scratch.wav",
}

_GIF_MAP = {
    "scratch_reveal": "assets/inputs/gif.gif",
}

_STICKER_MAP = {
    "logo_emth": "assets/inputs/sticker.png",
}


def list_semantic_sfx_keys() -> list[str]:
    return sorted(_SFX_MAP.keys())


def list_semantic_gif_keys() -> list[str]:
    return sorted(_GIF_MAP.keys())


def list_semantic_sticker_keys() -> list[str]:
    return sorted(_STICKER_MAP.keys())


def resolve_semantic_sfx(key: str | None) -> Path | None:
    if not key:
        return None
    k = str(key).strip().lower()
    raw = _SFX_MAP.get(k)
    if not raw:
        return None
    path = Path(raw)
    if not path.exists():
        return None
    return path


def resolve_semantic_gif(key: str | None) -> Path | None:
    if not key:
        return None
    raw = _GIF_MAP.get(str(key).strip().lower())
    if not raw:
        return None
    path = Path(raw)
    return path if path.exists() else None


def resolve_semantic_sticker(key: str | None) -> Path | None:
    if not key:
        return None
    raw = _STICKER_MAP.get(str(key).strip().lower())
    if not raw:
        return None
    path = Path(raw)
    return path if path.exists() else None
