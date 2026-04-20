from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

from vasp.a2v.v3.finetuning.planner_v3_dataset.validate_planner_v3_dataset import validate_jsonl, validate_planner_v3_example


ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "output"


PLANNER_SP = """You are Media-Transcript Matching Planner.
Your job is to match media assets to the transcript text parts they explain best.

Rules:
- Return valid JSON only.
- Use all mandatory media at least once.
- Optional media may be used only if it strongly matches transcript text.
- Mandatory media has priority over optional media.
- Each text part may be matched to only ONE media.
- One media may match multiple text parts.
- Prefer matching every meaningful transcript part; avoid leaving text unmatched unless no media fits.
- Match can be a word, phrase, sentence fragment, or full sentence.
- Always prioritize aim over about.
- If aim explicitly says media should be used for a certain topic/text, obey aim first.
- Match creatively like a video editor: use media where it improves clarity, humor, emotional impact, or topic relevance.
- Do not invent media ids.
- Do not output timestamps; segment_generator will recover timing from media.json word/caption timing.
- Do not output layout, animation, x/y/width/height.
- Do not match audio/caption ids."""


PLANNER_OS = """Planner output schema:

{
  "planner_version": "v3_media_text_matching",
  "matches": [
    {
      "match_id": "match_001",
      "text": "exact transcript text span",
      "media_id": "media_5",
      "match_strength": "high | medium | low",
      "match_style": "literal | emotional | humorous | contextual | reaction | cinematic | transition | fallback",
      "match_reason": "short varied reason",
      "mandatory_media": true
    }
  ],
  "unmatched_text": [
    {
      "text": "exact transcript text span",
      "reason": "no suitable media"
    }
  ],
  "warnings": []
}

Validation:
- Every mandatory visual media id must appear at least once in matches.
- No text span should overlap with another text span assigned to a different media.
- Each match.text must be copied exactly from transcript.
- No invented text.
- No invented media ids.
- Prefer emotional/reaction payoff, strong motion, and cinematic beats over weak literal filler.
- Date-only, connector-only, or filler-only spans are allowed only as low-strength fallback."""


DOMAINS: dict[str, dict[str, list[str]]] = {
    "science": {
        "topics": ["volcano ash cloud", "deep sea pressure", "magnetic field", "solar eclipse", "microscope slide"],
        "actions": ["revealed a hidden pattern", "changed the experiment", "confirmed the old theory", "surprised the research team"],
    },
    "history": {
        "topics": ["ancient trade route", "royal decree", "harbor archive", "lost manuscript", "city gate"],
        "actions": ["reshaped the kingdom", "started a public debate", "marked the turning point", "settled the dispute"],
    },
    "space": {
        "topics": ["Saturn's moon Titan", "Mars dust storm", "Jupiter's red spot", "lunar crater", "new telescope image"],
        "actions": ["gave astronomers a clear clue", "made the discovery famous", "confirmed the orbit", "opened a new question"],
    },
    "animals": {
        "topics": ["elephant migration", "octopus camouflage", "snow leopard trail", "bee waggle dance", "whale song"],
        "actions": ["helped scientists track behavior", "showed remarkable intelligence", "protected the group", "changed the survival strategy"],
    },
    "health": {
        "topics": ["vaccination clinic", "heart monitor", "sleep study", "nutrition label", "public health campaign"],
        "actions": ["lowered the risk", "helped doctors respond faster", "improved patient recovery", "made the advice easier to follow"],
    },
    "sports": {
        "topics": ["last minute goal", "defensive block", "coach strategy board", "scoreboard result", "training drill"],
        "actions": ["shifted the momentum", "sealed the victory", "exposed the weakness", "brought the crowd alive"],
    },
    "business": {
        "topics": ["market chart", "factory floor", "new product launch", "startup pitch", "central bank decision"],
        "actions": ["moved investor confidence", "changed production plans", "created fresh demand", "shaped the quarter"],
    },
    "education": {
        "topics": ["classroom experiment", "math proof", "robotics demo", "student presentation", "library archive"],
        "actions": ["made the concept simple", "helped students understand", "turned practice into progress", "created an aha moment"],
    },
    "mystery": {
        "topics": ["locked room clue", "strange footprint", "old photograph", "missing key", "foggy alley"],
        "actions": ["deepened the mystery", "pointed to the suspect", "changed the detective's theory", "made the reveal stronger"],
    },
    "emotion": {
        "topics": ["farewell letter", "family reunion", "quiet hospital hallway", "childhood photo", "standing ovation"],
        "actions": ["made the moment emotional", "brought relief", "turned sadness into hope", "gave the story its heart"],
    },
    "funny": {
        "topics": ["facepalm reaction", "awkward pause", "surprised dog meme", "office prank", "banana slip joke"],
        "actions": ["made the punchline land", "added comic timing", "turned the mistake into a laugh", "matched the silly result"],
    },
    "tech": {
        "topics": ["phone camera lens", "battery chip", "AI dashboard", "server rack", "app interface"],
        "actions": ["explained the feature", "showed the performance gain", "made the upgrade visible", "clarified the workflow"],
    },
    "environment": {
        "topics": ["wind farm", "solar panel field", "flood map", "forest recovery", "melting glacier"],
        "actions": ["showed the climate impact", "explained the energy shift", "made the risk visible", "pointed to the solution"],
    },
    "travel": {
        "topics": ["mountain train", "old market street", "coastal road", "airport board", "temple courtyard"],
        "actions": ["set the location clearly", "made the journey feel alive", "showed the destination", "added local color"],
    },
    "food": {
        "topics": ["steaming ramen bowl", "farmers market", "chocolate tempering", "street taco stand", "fresh bread oven"],
        "actions": ["made the flavor visual", "showed the craft", "explained the origin", "created appetite"],
    },
    "safety": {
        "topics": ["fire alarm", "seat belt reminder", "factory safety sign", "storm warning map", "first aid kit"],
        "actions": ["made the warning clear", "showed the correct action", "reduced confusion", "emphasized urgency"],
    },
    "news": {
        "topics": ["press conference", "city skyline", "election board", "breaking news desk", "court building"],
        "actions": ["gave context to the report", "showed the decision point", "made the update concrete", "framed the public reaction"],
    },
}


