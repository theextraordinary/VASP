# Planner Output Contract (Week 1)

Planner must return plain text only, starting with `EDIT PLAN`, and containing these exact headings in order:

1. `Global Style:`
2. `Audio Decision:`
3. `Caption Style:`
4. `Visual Style:`
5. `Background Style:`
6. `Segmentation Rule:`
7. `Segment 1`
8. `Time:`
9. `Purpose:`
10. `Elements Used:`
11. `Caption Decision:`
12. `Visual Decision:`
13. `Animation Decision:`
14. `Placement Decision:`
15. `Timing Events:`
16. `Transition Out:`
17. `Engagement Note:`

Hard rules:

- No JSON, no markdown code fences, no prose before `EDIT PLAN`.
- Segment blocks must use the same heading names as above.
- Element ids referenced in `Elements Used:` must be valid ids present in input compact elements.
- Caption grouping directives must explicitly include:
  - adaptive grouping (1 to 5 words),
  - split on sentence boundary (`.!?`),
  - split on long pause,
  - split when next token starts uppercase.
