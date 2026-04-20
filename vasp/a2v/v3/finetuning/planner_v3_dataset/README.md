# Planner V3 Media-Transcript Matching Dataset

This directory generates clean synthetic fine-tuning examples for the VASP A2V v3 planner.

The dataset teaches the planner to:

- Match visual media IDs to exact transcript text spans.
- Think like a short-form editor, not just a semantic retriever.
- Use every mandatory media item at least once.
- Use optional media only when strongly relevant.
- Prefer short exact spans instead of long full sentences.
- Split long narration when different media match different phrases.
- Extract strong visual beats such as actions, reveals, punchlines, and emotional turns.
- Prefer emotional/reaction payoff, strong motion, exact object/person matches, contextual support, then fallback.
- Use meme/reaction media for surprise, failure, celebration, awkwardness, and punchline moments.
- Use `match_style` to distinguish `literal`, `emotional`, `humorous`, `contextual`, `reaction`, `cinematic`, `transition`, and `fallback` matches.
- Prefer `aim` over `about`.
- Leave generic filler phrases unmatched.
- Avoid weak date-only or connector-only matches unless required as low-strength fallback.
- Avoid timestamps, layout fields, invented media IDs, and markdown.

No API calls, internet access, or real media files are required. All media entries are fake descriptions.

## Generate

From repo root:

```bash
python vasp/a2v/finetuning/planner_v3_dataset/generate_planner_v3_dataset.py --count 500 --out output/planner_v3_500_examples.jsonl
```

The generator is deterministic by default and keeps creating/fixing examples until all requested rows pass validation.

The generated examples include semantic-vs-emotional conflicts, split-beat sentences, mandatory fallback cases, and reaction/meme examples so Planner V3 learns what looks best on screen.

## Generate Grounded Examples

For the cleaner grounded dataset, use the transcript and media inventory files:

- `output/transcripts.md`
- `output/media_skill.md`

Run:

```bash
python vasp/a2v/finetuning/planner_v3_dataset/generate_grounded_planner_v3_dataset.py --count 500 --out output/planner_v3_500_examples.jsonl
```

This generator builds prompts using the same Planner V3 input/output schema, selects contiguous transcript snippets from `transcripts.md`, and maps mandatory visual media from `media_skill.md` only when there is a clear transcript anchor. The gold matches use exact transcript substrings and avoid clipped phrases, timestamps, layouts, and invented media IDs.

## Validate

```bash
python vasp/a2v/finetuning/planner_v3_dataset/validate_planner_v3_dataset.py --input vasp/a2v/finetuning/planner_v3_dataset/output/planner_v3_500_examples.jsonl
```

## Outputs

- `output/planner_v3_500_examples.jsonl`: fine-tuning JSONL.
- `output/planner_v3_examples_pretty.json`: readable pretty JSON copy.
- `output/validation_report.json`: validation results.
- `output/planner_v3_5_sample_examples_round8.txt`: five readable examples from the latest regenerated set.
- `output/planner_v3_grounded_5_examples.txt`: five readable examples from the grounded generator.

## Fine-Tuning Use

Each row uses chat format:

```json
{
  "messages": [
    {"role": "user", "content": "<full planner input prompt>"},
    {"role": "assistant", "content": "<valid JSON planner output>"}
  ]
}
```

Use the JSONL directly as supervised fine-tuning data for Planner V3.

## Failure Modes Prevented

- Mandatory media omitted from output.
- `mandatory_media` boolean set incorrectly.
- Matched text not copied exactly from transcript.
- Overlapping text spans assigned to different media.
- Audio/caption IDs used as visual media.
- Generic filler text matched to unrelated media.
- Date-only or vague connector spans treated as high-confidence matches.
- Optional media used weakly.
- Reaction and meme media ignored when they are editorially stronger than literal visuals.
- Too much fallback behavior or too little emotional/humorous/reaction matching.
- Layout/timing fields leaking into planner output.
