# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

Writing Council: a multi-agent fiction pipeline. A council of Claude-backed agents
plans, writes, reviews, and revises a short story, then exports it as a manuscript
.docx. Two entry points: a CLI script and a Flask browser UI.

## Running

```bash
python consult_the_council.py   # CLI run; story config is inline at the top of the file
python server.py                # browser UI at http://127.0.0.1:5000 (or launch.bat)
python -m pytest tests -q      # test suite (server tests need flask installed)
```

Requires `ANTHROPIC_API_KEY` in `.env` at the repo root. Runs are long (minutes) and
billed — never start a real council run just to verify code; the tests mock the council.

## Architecture

- `orchestrator.py` — `WritingCouncil.run()` drives three nested loops:
  Outer (Inner → Middle → prose-cleanup passes), Middle (4 reviewers in parallel →
  Inner), Inner (plan → write → parallel checkers → plan_revision → revise).
- `agents/` — one class per agent, all subclassing `agents/base_agent.py:BaseAgent`
  (shared Anthropic client; `_call_claude` and `_call_claude_with_image`).
  System prompts live as module-level string constants in each agent file.
- Model tiers (`agents/base_agent.py`): `DEFAULT_MODEL` (Sonnet) for planner/writer,
  `FEEDBACK_MODEL` (Haiku) for reviewers, `INITIAL_DRAFT_MODEL` (Opus 4.8) for the
  first plan + first write only. `PlanningAgent.run`/`WriterAgent.run` take an optional
  `model` override (falls back to `self.model`); the orchestrator passes
  `INITIAL_DRAFT_MODEL` at those two initial call sites, so all revisions stay on Sonnet.
- `ai_writing_failure_modes.md` — taxonomy the `AIFailureCheckerAgent` reviews against;
  injected into its system prompts.
- Drafts carry `<<<SECTION N>>>` markers so revisions can target sections (diff-style);
  markers are stripped once at the very end of `run()`.
- `document_writer.py` — manuscript-format .docx export under `story_outputs/<title>/`.
- `server.py` + `static/index.html` — Flask UI. Single self-contained HTML file:
  inline CSS (dark/light via CSS custom properties on `body.light`) and inline JS.
- `logs/` — every run writes a full per-step log (`run_<timestamp>.log`).

## Images

The planner can deduce world rules from reference images (WORLD DEDUCTION section).
The image parameter is a path/URL string **or a list of them**, accepted end-to-end:
`WritingCouncil.run(image=...)` → `PlanningAgent.run(image=...)` →
`BaseAgent._call_claude_with_image(images=...)` (one image block per entry).

Browser flow: photos are held client-side (`uploadedPhotos` array) with a thumbnail
strip — per-photo X button and remove-all; removed photos are excluded from the payload.
`POST /run` accepts `image_files: [{data: <dataURI>, filename}]`, writes one temp file
per photo, and deletes them all after the run. Legacy single `image_file`/`image_url`
fields still work.

## Conventions

- Tests characterize behavior with mocked LLM calls (`unittest.mock.patch`); server
  tests patch `server.WritingCouncil`. No real API calls in tests.
- Prompt edits are the product: writer/checker/planner system prompts encode hard-won
  style rules (em-dash rationing, tic-density reporting, forced prose-fix passes).
  Change wording deliberately and keep the escaped-newline string style.
- Branch model: `feature/*` branches; PRs have historically targeted the branch they
  build on (check `origin/HEAD` before assuming `master`).
