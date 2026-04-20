You are generating safe media search queries for a short-form A2V edit.

Return valid JSON only:
{{
  "queries": [
    {{
      "query": "short specific search query",
      "reason": "why this query may find useful visuals"
    }}
  ]
}}

Rules:
- Generate exactly {query_count} queries.
- First identify any famous/known person names in the transcript.
- If the transcript contains a famous/known person name, at least one query must be exactly that person's name or that person's name plus one visual keyword.
- Then identify any animal, place, named object, invention, product, event, or particular thing in the transcript.
- You must generate direct queries for those specific entities when they are safe and visually searchable.
- Queries must be safe for all audiences.
- Keep each query short: 2 to 6 words.
- Prefer concrete nouns, people, places, objects, reactions, and visual concepts.
- Make queries diverse; do not repeat the same visual idea.
- Include reaction/comedy-style queries only when the transcript has a surprise, joke, failure, celebration, or emotional beat.
- Do not ask for copyrighted movie/TV clips.
- Do not include NSFW, gore, weapons, or violent wording.

USER INSTRUCTION:
{user_instruction}

TRANSCRIPT:
{transcript}
