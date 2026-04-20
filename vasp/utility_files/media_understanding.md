# Basic Knowledge
1. Each media item is an ELEMENT identified by a unique element_id.
2. Planner must understand media semantically using:
   - type
   - about
   - aim
3. Planner must map media to the exact caption phrases where the meaning matches.
4. Media timing must follow caption meaning, not media duration.
5. Every provided media element must appear exactly once in asset_understanding.
6. If a media item is not useful, mark it as unused instead of ignoring it.
7. Planner must use ALL media intelligently and avoid missing assets.

# MEDIA UNDERSTANDING RULE (VERY IMPORTANT)
Each media item contains:
- type
- about
- aim

Planner MUST use BOTH:
- about = what the media visually contains
- aim = preferred usage behavior

Examples:
- about: "war area"
  → use during war-related captions

- about: "Christian huygens"
  → use when Huygens is mentioned

- about: "Titan planet video"
  → use only around Titan/Saturn captions

- about: "person saying i am free"
  → use around freedom/abolition captions

- about: "war is over slogan"
  → use near war-ending captions only

General Rule:
- Media must be mapped to the MOST semantically relevant caption phrase.
- Do not stretch media across unrelated captions.
- If meaning changes, split segments.

# Caption Track
1. Caption track is the timing backbone of the edit.
2. grouped_caption_map defines ALL valid timings.
3. Planner must use ONLY grouped_caption_map boundaries.
4. Every caption index must appear exactly once across segments.
5. Captions should remain readable at all times.
6. If no visual is active, captions may become center-focused.
7. Caption timing must NEVER be modified.

# Audio
1. Audio is timeline-only and has no screen placement.
2. Main audio drives caption timing.
3. Audio elements must NEVER appear in visual_candidates.
4. main_audio must always be a valid audio element_id.
5. Audio timing must not be altered.

# Image
1. Images represent static semantic concepts.
2. Use images during the exact caption phrase matching the image meaning.
3. Images are best for:
   - people
   - objects
   - locations
   - historical references
4. Images should usually appear for short focused windows.
5. Do not keep images active across unrelated caption groups.

# GIF
1. GIFs are semantic animated visuals.
2. GIFs are NOT filler.
3. GIFs must appear only when caption meaning strongly matches.
4. GIFs should usually be short-lived:
   - reaction
   - emphasis
   - humor
   - emotional punch
5. GIFs must NOT span long unrelated sections.
6. If GIF meaning matches only one phrase, map only to that phrase.
7. GIFs may act as main visuals if strongly relevant.

# Sticker
1. Stickers are lightweight emphasis visuals.
2. Use stickers only around exact matching words/phrases.
3. Stickers must be very short-lived.
4. Stickers should never dominate a segment.
5. Stickers are mainly for:
   - reaction
   - emphasis
   - emotion
   - keyword highlighting

# No Audio Video Clips
1. Videos are primary semantic visuals.
2. Videos should align tightly with transcript meaning.
3. Use videos for:
   - environments
   - actions
   - events
   - motion-heavy concepts
4. Videos should NOT automatically span the whole segment.
5. If transcript meaning changes, shorten or split usage.
6. Video timing must follow caption meaning only.

# Segment Understanding Rules
1. Segments must be SMALL and focused.
2. Prefer 2–4 caption groups per segment.
3. Max 5 caption groups only if idea is continuous.
4. Split segments when:
   - topic changes
   - subject changes
   - action changes
   - event changes
   - historical year changes
   - media concept changes
5. One segment should represent ONE clear visual idea.

# Visual Mapping Rules
1. Every strong concept should get matching media if available.
2. Prefer:
   - exact semantic match
   - contextual match
   - generic match
3. Do NOT assign unrelated visuals.
4. Do NOT skip relevant media.
5. If multiple media match different concepts:
   → split the segment.

# Time Hint Rules
1. time_hint.start/end MUST come from grouped_caption_map only.
2. time_hint must stay inside its segment.
3. supporting_visual:
   - usually 1–4 sec
   - tied to exact phrase window
4. accent:
   - usually ≤2 sec
   - phrase-specific
5. Avoid full-segment visuals unless entire segment discusses the same concept.
