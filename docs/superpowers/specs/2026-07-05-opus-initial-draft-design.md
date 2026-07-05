# Opus 4.8 for the initial plan + write

## Goal

The first planning and writing calls — the initial narrative plan and the
initial full write — should run on Opus 4.8 (`claude-opus-4-8`). All later
plan revisions and writer revisions stay on the current default (Sonnet
`claude-sonnet-4-6`); reviewers stay on Haiku.

## Scope

**Initial draft only.** In `orchestrator._run_inner`, only the `idea is not None`
branch (the Outer initial call) uses Opus:

- `planner.run()` — initial plan
- `writer.run()` — initial write

Untouched (stay Sonnet): `planner.plan_revision`, `writer.revise`, and the
prose-cleanup pass.

## Changes

1. `agents/base_agent.py` — add `INITIAL_DRAFT_MODEL = "claude-opus-4-8"`.
2. `agents/planning_agent.py` — `run()` gains `model: str = None`, forwarded to
   `_call_claude` / `_call_claude_with_image`.
3. `agents/writer_agent.py` — `run()` gains `model: str = None`, forwarded to
   `_call_claude`.
4. `orchestrator.py` — initial branch passes `model=INITIAL_DRAFT_MODEL` to the
   two initial calls; import the constant.

## Design notes

- `BaseAgent._call_claude` and `_call_claude_with_image` already accept a `model`
  override that falls back to `self.model`. `run(model=None)` preserves that
  fallback, so existing callers and tests are unaffected.
- No new model-selection surface beyond the one constant.

## Testing

- Assert initial `planner.run` / `writer.run` issue `messages.create` with
  `model="claude-opus-4-8"`.
- Assert a revision call (`writer.revise` / `plan_revision`) still uses the
  default Sonnet model.
