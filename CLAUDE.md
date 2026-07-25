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
  Inner), Inner (plan → write → parallel checkers → plan_revision → revise). The Inner
  checker fan-out runs Consistency + AIFailure + `EngineReviewerAgent` on every run
  (`max_workers` 3), plus Strangeness + Sensory on `non_earth` (`max_workers` 5).
- `agents/` — one class per agent, all subclassing `agents/base_agent.py:BaseAgent`
  (shared Anthropic client; `_call_claude` and `_call_claude_with_image`).
  System prompts live as module-level string constants in each agent file.
- Model tiers (`agents/base_agent.py`): `DEFAULT_MODEL` (`claude-sonnet-5`) for
  planner/writer, `FEEDBACK_MODEL` (`claude-haiku-4-5`) for reviewers,
  `INITIAL_DRAFT_MODEL` (`claude-opus-5`) for the first plan + first write only.
  These are the Sonnet 5 / Opus 5 family, which runs adaptive thinking on by default when
  `thinking` is omitted; `_call_claude`/`_call_claude_with_image` pass
  `thinking={"type": "disabled"}` to keep behavior controlled and extract the first text
  block defensively (`_first_text`) rather than indexing `content[0]`.
  `PlanningAgent.run`/`WriterAgent.run` take an optional
  `model` override (falls back to `self.model`); the orchestrator passes
  `INITIAL_DRAFT_MODEL` at those two initial call sites, so on an EARTH run all revisions
  stay on Sonnet. (On a `non_earth` run the writer is Opus on every pass — see Alien-world path.)
- `ai_writing_failure_modes.md` — taxonomy the `AIFailureCheckerAgent` reviews against;
  injected into its system prompts.
- Drafts carry `<<<SECTION N>>>` markers so revisions can target sections (diff-style);
  markers are stripped once at the very end of `run()`.
- `document_writer.py` — manuscript-format .docx export under `story_outputs/<title>/`.
- `server.py` + `static/index.html` — Flask UI. Single self-contained HTML file:
  inline CSS (dark/light via CSS custom properties on `body.light`) and inline JS.
- `logs/` — every run writes a full per-step log (`run_<timestamp>.log`).

## Alien-world path (`non_earth`)

For out-of-distribution worlds (off-Earth, or Earth far from present-day experience —
far future, deep past), the pipeline front-loads the world so write-time is pure craft.
Gated entirely on a `non_earth` flag; **an EARTH run is byte-for-byte the base pipeline.**

- `PlanningAgent.run` always emits `<<<WORLD_CLASS: EARTH|NON-EARTH>>>` as the first line
  (classification by distributional distance) and, when NON-EARTH, chunks into more/smaller
  sections. `WritingCouncil._parse_world_class` reads and strips the tag → `non_earth`.
- `WorldBuilderAgent` (Opus, runs once when `non_earth`) turns the plan text into a
  `=== CANON SHEET ===` (short authoritative rules) + `=== WORLD BIBLE ===` (dense sensory
  detail bank) — canon emitted first so truncation only ever costs the bible tail. Reads the
  plan (which already holds any image WORLD DEDUCTION), not raw images. Injects
  `trope_blacklist.md` like `ai_writing_failure_modes.md`.
- `PlanningAgent.revise_with_world_bible` (Opus) rewrites the plan to exploit the world
  before the first write. Returns a full plan (not the `===` diff-ops format).
- `WriterAgent` runs on Opus for **all** passes when `non_earth`, with canon + bible +
  blacklist in context (`_world_block`). Reviewers get the **canon only**, never the bible.
- Two Inner-loop reviewers (Sonnet), added to the checker fan-out only when `non_earth`
  (they raise `max_workers` from the base 3 to 5): `StrangenessReviewerAgent` (flags prose
  too Earth-tame) and `SensoryQuotaAgent` (bans abstraction hedge-nouns, reports per-section
  sensory density). `EngineReviewerAgent` (see Story engine section) also gains a
  weird-with-spine clause on `non_earth`: strangeness that sits on no causal beat is flagged
  `[CRAFT]` (noise), so `plan_revision` fixes it and it survives the prose-pass force-all.
- The six existing reviewers are canon-aware via `agents/world_calibration.py:with_canon`,
  which tags findings `[CRAFT]` vs `[WORLD]` and lowers authority near canon-elements —
  **PeerWriter is exempt** (`lower_authority=False`). `plan_revision`/`plan_revision_prose`
  fix `[CRAFT]`, treat `[WORLD]` as intent (and the prose pass drops `[WORLD]` even under
  force-all). `with_canon(prompt, "")` returns the prompt unchanged — that identity is what
  keeps EARTH byte-for-byte, so existing prompt-string tests are the regression guard.
- Cost: a `non_earth` run is ~3–5× an EARTH run (three Opus calls before the first write +
  Opus on every write) — a deliberate tradeoff. `run()` returns `non_earth`; `/run` surfaces it.

## Story engine, escalation, and constraints

Craft insights from `theory-of-the-good-unique-short-story.md`, applied on **every** run
(EARTH included — these deliberately changed the base prompts):

- `PlanningAgent` emits a `STORY ENGINE` block at the top of the plan: name the *obvious*
  engine the premise reaches for, then the *chosen* one (mood / voice / situation / structure
  / language / constraint / document-form / plot-character), biased toward a non-default power
  source. Each section also carries a "How it escalates" field — the one term (stake, option,
  alliance, want) that beat changes from the previous. `WriterAgent` treats the declared
  engine as binding.
- `EngineReviewerAgent` (`agents/engine_agent.py`, `FEEDBACK_MODEL`) is the Inner-loop reviewer
  for both: engine adherence and causality/escalation (does beat N cause N+1; does exposition
  ascend to rising action). Canon-aware via `with_canon` on `non_earth`.
- `constraint` is an optional hard formal rule threaded like `style` end-to-end (`run` param →
  `PlanningAgent.run` → `WriterAgent.run`/`revise` via a `_constraint_block`, plus server, CLI,
  and browser UI). The planner translates it into checkable rules; the writer obeys it on every
  pass. Countable constraints (exact word count, forbidden words) are verified deterministically
  in `constraints.py:check_constraint` and returned as `constraint_check` (surfaced by `/run`,
  the CLI, and the UI). Non-countable constraints (document-form, second-person) lean on the
  engine reviewer.

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
