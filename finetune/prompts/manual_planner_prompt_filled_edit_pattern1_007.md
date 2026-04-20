# Manual Planner Prompt (Filled Example: edit_pattern1_007)

You are a professional short-form video editor. Using the provided inputs, generate a structured language edit plan (not JSON) for a vertical video.

## Task
Create an engaging, readable, and time-synced edit plan from the given transcript, captions mapping, images, and audio.

## Core Editing Constraints
- Output video target: `9:16` (vertical), intended final render format: `mp4`.
- Treat screen as a safe grid: no element should go outside the visible frame.
- Keep the edit smooth, clear, and synchronized with speech.
- Prefer clean composition over clutter.
- Transition policy: use light transitions only.

## Elements and Their Properties
Inputs are provided as elements of type: `image`, `audio`, `caption`.
Each planned element/action should be defined using these properties:
1. `id`
2. `type`
3. `position`
4. `size`
5. `time`
6. `data`
7. `animation`

## Timing and Sync Rules
- Audio is the timeline backbone.
- Captions must remain synced with provided word timings.
- You may group words into caption groups for readability, but groups must still respect timing:
  - Group start = first word start in that group.
  - Group end = next group start (or last word end for final group).
- Do not create caption timings that drift from mapped audio speech.

## Caption Readability Rules (Hard)
- Max 2 lines per caption block.
- Max 5 words per caption group.
- Caption safe zone: y=1450 to 1780 for 1080x1920.
- No overlapping captions unless intentionally layered.

## Visual Fallback Rule
- If no relevant image matches current spoken content, keep caption-focused; do not force visuals.

## Input

### Transcript
"Ill take this pain, yeah, I cant, I cant But what about love? What about our promises? What about love? You take it all and leave me nothing What about love? What about our studio? What about love? You come on weeks, know I am all in What about love?"

### Caption Word Timing Map
[{"text": "I'll", "start": 0.0, "end": 0.12}, {"text": "take", "start": 0.2, "end": 0.46}, {"text": "this", "start": 0.521, "end": 0.621}, {"text": "pain,", "start": 0.801, "end": 1.041}, {"text": "yeah,", "start": 1.101, "end": 1.341}, {"text": "I", "start": 1.561, "end": 1.641}, {"text": "can't,", "start": 1.721, "end": 2.022}, {"text": "I", "start": 2.042, "end": 2.092}, {"text": "can't", "start": 2.402, "end": 2.602}, {"text": "But", "start": 2.642, "end": 2.942}, {"text": "what", "start": 3.043, "end": 3.323}, {"text": "about", "start": 3.343, "end": 3.763}, {"text": "love?", "start": 4.924, "end": 5.545}, {"text": "What", "start": 5.605, "end": 6.125}, {"text": "about", "start": 6.285, "end": 6.826}, {"text": "our", "start": 6.846, "end": 6.966}, {"text": "promises?", "start": 6.986, "end": 7.306}, {"text": "What", "start": 7.866, "end": 8.007}, {"text": "about", "start": 8.127, "end": 8.547}, {"text": "love?", "start": 8.647, "end": 8.967}, {"text": "You", "start": 9.087, "end": 10.168}, {"text": "take", "start": 10.268, "end": 10.509}, {"text": "it", "start": 10.529, "end": 10.749}, {"text": "all", "start": 10.769, "end": 10.989}, {"text": "and", "start": 11.489, "end": 11.549}, {"text": "leave", "start": 11.589, "end": 11.77}, {"text": "me", "start": 11.81, "end": 11.99}, {"text": "nothing", "start": 12.05, "end": 12.69}, {"text": "What", "start": 13.091, "end": 13.351}, {"text": "about", "start": 13.511, "end": 14.332}, {"text": "love?", "start": 14.532, "end": 15.032}, {"text": "What", "start": 15.052, "end": 15.152}, {"text": "about", "start": 15.272, "end": 15.693}, {"text": "our", "start": 15.853, "end": 16.013}, {"text": "studio?", "start": 16.033, "end": 16.994}, {"text": "What", "start": 17.474, "end": 17.614}, {"text": "about", "start": 17.714, "end": 18.155}, {"text": "love?", "start": 18.195, "end": 18.515}, {"text": "You", "start": 18.535, "end": 18.715}, {"text": "come", "start": 18.815, "end": 19.936}, {"text": "on", "start": 20.096, "end": 20.216}, {"text": "weeks,", "start": 20.356, "end": 20.677}, {"text": "know", "start": 20.697, "end": 21.297}, {"text": "I", "start": 21.477, "end": 21.527}, {"text": "am", "start": 21.517, "end": 21.617}, {"text": "all", "start": 21.758, "end": 21.898}, {"text": "in", "start": 22.118, "end": 22.378}, {"text": "What", "start": 22.418, "end": 22.598}, {"text": "about", "start": 22.638, "end": 22.979}, {"text": "love?", "start": 23.059, "end": 23.239}]

### Image Data
{'assets/inputs/images/990890291_afc72be141.jpg': '{about: A man is doing a wheelie on a mountain bike.; aim: Cover frame horizontally when mentioned, then fade out as next topic starts.; timing: 0.000-7.813}', 'assets/inputs/images/947969010_f1ea572e89.jpg': '{about: The dog is climbing out of the water with a stick.; aim: Cover frame horizontally when mentioned, then fade out as next topic starts.; timing: 7.813-15.626}', 'assets/inputs/images/873633312_a756d8b381.jpg': '{about: A child wearing a white, red, and black life jacket was bounced into the air by something big and yellow.; aim: Cover frame horizontally when mentioned, then fade out as next topic starts.; timing: 15.626-23.439}'}

### Audio Data
{'audio_1' (assets/inputs/song_0063.m4a): 0.000-23.439}

### Allowed Animations
[fade in/out, jump in/out, roll in/out]

## Output Format (Strict)
Return a table of planned elements/actions with columns:
- id
- type
- position
- size
- time
- data
- animation
- purpose

Also include a short section before the table:
- Global Style
- Caption Strategy
- Image Strategy
- Sync Strategy
- Transition Policy

Do not return JSON or code. Return plain text only.
