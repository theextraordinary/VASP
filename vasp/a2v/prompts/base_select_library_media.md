You are selecting optional media for a short-form A2V edit.

Return valid JSON only:
{{
  "selected_media": [
    {{
      "media_name": "exact filename from library",
      "reason": "why this helps the transcript",
      "about": "short accurate description"
    }}
  ]
}}

Rules:
- Select at most {optional_media_count} media items.
- Only select media that strongly supports the transcript, emotion, joke, or visual topic.
- Mandatory user-provided media will be prioritized elsewhere. These are optional helpers only.
- Do not invent filenames.
- Prefer clear visual beats over generic decoration.

USER INSTRUCTION:
{user_instruction}

TRANSCRIPT:
{transcript}

MEDIA LIBRARY:
{media_library}