FILLERS = [
    "Today was the day",
    "The story moved forward",
    "For many viewers",
    "At first glance",
    "The context was easy to miss",
    "What happened next",
    "By the end of the day",
    "The detail mattered",
    "This was not obvious",
    "A small clue appeared",
]


TOPIC_VARIANTS = [
    "{topic}",
    "a close view of {topic}",
    "archival footage of {topic}",
    "a wide shot of {topic}",
    "a detailed look at {topic}",
    "the moment involving {topic}",
    "the scene around {topic}",
    "a clear example of {topic}",
    "the main visual of {topic}",
    "the background story of {topic}",
    "a second angle on {topic}",
    "a later reference to {topic}",
    "the evidence around {topic}",
    "the public reaction to {topic}",
    "the final result of {topic}",
    "a simple graphic about {topic}",
    "a field report on {topic}",
    "a memorable shot of {topic}",
]


MATCH_SENTENCE_TEMPLATES = [
    "The narrator explains how {span}.",
    "The key visual moment is when {span}.",
    "A focused shot helps show how {span}.",
    "The story becomes clearer as {span}.",
    "This part needs a visual because {span}.",
    "The edit should highlight how {span}.",
]


def _media_line(item: dict[str, Any]) -> str:
    return f"{item['media_id']} | {item['type']} | about: {item['about']} | aim: {item['aim']}"


def _build_prompt(user_instruction: str, transcript: str, mandatory: list[dict[str, Any]], optional: list[dict[str, Any]]) -> str:
    return (
        f"{PLANNER_SP}\n\n"
        f"USER INSTRUCTION:\n{user_instruction}\n\n"
        f"FULL TRANSCRIPT:\n{transcript}\n\n"
        f"MANDATORY MEDIA:\n" + "\n".join(_media_line(x) for x in mandatory) + "\n\n"
        f"OPTIONAL MEDIA:\n" + ("\n".join(_media_line(x) for x in optional) if optional else "(none)") + "\n\n"
        f"{PLANNER_OS}"
    )


