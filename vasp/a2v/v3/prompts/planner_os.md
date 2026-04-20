Planner output schema:

{
  "planner_version": "v3_media_text_matching",
  "matches": [
    {
      "match_id": "match_001",
      "text": "exact transcript text span",
      "media_id": "media_5",
      "match_strength": "high | medium | low",
      "match_style": "literal | emotional | humorous | contextual | reaction | cinematic | transition | fallback",
      "match_reason": "short reason",
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
- USER INSTRUCTION has priority over default editorial preferences such as tone, humor, emotional matching, what to emphasize, what to avoid, and how selective the matching should be.
- USER INSTRUCTION must still produce this exact JSON schema and cannot allow invented media ids, invented transcript text, overlapping match spans, markdown, timestamps, layout, or audio/caption media matches.
- Every mandatory visual media id must appear at least once in matches.
- No text span should overlap with another text span assigned to a different media.
- Each match.text must be copied exactly from transcript.
- No invented text.
- No invented media ids.
- Prefer emotional/reaction payoff, strong motion/action visuals, exact object/person matches, then contextual support.
- Avoid date-only, connector-only, or filler-only spans unless a mandatory media needs fallback coverage.
- If a weak filler/date span is used as fallback, use match_strength="low" and match_style="fallback".
- If all mandatory media are not used, do not reuse another mandatory media for a second match until every mandatory media has appeared once.
- Make segments only when it makees sense do not forcibly match the media with any segment.
