# Final Prose-Cleanup Pass — Design

Date: 2026-07-03
Branch: `feature/prose-cleanup-pass`

## Goal

Add a final loop to the Writing Council pipeline, after the Middle loop, that
emphasizes line-level prose quality. A new prose mode of the AIFailureChecker
hunts prose-specific violations (not structural ones) and reports the top N most
egregious, which the planner and writer then fix.

## Loop Shape

After the Middle loop returns, run one new half-pass on the full story:

```
(4 ∥ 3_prose)  →  1 plan_revision  →  2 revise
```

- `4` = existing `ConsistencyAgent.run(story)` — full story, unchanged.
- `3_prose` = `AIFailureCheckerAgent.run_prose(story, top_n)` — new mode.
- `1` = existing `PlanningAgent.plan_revision(story, plan, [consistency, prose])`.
- `2` = existing `WriterAgent.revise(plan, story, feedback)`.

This is the back half of the existing inner loop — no leading `1 → 2`. Both
checkers run in parallel via `ThreadPoolExecutor`, mirroring the existing inner
and middle patterns.

## New Code

### 1. `AIFailureCheckerAgent.run_prose(story, top_n=5)`

New method + new system prompt (`PROSE_SYSTEM_PROMPT_TEMPLATE`) built from the
same `ai_writing_failure_modes.md` taxonomy, reframed:

- **In scope — prose-specific modes:** Part II Voice/Style in full (AI dialect,
  affective safety net, aphorism cadence, adverb dependency, "particular",
  negation-then-correction, emotional inventory by negation, polysyndeton,
  rhetorical restatement, "it isn't X" etc.) plus line-level Part III items
  (self-congratulatory simile, characterological action simile, described
  insight, credentialed perception, scene as caption, dialogue as exposition).
- **Out of scope — structural modes:** Part I (compressed arc, premature
  resolution, three-act skeleton, symmetrical structure) and any
  plot/pacing/arc-level concern. The Middle loop already owns structure.
- **Output:** the **top N most-egregious** prose violations by severity
  (N = `top_n`, default 5). If fewer than N genuine violations exist, report
  only what is present — do not pad. Each item: the failure-mode name, the exact
  quoted passage, the `<<<SECTION N>>>` number it appears in, and a concrete fix
  direction. No separate priority block — the ranked list *is* the priority.

Returns `{"agent": "AIFailureCheckerAgent", "output": ...}` — same shape as
`run()`, so the planner consumes it identically.

### 2. `WritingCouncil._run_prose_pass(plan, story, target_audience, top_n=5, label="prose")`

New orchestrator method:

1. Run `consistency.run(story)` and `ai_checker.run_prose(story, top_n)` in
   parallel (ThreadPoolExecutor, max_workers=2).
2. `planner.plan_revision(story, plan, [cons_output, prose_output])`.
3. `writer.revise(plan, story, revision_plan)`.
4. Return the revised story.

Logs every step with existing `_log_start` / `_log_end`. Step labels namespaced
under `prose.*` (e.g. `prose.consistency`, `prose.prose_check`,
`prose.plan_revision`, `prose.write`).

Operates on the full story (not section-limited) — the pass exists to catch
prose defects wherever they sit after all prior rewrites.

### 3. Wiring in `run()`

Add a `prose_passes: int = 1` parameter and a `prose_top_n: int = 5` parameter.
After the Middle loop:

```python
for i in range(prose_passes):
    story = self._run_prose_pass(plan, story, target_audience,
                                 top_n=prose_top_n, label=f"prose.{i+1}")
```

Default runs the pass once. Structured so a future "until clean" mode changes
only the loop condition — the per-pass method stays as-is.

## Callers

`run()` gains two optional keyword args with safe defaults, so existing callers
(`server.py`, `consult_the_council.py`, `document_writer.py`) need no change.
Surface the new knobs through the CLI / server only if the user asks; out of
scope for this pass.

## Non-Goals

- "Until clean" iteration (deferred; the loop structure leaves room for it).
- Section-limited prose checking.
- Changing the existing inner/middle loops.
- Exposing the new params in the UI.

## Testing

- Unit: `run_prose` returns the expected dict shape and its prompt names the
  prose taxonomy and the `top_n` cap. Mock `_call_claude`.
- Unit: `_run_prose_pass` calls consistency + prose-check + plan_revision +
  revise in order and returns the writer's story. Mock the agents.
- Integration (manual): run the full pipeline on a short idea, confirm the log
  shows a `prose.*` block after the middle block and the story changes.