def _make_media(domain: str, rng: random.Random, total: int, mandatory_count: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    bank = DOMAINS[domain]
    items: list[dict[str, Any]] = []
    topics = list(bank["topics"])
    rng.shuffle(topics)
    for i in range(total):
        base_topic = topics[i % len(topics)]
        topic = TOPIC_VARIANTS[i % len(TOPIC_VARIANTS)].format(topic=base_topic)
        type_ = rng.choice(["image", "video", "gif", "sticker"])
        media_id = f"media_{i + 2}"
        items.append(
            {
                "media_id": media_id,
                "type": type_,
                "topic": topic,
                "about": f"{type_} showing {topic}",
                "aim": f"use for transcript text about {topic}",
            }
        )
    return items[:mandatory_count], items[mandatory_count:]


def _example(index: int, rng: random.Random) -> dict[str, Any]:
    domain = rng.choice(list(DOMAINS))
    media_total = rng.randint(6, 18)
    mandatory_count = rng.randint(4, min(12, media_total))
    optional_count = rng.randint(0, min(5, media_total - mandatory_count))
    mandatory, optional_all = _make_media(domain, rng, media_total, mandatory_count)
    optional = optional_all[:optional_count]

    units: list[dict[str, Any]] = []
    sentences: list[str] = []
    for item in mandatory:
        action = rng.choice(DOMAINS[domain]["actions"])
        span = rng.choice(
            [
                f"{item['topic']} {action}",
                f"the {item['topic']} {action}",
                f"{item['topic']} became the key clue",
            ]
        )
        units.append({"text": span, "media_id": item["media_id"], "mandatory": True, "strength": rng.choice(["high", "high", "medium"])})
        sentences.append(rng.choice(MATCH_SENTENCE_TEMPLATES).format(span=span))
        if rng.random() < 0.22:
            second = f"{item['topic']} returned later in the explanation"
            units.append({"text": second, "media_id": item["media_id"], "mandatory": True, "strength": "medium"})
            sentences.append(rng.choice(MATCH_SENTENCE_TEMPLATES).format(span=second))

    for item in optional:
        if rng.random() < 0.55:
            span = f"{item['topic']} made the point easier to see"
            units.append({"text": span, "media_id": item["media_id"], "mandatory": False, "strength": "high"})
            sentences.append(rng.choice(MATCH_SENTENCE_TEMPLATES).format(span=span))

    filler_pool = list(FILLERS)
    rng.shuffle(filler_pool)
    unmatched_units = [{"text": text, "reason": "generic filler phrase with no useful media match"} for text in filler_pool[: rng.randint(2, 5)]]
    for unit in unmatched_units:
        sentences.append(f"{unit['text']}.")
    rng.shuffle(sentences)
    transcript = " ".join(sentences)

    matches: list[dict[str, Any]] = []
    unmatched_text: list[dict[str, Any]] = []
    for unit in units + unmatched_units:
        if "media_id" in unit:
            matches.append(
                {
                    "text": unit["text"],
                    "media_id": unit["media_id"],
                    "match_strength": unit["strength"],
                    "match_style": "fallback" if unit["strength"] == "low" else "literal",
                    "match_reason": _match_reason("fallback" if unit["strength"] == "low" else "literal", rng),
                    "mandatory_media": bool(unit["mandatory"]),
                }
            )
        else:
            unmatched_text.append({"text": unit["text"], "reason": unit["reason"]})

    # Sort by transcript order and assign ids. This enforces non-overlap naturally.
    matches.sort(key=lambda m: transcript.find(m["text"]))
    for i, m in enumerate(matches, start=1):
        m["match_id"] = f"match_{i:03d}"
    for m in matches:
        m.move_to_end("match_id", last=False) if hasattr(m, "move_to_end") else None

    ordered_matches = []
    for m in matches:
        ordered_matches.append(
            {
                "match_id": m["match_id"],
                "text": m["text"],
                "media_id": m["media_id"],
                "match_strength": m["match_strength"],
                "match_style": m["match_style"],
                "match_reason": m["match_reason"],
                "mandatory_media": m["mandatory_media"],
            }
        )

    output = {
        "planner_version": "v3_media_text_matching",
        "matches": ordered_matches,
        "unmatched_text": unmatched_text,
        "warnings": [],
    }
    prompt = _build_prompt(
        "Create a clear short-form edit by matching each visual asset to the transcript text it explains best.",
        transcript,
        mandatory,
        optional,
    )
    return {"messages": [{"role": "user", "content": prompt}, {"role": "assistant", "content": json.dumps(output, ensure_ascii=False)}]}


def _blueprint_media(category: str, rng: random.Random) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    specs = list(BLUEPRINT_TOPICS[category])
    rng.shuffle(specs)
    media_total = rng.randint(6, min(18, len(specs)))
    mandatory_count = rng.randint(4, min(12, media_total))
    optional_count = rng.randint(1, min(5, media_total - mandatory_count)) if media_total > mandatory_count else 0
    rows: list[dict[str, Any]] = []
    for i, (about, span, aim) in enumerate(specs[:media_total], start=2):
        rows.append(
            {
                "media_id": f"media_{i}",
                "type": rng.choice(["gif", "image", "video", "sticker"]),
                "about": about,
                "span": span,
                "aim": aim if rng.random() < 0.38 else "show when relevant caption topic is spoken",
            }
        )
    return rows[:mandatory_count], rows[mandatory_count : mandatory_count + optional_count]


def _optional_distractors(category: str, existing_count: int) -> list[dict[str, Any]]:
    if existing_count >= 2:
        return []
    distractors = [
        ("cute dolphin gif", "dolphins jump happily near a boat", "use only for ocean animal joy"),
        ("generic chart image", "a simple chart with no specific story", "use only if the transcript discusses charts"),
        ("random celebration sticker", "people celebrating with confetti", "use only for victory or relief"),
    ]
    out = []
    for i, (about, span, aim) in enumerate(distractors[: 2 - existing_count], start=20):
        out.append({"media_id": f"media_{i}", "type": "gif", "about": about, "span": span, "aim": aim})
    return out


def _span_sentence(span: str, rng: random.Random) -> str:
    templates = [
        "A quick cut to {span} makes the point clear.",
        "The edit can briefly hold on {span}.",
        "The next visual beat focuses on {span}.",
        "This moment is easiest to show with {span}.",
        "The scene lands better when we see {span}.",
        "The shot gets stronger once {span} appears.",
    ]
    return rng.choice(templates).format(span=span)


PUNCHY_TERMS = {
    "escape", "collapse", "supernovas", "shocked", "clumsy", "underwater", "freezing",
    "roads", "aqueducts", "gladiators", "generate", "seconds", "eruptions", "lava",
    "signals", "blood", "memes", "millions", "glowing", "unexplored", "pyramids",
    "treasures", "memory", "sleep", "Mars", "radiation", "lightning", "thunder",
    "fastest", "accelerate", "Bushido", "caffeine", "tornadoes", "radar", "checkmate",
    "echolocation", "Moon", "pollinating", "pirates", "treasure", "fear", "thrilling",
    "symbols", "G-forces", "crashed", "ended", "victory", "decline", "exploded",
    "rushed", "buy", "pitch", "confidence", "policy", "warning", "mystery",
    "reveal", "tears", "laugh", "punchline", "mistake",
}


STOP_START = {
    "a", "an", "the", "to", "of", "and", "or", "for", "with", "by", "in", "on",
    "showed", "made", "gave", "helped", "changed", "pointed", "fed", "became",
}
WEAK_END = {
    "the", "a", "an", "to", "of", "and", "or", "for", "with", "by", "in", "on",
    "as", "is", "are", "was", "were", "into", "from", "when", "where",
    "showed", "made", "gave", "helped", "changed", "pointed", "opened", "recorded", "spread", "moved",
    "fed", "new", "attracted", "reached", "shifted", "brought", "landed", "looked",
}
WEAK_SPANS = {"are known", "is known", "was known", "were known", "to see", "to buy", "as the", "in the", "of the"}
MATCH_STYLES = {"literal", "emotional", "humorous", "contextual", "reaction", "cinematic", "transition", "fallback"}

REACTION_MARKERS = (
    "shocked",
    "surprised",
    "reaction",
    "facepalm",
    "awkward",
    "crying",
    "celebrating",
    "celebration",
    "laughing",
    "panic",
    "screaming",
    "finally",
)

REASONS_BY_STYLE = {
    "literal": [
        "Direct object match for the spoken concept.",
        "Exact person or object anchor for the beat.",
        "Clear visual reference for the named subject.",
        "Specific visual match that keeps the edit readable.",
    ],
    "emotional": [
        "Emotional visual support for the story turn.",
        "Strong feeling match for the payoff phrase.",
        "Human reaction emphasis for the emotional beat.",
        "Sentimental visual that makes the moment land.",
    ],
    "humorous": [
        "Humorous metaphor that makes the beat more engaging.",
        "Meme-style visual that sharpens the joke.",
        "Comedic timing match for the punchy phrase.",
        "Funny exaggeration that fits the spoken moment.",
    ],
    "contextual": [
        "Contextual match that supports the broader idea.",
        "Supporting visual that keeps the scene grounded.",
        "Background context for the narration beat.",
        "Useful visual context without stealing the scene.",
    ],
    "reaction": [
        "Reaction-style visual for the surprise moment.",
        "Expressive reaction beat for what the viewer should feel.",
        "Audience-feeling match for the unexpected phrase.",
        "Reaction cutaway that makes the moment more alive.",
    ],
    "cinematic": [
        "Cinematic reveal visual for the payoff phrase.",
        "Hero-style visual for the strongest beat.",
        "Dramatic visual emphasis for the reveal.",
        "Big-screen moment that deserves a longer hold.",
    ],
    "transition": [
        "Transition beat that bridges two visual ideas.",
        "Quick connective visual for the scene change.",
        "Pacing visual that helps the edit move cleanly.",
        "Bridge shot that supports the next idea.",
    ],
    "fallback": [
        "Mandatory fallback placed on the closest usable phrase.",
        "Weak but required visual coverage for the mandatory asset.",
        "Closest available phrase for mandatory media coverage.",
        "Fallback match because no stronger transcript beat exists.",
    ],
}


def _is_good_span(text: str) -> bool:
    words = text.split()
    if len(words) < 2 or len(words) > 8:
        return False
    norm = text.lower().strip(".,;:!?")
    if norm in WEAK_SPANS:
        return False
    if words[0].lower().strip(".,;:!?") in STOP_START:
        return False
    if words[-1].lower().strip(".,;:!?") in WEAK_END:
        return False
    meaningful = [w for w in words if w.lower().strip(".,;:!?") not in STOP_START | WEAK_END]
    return len(meaningful) >= 2


def _clean_window(words: list[str], start: int, end: int) -> str:
    start = max(0, start)
    end = min(len(words), end)
    while start < end and words[start].strip(".,;:!?").lower() in STOP_START:
        start += 1
    while end > start and words[end - 1].strip(".,;:!?").lower() in WEAK_END:
        end -= 1
    if end - start < 2:
        start = max(0, start - 1)
        end = min(len(words), end + 2)
        while start < end and words[start].strip(".,;:!?").lower() in STOP_START:
            start += 1
    return " ".join(words[start:end]).strip()


def _editor_span(full_span: str, rng: random.Random) -> str:
    words = full_span.split()
    if len(words) <= 4:
        return full_span
    lowered = [w.strip(".,;:!?").lower() for w in words]
    candidates: list[str] = []
    connector_verbs = {
        "showed", "made", "gave", "helped", "changed", "pointed", "opened", "recorded",
        "spread", "moved", "created", "fed", "attracted", "reached", "shifted", "brought",
        "landed", "looked", "exploded",
    }
    for i, word in enumerate(lowered):
        if word in connector_verbs and i >= 2:
            subject = _clean_window(words, 0, i)
            obj = _clean_window(words, i + 1, min(len(words), i + 7))
            subject_action = _clean_window(words, max(0, i - 2), min(len(words), i + 3))
            full_clean = _clean_window(words, 0, min(len(words), i + 5))
            for picked in (subject, obj, full_clean, subject_action):
                if _is_good_span(picked):
                    candidates.append(picked)
        if word in {"were", "was", "are", "is"} and i + 1 < len(words):
            picked = _clean_window(words, i + 1, min(len(words), i + 5))
            if _is_good_span(picked):
                candidates.append(picked)
    for i, word in enumerate(lowered):
        if word in PUNCHY_TERMS:
            start = max(0, i - rng.choice([0, 1]))
            end = min(len(words), i + rng.choice([2, 3, 4]))
            picked = _clean_window(words, start, end)
            if _is_good_span(picked):
                candidates.append(picked)
    if lowered[0] in {"the", "a", "an"} and len(words) >= 4:
        picked = _clean_window(words, 1, min(len(words), 5))
        if _is_good_span(picked):
            candidates.append(picked)
    if "when" in lowered:
        i = lowered.index("when")
        picked = _clean_window(words, i + 1, min(len(words), i + 6))
        if _is_good_span(picked):
            candidates.append(picked)
    if "where" in lowered:
        i = lowered.index("where")
        picked = _clean_window(words, i + 1, min(len(words), i + 6))
        if _is_good_span(picked):
            candidates.append(picked)
    if "that" in lowered:
        i = lowered.index("that")
        picked = _clean_window(words, i + 1, min(len(words), i + 6))
        if _is_good_span(picked):
            candidates.append(picked)
    for start in range(0, max(1, len(words) - 2)):
        for size in (3, 4, 5, 6):
            picked = _clean_window(words, start, start + size)
            if _is_good_span(picked):
                candidates.append(picked)
    if candidates:
        return candidates[0]
    return " ".join(words[: min(5, len(words))])


def _match_style(item: dict[str, Any], strength: str, rng: random.Random) -> str:
    about = str(item.get("about", "")).lower()
    aim = str(item.get("aim", "")).lower()
    text = f"{about} {aim}"
    if strength == "low":
        return "fallback"
    if any(marker in text for marker in REACTION_MARKERS):
        return rng.choice(["reaction", "humorous", "emotional"])
    if "funny" in aim:
        return rng.choice(["humorous", "reaction"])
    if "emotional" in aim:
        return rng.choice(["emotional", "reaction", "cinematic"])
    if "shocking" in aim:
        return rng.choice(["cinematic", "reaction"])
    if "scientific" in aim:
        return rng.choice(["literal", "contextual"])
    if str(item.get("type", "")).lower() in {"gif", "sticker"} and rng.random() < 0.35:
        return rng.choice(["reaction", "humorous", "transition"])
    return rng.choice(["literal", "literal", "contextual", "cinematic"])


def _match_reason(style: str, rng: random.Random) -> str:
    return rng.choice(REASONS_BY_STYLE.get(style, REASONS_BY_STYLE["contextual"]))


def _multi_cut_sentence(spans: list[str], rng: random.Random) -> str:
    if len(spans) == 2:
        return rng.choice(
            [
                "The scene first highlights {a}, then quickly cuts to {b}.",
                "The narration gives us {a} before the edit snaps to {b}.",
                "The pacing works as a quick contrast between {a} and {b}.",
            ]
        ).format(a=spans[0], b=spans[1])
    return rng.choice(
        [
            "The sequence moves from {a} to {b}, then finishes on {c}.",
            "A rapid edit can show {a}, switch to {b}, and end on {c}.",
            "The story builds with {a}, then {b}, and finally {c}.",
        ]
    ).format(a=spans[0], b=spans[1], c=spans[2])


def _blueprint_example(index: int, rng: random.Random, category: str) -> dict[str, Any]:
    mandatory, optional = _blueprint_media(category, rng)
    optional = optional + _optional_distractors(category, len(optional))
    units: list[dict[str, Any]] = []
    sentence_units: list[list[dict[str, Any]]] = []

    hook = rng.choice(
        [
            "Today was the day.",
            "At first glance, the story seems simple.",
            "The opening sounds ordinary, but the details get stranger.",
            "For a short-form edit, the first detail needs to land quickly.",
        ]
    )
    ending = rng.choice(
        [
            "By the end, the whole story feels much clearer.",
            "That final detail gives the edit a strong ending.",
            "The last moment makes the earlier clues feel connected.",
            "This is why the visual choices matter.",
        ]
    )

    for item in mandatory:
        span = _editor_span(item["span"], rng)
        strength = rng.choice(["high", "high", "high", "medium", "medium", "low"])
        unit = {"text": span, "media_id": item["media_id"], "mandatory": True, "strength": strength, "item": item}
        units.append(unit)
        sentence_units.append([unit])
        if rng.random() < 0.22:
            later = rng.choice([f"{span} returns", f"another look at {span}", f"{span} appears again"])
            second = {"text": later, "media_id": item["media_id"], "mandatory": True, "strength": "medium", "item": item}
            units.append(second)
            sentence_units.append([second])

    for item in optional:
        if "generic" in item["about"] or "random" in item["about"] or "cute dolphin" in item["about"]:
            continue
        if rng.random() < 0.68:
            span = _editor_span(item["span"], rng)
            unit = {"text": span, "media_id": item["media_id"], "mandatory": False, "strength": "high", "item": item}
            units.append(unit)
            sentence_units.append([unit])

    # Teach clean splitting when multiple visuals can fit one sentence.
    rng.shuffle(sentence_units)
    compacted: list[list[dict[str, Any]]] = []
    i = 0
    while i < len(sentence_units):
        if i + 2 < len(sentence_units) and rng.random() < 0.28:
            compacted.append([sentence_units[i][0], sentence_units[i + 1][0], sentence_units[i + 2][0]])
            i += 3
        elif i + 1 < len(sentence_units) and rng.random() < 0.35:
            compacted.append([sentence_units[i][0], sentence_units[i + 1][0]])
            i += 2
        else:
            compacted.append(sentence_units[i])
            i += 1

    sentences = [hook]
    for group in compacted:
        if len(group) == 1:
            sentences.append(_span_sentence(group[0]["text"], rng))
        else:
            sentences.append(_multi_cut_sentence([g["text"] for g in group], rng))

    filler_pool = [
        "The detail mattered.",
        "This was not obvious.",
        "For many viewers, the context was easy to miss.",
        "A small clue appeared.",
        "The story moved forward.",
    ]
    rng.shuffle(filler_pool)
    unmatched_text = []
    if rng.random() < 0.12:
        for filler in filler_pool[: rng.randint(1, 2)]:
            clean = filler[:-1] if filler.endswith(".") else filler
            sentences.append(filler)
            unmatched_text.append({"text": clean, "reason": "generic filler phrase with no suitable media"})
    sentences.append(ending)
    if rng.random() < 0.18:
        unmatched_text.append({"text": ending[:-1], "reason": "closing narration does not need a separate media match"})

    # Keep hook first and ending last, shuffle the middle for variety.
    middle = sentences[1:-1]
    rng.shuffle(middle)
    transcript = " ".join([sentences[0], *middle, sentences[-1]])
    matches: list[dict[str, Any]] = []
    for unit in units:
        style = _match_style(unit["item"], unit["strength"], rng)
        matches.append(
            {
                "text": unit["text"],
                "media_id": unit["media_id"],
                "match_strength": unit["strength"],
                "match_style": style,
                "match_reason": _match_reason(style, rng),
                "mandatory_media": bool(unit["mandatory"]),
            }
        )
    matches.sort(key=lambda m: transcript.find(m["text"]))
    ordered = []
    for i, m in enumerate(matches, start=1):
        ordered.append(
            {
                "match_id": f"match_{i:03d}",
                "text": m["text"],
                "media_id": m["media_id"],
                "match_strength": m["match_strength"],
                "match_style": m["match_style"],
                "match_reason": m["match_reason"],
                "mandatory_media": m["mandatory_media"],
            }
        )
    output = {
        "planner_version": "v3_media_text_matching",
        "matches": ordered,
        "unmatched_text": unmatched_text,
        "warnings": [],
    }
    prompt = _build_prompt(
        "Create a clear short-form edit by matching each visual asset to the transcript text it explains best.",
        transcript,
        mandatory,
        optional,
    )
    return {"messages": [{"role": "user", "content": prompt}, {"role": "assistant", "content": json.dumps(output, ensure_ascii=False)}]}


BLUEPRINT_COUNTS = [
    ("Space & Astronomy", 35),
    ("Animals & Nature", 35),
    ("Human Body & Science", 30),
    ("Historical Events", 40),
    ("Wars & Politics", 35),
    ("Technology & AI", 30),
    ("Sports Moments", 20),
    ("Business & Money", 20),
    ("Internet Culture", 20),
    ("Food & Cooking", 20),
    ("Mystery & Crime", 20),
    ("Motivation & Success", 20),
    ("Funny Facts", 35),
    ("Emotional Stories", 20),
    ("Travel & Geography", 20),
    ("Environment & Climate", 20),
    ("Inventions & Discoveries", 25),
    ("Ancient Civilizations", 20),
    ("Psychology & Human Behavior", 20),
    ("Ocean & Deep Sea", 25),
]


BLUEPRINT_TOPICS = {
    "Space & Astronomy": [
        ("black hole animation", "black holes are regions where gravity becomes so strong that even light cannot escape", "show when relevant caption topic is spoken"),
        ("exploding star gif", "massive stars collapse after exploding as supernovas", "use during shocking fact"),
        ("milky way image", "a giant black hole exists at the center of our galaxy", "show when relevant caption topic is spoken"),
        ("astronaut floating sticker", "astronauts drift through deep space", "use during emotional reveal"),
        ("spinning galaxy video", "galaxies spin slowly across enormous distances", "emphasize scientific explanation"),
        ("scientist shocked gif", "scientists were shocked by the discovery", "use during funny moment"),
        ("mars rover image", "rovers explore the dusty surface of Mars", "show when relevant caption topic is spoken"),
        ("moon crater video", "the lunar surface is covered with ancient craters", "show when relevant caption topic is spoken"),
        ("rocket launch gif", "rockets lift spacecraft beyond Earth's atmosphere", "use during shocking fact"),
        ("telescope dome image", "telescopes reveal objects too distant for human eyes", "emphasize scientific explanation"),
    ],
    "Animals & Nature": [
        ("penguin walking funny gif", "penguins may look clumsy on land", "use during funny moment"),
        ("underwater penguin video", "underwater penguins are incredibly fast swimmers", "show when relevant caption topic is spoken"),
        ("snow storm video", "emperor penguins survive freezing Antarctic temperatures", "show when relevant caption topic is spoken"),
        ("fish image", "penguins dive deep while hunting fish", "show when relevant caption topic is spoken"),
        ("shark swimming video", "sharks have existed for hundreds of millions of years", "show when relevant caption topic is spoken"),
        ("electric signal animation", "some sharks detect tiny electrical signals", "emphasize scientific explanation"),
        ("cheetah running video", "cheetahs are the fastest land animals on Earth", "show when relevant caption topic is spoken"),
        ("bee macro video", "bees pollinate crops and wild plants", "show when relevant caption topic is spoken"),
        ("dolphin jumping video", "dolphins are known for playful behavior", "show when relevant caption topic is spoken"),
        ("sonar animation", "dolphins navigate underwater through echolocation", "emphasize scientific explanation"),
    ],
    "Human Body & Science": [
        ("human brain image", "the human brain constantly stores and processes memories", "emphasize scientific explanation"),
        ("sleeping person gif", "sleep strengthens long-term memory formation", "show when relevant caption topic is spoken"),
        ("heart monitor video", "heart monitors help doctors respond faster", "show when relevant caption topic is spoken"),
        ("brain stimulation animation", "caffeine affects the human brain and nervous system", "emphasize scientific explanation"),
        ("doctor research image", "scientists still study why sleep paralysis happens", "show when relevant caption topic is spoken"),
        ("frightened reaction gif", "fear is commonly reported during sleep paralysis", "use during emotional reveal"),
        ("microscope slide image", "microscopes reveal details hidden from the naked eye", "emphasize scientific explanation"),
        ("DNA animation", "DNA carries instructions for living cells", "emphasize scientific explanation"),
        ("immune cell video", "immune cells attack dangerous invaders", "show when relevant caption topic is spoken"),
    ],
    "Historical Events": [
        ("roman road image", "the Roman Empire built massive roads", "show when relevant caption topic is spoken"),
        ("aqueduct video", "Roman engineers created giant aqueducts", "show when relevant caption topic is spoken"),
        ("gladiator arena gif", "gladiators fought in giant arenas", "use during shocking fact"),
        ("emperor painting", "emperors ruled from lavish palaces", "show when relevant caption topic is spoken"),
        ("moon landing footage", "astronauts landed on the Moon during Apollo 11", "show when relevant caption topic is spoken"),
        ("television audience reaction", "millions watched the historic event live on television", "use during emotional reveal"),
        ("ancient manuscript image", "old manuscripts preserved forgotten stories", "show when relevant caption topic is spoken"),
        ("revolution crowd video", "crowds gathered as the revolution spread", "show when relevant caption topic is spoken"),
        ("historic map image", "maps connected distant cities and trade routes", "show when relevant caption topic is spoken"),
    ],
    "Wars & Politics": [
        ("battle map animation", "forces launched the final offensive", "show when relevant caption topic is spoken"),
        ("peace talks image", "peace talks began after years of conflict", "show when relevant caption topic is spoken"),
        ("soldiers celebrating gif", "the war finally ended", "use during emotional reveal"),
        ("parliament vote image", "parliament passed the act", "show when relevant caption topic is spoken"),
        ("protest march video", "campaigners marched through the streets", "show when relevant caption topic is spoken"),
        ("broken chains image", "the law made slave trading illegal", "use during emotional reveal"),
        ("court building image", "the court decision changed public policy", "show when relevant caption topic is spoken"),
        ("election board image", "the election result shifted political power", "show when relevant caption topic is spoken"),
        ("press conference video", "leaders announced the agreement", "show when relevant caption topic is spoken"),
    ],
    "Technology & AI": [
        ("robot typing gif", "artificial intelligence is changing how people work", "show when relevant caption topic is spoken"),
        ("AI brain animation", "modern AI systems generate images and essays", "emphasize scientific explanation"),
        ("futuristic city video", "AI could become one of the most important technologies", "use during shocking fact"),
        ("surprised man reaction gif", "experts were surprised by the speed of progress", "use during funny moment"),
        ("phone interface video", "the app interface opens instantly", "show when relevant caption topic is spoken"),
        ("battery chip image", "the battery lasts two days", "show when relevant caption topic is spoken"),
        ("server rack video", "servers process millions of requests", "show when relevant caption topic is spoken"),
        ("camera lens image", "the camera captures sharp night photos", "show when relevant caption topic is spoken"),
    ],
    "Sports Moments": [
        ("formula one race video", "Formula One cars are among the fastest racing machines", "show when relevant caption topic is spoken"),
        ("speed telemetry animation", "drivers experience intense G forces", "emphasize scientific explanation"),
        ("driver helmet closeup", "drivers turn corners at extreme speeds", "show when relevant caption topic is spoken"),
        ("cheering crowd gif", "the crowd exploded after the final point", "use during emotional reveal"),
        ("chess board image", "chess is one of the greatest strategy games", "show when relevant caption topic is spoken"),
        ("thinking genius gif", "grandmasters think many moves ahead", "use during funny moment"),
        ("AI computer animation", "modern chess engines defeat top human players", "show when relevant caption topic is spoken"),
    ],
    "Business & Money": [
        ("market chart image", "the market chart showed a sharp decline", "show when relevant caption topic is spoken"),
        ("factory floor video", "production plans changed after demand rose", "show when relevant caption topic is spoken"),
        ("startup pitch image", "the startup pitch attracted investors", "show when relevant caption topic is spoken"),
        ("central bank building", "the central bank decision moved confidence", "show when relevant caption topic is spoken"),
        ("cash register gif", "customers rushed to buy the product", "use during funny moment"),
        ("budget sheet image", "budget policy changed the forecast", "show when relevant caption topic is spoken"),
    ],
    "Internet Culture": [
        ("viral meme gif", "internet memes spread across social media at incredible speed", "use during funny moment"),
        ("social media animation", "a single funny video reached millions within hours", "show when relevant caption topic is spoken"),
        ("laughing crowd gif", "the joke became part of global culture", "use during funny moment"),
        ("phone scrolling video", "people shared the clip on their phones", "show when relevant caption topic is spoken"),
        ("comment section screenshot", "the comment section turned the moment into a meme", "use during funny moment"),
        ("creator reaction gif", "the creator looked shocked by the response", "use during emotional reveal"),
    ],
    "Food & Cooking": [
        ("coffee pouring gif", "millions of people drink coffee every morning", "show when relevant caption topic is spoken"),
        ("coffee beans image", "different roasting methods change coffee flavor", "show when relevant caption topic is spoken"),
        ("sleepy person reaction", "caffeine helps people feel awake and focused", "use during funny moment"),
        ("ramen bowl video", "steaming ramen made the flavor visual", "show when relevant caption topic is spoken"),
        ("farmers market image", "fresh ingredients came from the farmers market", "show when relevant caption topic is spoken"),
        ("chef chopping gif", "the chef prepared everything in seconds", "use during funny moment"),
    ],
    "Mystery & Crime": [
        ("locked room image", "the locked room clue changed the detective's theory", "show when relevant caption topic is spoken"),
        ("strange footprint image", "a strange footprint pointed to the suspect", "show when relevant caption topic is spoken"),
        ("foggy alley video", "the foggy alley deepened the mystery", "show when relevant caption topic is spoken"),
        ("scary shadow gif", "a shadow appeared behind the door", "use during shocking fact"),
        ("old photograph image", "an old photograph revealed the missing connection", "show when relevant caption topic is spoken"),
        ("police tape video", "police sealed the scene after midnight", "show when relevant caption topic is spoken"),
    ],
    "Motivation & Success": [
        ("runner training video", "daily practice slowly built momentum", "show when relevant caption topic is spoken"),
        ("mountain summit image", "the final climb became a symbol of success", "use during emotional reveal"),
        ("standing ovation gif", "the audience gave a standing ovation", "use during emotional reveal"),
        ("notebook goals image", "writing clear goals made progress visible", "show when relevant caption topic is spoken"),
        ("early morning alarm gif", "the first habit started before sunrise", "use during funny moment"),
        ("trophy closeup image", "the trophy represented years of discipline", "show when relevant caption topic is spoken"),
    ],
    "Funny Facts": [
        ("penguin walking funny gif", "penguins may look clumsy on land", "use during funny moment"),
        ("banana slip joke gif", "the banana fact made everyone laugh", "use during funny moment"),
        ("surprised dog meme", "the surprising answer looked ridiculous", "use during funny moment"),
        ("facepalm reaction", "the mistake was obvious in hindsight", "use during funny moment"),
        ("awkward pause gif", "the room went silent after the reveal", "use during funny moment"),
        ("laughing crowd gif", "the punchline landed perfectly", "use during funny moment"),
    ],
    "Emotional Stories": [
        ("farewell letter image", "the farewell letter changed the mood", "use during emotional reveal"),
        ("family reunion video", "the family reunion brought everyone to tears", "use during emotional reveal"),
        ("quiet hospital hallway", "the quiet hospital hallway made the scene heavy", "show when relevant caption topic is spoken"),
        ("childhood photo image", "the childhood photo gave the story its heart", "use during emotional reveal"),
        ("crying reaction gif", "the emotional reveal was hard to ignore", "use during emotional reveal"),
        ("sunrise hope video", "the sunrise turned sadness into hope", "use during emotional reveal"),
    ],
    "Travel & Geography": [
        ("mountain train video", "the mountain train set the location clearly", "show when relevant caption topic is spoken"),
        ("old market street image", "the old market street added local color", "show when relevant caption topic is spoken"),
        ("coastal road video", "the coastal road made the journey feel alive", "show when relevant caption topic is spoken"),
        ("airport board image", "the airport board showed the next destination", "show when relevant caption topic is spoken"),
        ("temple courtyard image", "the temple courtyard revealed the history of the place", "show when relevant caption topic is spoken"),
        ("map route animation", "the route map connected every stop", "emphasize scientific explanation"),
    ],
    "Environment & Climate": [
        ("wind farm video", "the wind farm showed the energy shift", "show when relevant caption topic is spoken"),
        ("solar panel field", "solar panels fed power into the grid", "show when relevant caption topic is spoken"),
        ("flood map image", "the flood map made the climate risk visible", "use during shocking fact"),
        ("forest recovery video", "forest recovery pointed to the solution", "use during emotional reveal"),
        ("melting glacier image", "the melting glacier showed the climate impact", "use during shocking fact"),
        ("heatwave reaction gif", "the heatwave shocked local residents", "use during emotional reveal"),
    ],
    "Inventions & Discoveries": [
        ("pendulum clock image", "the pendulum clock changed timekeeping", "show when relevant caption topic is spoken"),
        ("light bulb animation", "the light bulb made electric lighting practical", "show when relevant caption topic is spoken"),
        ("printing press video", "the printing press spread ideas faster", "show when relevant caption topic is spoken"),
        ("telescope image", "the telescope opened a new view of the sky", "show when relevant caption topic is spoken"),
        ("lab discovery gif", "scientists were shocked by the discovery", "use during funny moment"),
        ("patent document image", "the patent document recorded the invention", "show when relevant caption topic is spoken"),
    ],
    "Ancient Civilizations": [
        ("pyramid image", "ancient Egyptians built pyramids that still stand", "show when relevant caption topic is spoken"),
        ("pharaoh artwork", "pharaohs were buried with sacred objects", "show when relevant caption topic is spoken"),
        ("treasure chest gif", "treasures filled the royal tomb", "use during shocking fact"),
        ("maya pyramid image", "the ancient Maya built massive stone pyramids", "show when relevant caption topic is spoken"),
        ("astronomy stone carving", "Maya astronomers tracked stars and planets", "emphasize scientific explanation"),
        ("symbol carving gif", "their writing used complex carved symbols", "show when relevant caption topic is spoken"),
    ],
    "Psychology & Human Behavior": [
        ("brain scan image", "the brain reacts quickly to emotional experiences", "emphasize scientific explanation"),
        ("crowd behavior video", "people often copy the behavior of a group", "show when relevant caption topic is spoken"),
        ("memory animation", "emotional memories are remembered more clearly", "show when relevant caption topic is spoken"),
        ("mirror reaction gif", "body language can reveal hidden confidence", "use during funny moment"),
        ("decision maze image", "small choices can change later behavior", "show when relevant caption topic is spoken"),
        ("calm breathing video", "slow breathing helped reduce stress", "show when relevant caption topic is spoken"),
    ],
    "Ocean & Deep Sea": [
        ("glowing fish gif", "strange glowing creatures survive in the deep sea", "show when relevant caption topic is spoken"),
        ("submarine video", "submarines explore places sunlight never reaches", "show when relevant caption topic is spoken"),
        ("dark ocean animation", "the deepest parts of the ocean remain unexplored", "show when relevant caption topic is spoken"),
        ("scientist discovery reaction", "scientists discover new species every year", "use during emotional reveal"),
        ("giant squid image", "giant squid live in deep and mysterious water", "use during shocking fact"),
        ("hydrothermal vent video", "hydrothermal vents support life without sunlight", "emphasize scientific explanation"),
    ],
}

def generate(count: int, out: str | Path, seed: int = 12345) -> dict[str, Any]:
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    schedule: list[str] = []
    for category, n in BLUEPRINT_COUNTS:
        schedule.extend([category] * n)
    if len(schedule) < count:
        cats = [c for c, _ in BLUEPRINT_COUNTS]
        while len(schedule) < count:
            schedule.append(rng.choice(cats))
    schedule = schedule[:count]
    rng.shuffle(schedule)
    attempts = 0
    while len(rows) < count and attempts < count * 20:
        attempts += 1
        row = _blueprint_example(attempts, rng, schedule[len(rows)])
        errors = validate_planner_v3_example(row["messages"][0]["content"], row["messages"][1]["content"])
        if not errors:
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

    pretty_path = OUT_DIR / "planner_v3_examples_pretty.json"
    pretty_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    report = validate_jsonl(out_path)
    (OUT_DIR / "validation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"output": str(out_path), "pretty": str(pretty_path), "report": str(OUT_DIR / "validation_report.json"), **report}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=500)
    parser.add_argument("--out", default="output/planner_v3_500_examples.jsonl")
    parser.add_argument("--seed", type=int, default=12345)
    args = parser.parse_args()
    result = generate(args.count, args.out, args.seed)
    print(json.dumps({k: result[k] for k in ("rows", "passed", "failed", "output")}, indent=2))
    return 0 if result["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
