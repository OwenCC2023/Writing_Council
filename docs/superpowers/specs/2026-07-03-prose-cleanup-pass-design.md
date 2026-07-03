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
- `1` = new `PlanningAgent.plan_revision_prose(story, plan, prose, consistency)`.
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
- **Framing — surviving-residue polish, not a fresh sweep.** This runs after the
  inner and middle loops have already applied a full-taxonomy pass. The prompt
  states that: the story has been revised repeatedly, so the goal is to catch the
  **line-level prose defects that survived** prior passes — residue, not a
  first-pass audit. Prefer defects a reader would trip over in the sentence, not
  patterns already smoothed.
- **Output:** the **top N most-egregious** prose violations by severity
  (N = `top_n`, default 5). If fewer than N genuine violations exist, report
  only what is present — do not pad. Each item: the failure-mode name, the exact
  quoted passage, the `<<<SECTION N>>>` number it appears in (load-bearing — the
  planner maps fixes by this number; an item without a section number cannot be
  targeted), and a concrete fix direction. No separate priority block — the
  ranked list *is* the priority.
- **Cite numbered sections only.** Every violation must sit inside a numbered
  `<<<SECTION N>>>`. Defects in preamble text before section 1 are not fixable by
  the writer (`revise` skips section 0) — the reviewer must skip them rather than
  report an untargetable finding.

Returns `{"agent": "AIFailureCheckerAgent", "output": ...}` — same shape as
`run()`, so the planner consumes it identically.

### 2. `PlanningAgent.plan_revision_prose(story, plan, prose_feedback, consistency_feedback)`

New planner method + new system prompt (`PROSE_REVISION_PLAN_SYSTEM_PROMPT`),
used **only** by the prose pass. Same three-block output format as
`plan_revision` (STRUCTURAL OPERATIONS / SECTION REVISIONS / GENERAL NOTES), so
`writer.revise` consumes it unchanged. The difference is the instruction:

- **Force-all-N.** Every prose violation in the prose reviewer's ranked list
  MUST be addressed by a `SECTION N:` revision instruction — the planner may not
  omit or downrank any of them (this overrides the "omit marginal changes"
  guidance in the generic `plan_revision`). The ranked list is a fix list, not a
  candidate pool.
- **One line per section — merge, never split.** `writer._parse_section_revisions`
  keys instructions by section number in a dict, so a second `SECTION N:` line for
  the same N silently overwrites the first. When multiple violations share a
  section, the planner MUST combine them into a **single** `SECTION N:` line,
  semicolon-separating the individual fixes. Emitting two lines for the same
  section drops a forced fix. This is the load-bearing constraint for force-all-N.
- **STRUCTURAL OPERATIONS = NONE, GENERAL NOTES = NONE.** Every prose fix maps to
  a numbered section, so all output goes in SECTION REVISIONS. Forcing the other
  two blocks to NONE (a) keeps every forced fix on the targeted path and (b)
  avoids `writer`'s full-story fallback rewrite (triggered by any GENERAL NOTES
  content), which would degrade already-polished sections.
- **Consistency feedback is folded in as text edits only.** Continuity fixes that
  are section-content changes (a name slip, a timeline typo) attach as supporting
  clauses on the relevant `SECTION N:` line and never displace a prose item.
  Because STRUCTURAL OPERATIONS is pinned to NONE, any consistency finding that
  would need a MOVE/MERGE (reordering) is **intentionally dropped this pass** —
  structure is the Middle loop's responsibility; the prose pass only polishes
  line-level text.
- Same quoting/self-containment rules as `plan_revision`: quote the exact phrase
  to cut/change, keep each instruction to one line, prefer CUT over rework for
  stylistic tics.

The generic `plan_revision` is left untouched (inner and middle loops keep
their funnel behavior).

### 3. `WritingCouncil._run_prose_pass(plan, story, target_audience, top_n=5, label="prose")`

New orchestrator method:

1. Run `consistency.run(story)` and `ai_checker.run_prose(story, top_n)` in
   parallel (ThreadPoolExecutor, max_workers=2).
2. `planner.plan_revision_prose(story, plan, prose_output, cons_output)`.
3. `writer.revise(plan, story, revision_plan)`.
4. Return the revised story.

Logs every step with existing `_log_start` / `_log_end`. Step labels namespaced
under `prose.*` (e.g. `prose.consistency`, `prose.prose_check`,
`prose.plan_revision`, `prose.write`).

Operates on the full story (not section-limited) — the pass exists to catch
prose defects wherever they sit after all prior rewrites.

### 4. Wiring in `run()`

Add a `prose_passes: int = 1` parameter and a `prose_top_n: int = 5` parameter.
After the Middle loop:

```python
for i in range(prose_passes):
    story = self._run_prose_pass(plan, story, target_audience,
                                 top_n=prose_top_n, label=f"prose.{i+1}")
story = self._strip_section_markers(story)   # final step — see below
return {"story": story, "log": list(self._log)}
```

Default runs the pass once. Structured so a future "until clean" mode changes
only the loop condition — the per-pass method stays as-is.

### 5. Move section-marker stripping to the end of the pipeline

`<<<SECTION N>>>` markers are currently stripped inside `document_writer.py`
(`save_as_manuscript`, the `re.sub(r'<<<SECTION\s+\d+>>>\n?', '', story)` line).
The prose pass needs the markers intact (both the prose reviewer's section
citations and `writer.revise`'s section targeting depend on them), so stripping
must happen **after** all prose passes complete, as the final step of `run()`.

- Add `WritingCouncil._strip_section_markers(story)` — the same regex — and call
  it once at the end of `run()`, after the prose loop.
- Remove the `re.sub` strip line from `document_writer.save_as_manuscript`.
  Safe because all three producers (`server.py` → `/save`, `consult_the_council.py`,
  `prompt_harness.py`) receive the story from `council.run()`, which now returns
  it marker-free. `document_writer` receives no marked-up story from any path.
- **Pre-implementation check:** `/run` now hands the frontend a marker-free story
  (previously markers survived to the client and were stripped only at `/save`).
  Grep `static/` for `<<<SECTION` / `SECTION` before implementing — if the UI
  parses markers for display, adjust it. Expected low risk (frontend shows raw
  text).

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

- Unit: `run_prose` returns the expected dict shape; its prompt names the prose
  taxonomy, the surviving-residue framing, and the `top_n` cap. Mock `_call_claude`.
- Unit: `plan_revision_prose` returns the three-block shape and its prompt
  carries the force-all-N instruction, the merge-same-section rule, and the
  STRUCTURAL/GENERAL = NONE pins. Mock `_call_claude`.
- Unit: two prose violations in the same section survive as one `SECTION N:`
  line through `writer._parse_section_revisions` (guards the overwrite bug) —
  feed a crafted revision plan, assert both fixes present.
- Unit: `_run_prose_pass` calls consistency + prose-check + plan_revision_prose +
  revise in order and returns the writer's story. Mock the agents.
- Unit: `_strip_section_markers` removes `<<<SECTION N>>>` lines; `run()` returns
  a marker-free story.
- Regression: `save_as_manuscript` still produces clean output when given a
  marker-free story (markers no longer its responsibility).
- Integration (manual): run the full pipeline on a short idea, confirm the log
  shows a `prose.*` block after the middle block and the story changes.
