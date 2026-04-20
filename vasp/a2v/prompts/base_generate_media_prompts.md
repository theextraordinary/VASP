You are generating AI media prompt ideas for optional A2V visual assets.

Return valid JSON only:
{{
  "generated_media": [
    {{
      "type": "image",
      "prompt": "safe detailed visual generation prompt",
      "about": "what this generated asset would represent",
      "aim": "show when relevant caption topic is spoken"
    }}
  ]
}}

Rules:
- Generate at most {optional_media_count} prompt ideas.
- Keep every prompt safe for all audiences.
- Make prompts visually useful for vertical short-form video.
- Prefer concrete topics, emotional reactions, scientific/historical objects, and clean editorial visuals.
- Do not request copyrighted characters, logos, celebrities, gore, nudity, or violence.
- These are future placeholders only; do not claim files already exist.

USER INSTRUCTION:
{user_instruction}

TRANSCRIPT:
{transcript}
