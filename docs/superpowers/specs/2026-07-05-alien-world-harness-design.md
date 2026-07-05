# Alien-World Quality Harness — Design

**Branch:** `feature/alien-world-harness`
**Date:** 2026-07-05

## Problem

Writing quality degrades as the story world grows more alien. Three root drivers:

1. **Distribution pull** — the model is trained on human/Earth prose and drifts back to
   familiar tropes, fighting the premise instead of inhabiting it.
2. **Concreteness starvation** — invented alien detail is thinner and more abstract than
   the model's deep well of Earth detail; abstraction = weak prose.
3. **Consistency tax** — more novel rules = more ways to contradict them, so the model
   hedges into vagueness to stay safe. Vague = bad.

Two amplifiers also addressed: **cognitive-budget split** (world-tracking steals craft
budget at write-time) and **reviewer normalization** (human-trained reviewers flag correct
strangeness as error and sand it off).

Central architectural move: **front-load the world into a precomputed concrete bank
(world-bible) and a short authoritative rule set (canon sheet), so write-time is pure
craft** — one pair of artifacts fixes all five problems.

## Trigger: the `non_earth` flag

The PlanningAgent classifies the world during its plan pass. Classification is by
**distributional distance, not geography**: flag `NON-EARTH` (alien) when the world is
off-Earth OR an Earth far enough from present-day common experience (far future, deep
past / Cretaceous, radically altered) that its sensory texture falls outside the training
distribution. Contemporary or familiar-historical Earth = `EARTH` (familiar).

Mechanism: planner emits `<<<WORLD_CLASS: EARTH|NON-EARTH>>>` at the top of its plan
output. When `NON-EARTH`, the same plan pass also breaks the story into **more, smaller
`<<<SECTION N>>>` units** (chunking co-occurs with classification — a single planner call).
The orchestrator parses and strips the tag → `non_earth: bool`, which gates every
component below. **EARTH runs are byte-for-byte today's pipeline.**

## Pipeline order (non_earth)

```
planner.run [Opus]                  classify EARTH|NON-EARTH + chunk smaller
   │  parse + strip <<<WORLD_CLASS>>> → non_earth
   ▼  (non_earth only:)
WorldBuilder.run [Opus]             plan text → world_bible + canon_sheet (one call)
   ▼
planner.revise_with_world_bible     NEW method. Full plan rewrite informed by the
   [Opus]                           bible, so plan events actually exploit the world.
   │                                Returns a full narrative plan (same shape as run(),
   │                                NOT the === diff-ops format). Fixes "plan predates
   ▼                                the bible."
writer.run [Opus]                   plan + world_bible + canon_sheet
   ▼
... Inner / Middle / prose as today, all writer calls Opus, canon everywhere
```

For EARTH the middle two stages are skipped entirely and `planner.run` output feeds the
writer directly, exactly as today.

## Artifact threading (bible vs canon)

| Artifact | Size | Goes to |
|----------|------|---------|
| **canon sheet** | short rule list | writer (all calls) + all six reviewers + strangeness + sensory + planner bible-revision |
| **world-bible** | dense detail bank | write passes only (`run` + `revise`) and the planner bible-revision. **Never** to reviewers — they judge against rules, not the detail bank. |

Both artifacts are produced once and threaded as params (like `plan`/`story`) through
`_run_inner`, `_run_middle`, `_run_prose_pass`. Empty strings when EARTH.

**Derivation vs consumption (signature impact).** `non_earth`, `canon_sheet`, and
`world_bible` are all *produced inside the initial `_run_inner` branch* (that is where the
planner runs, is classified, and — when alien — WorldBuilder + the bible-revision run).
But they are *consumed* by the sibling loop methods. So they must bubble **out**:
- Initial `_run_inner` returns `(plan, story, non_earth, canon_sheet, world_bible)`.
- `run()` holds them and passes them into `_run_middle` and `_run_prose_pass`.
- The middle's *from-middle* `_run_inner` call receives them as params and must **not**
  reclassify or rebuild the world — WorldBuilder and the bible-revision run **once**, in
  the initial inner only.

## Components

### 1. WorldBuilderAgent (new)
- Runs once, immediately after the planner, only when `non_earth`.
- Input: idea, **the plan text** (which already contains the planner's WORLD DEDUCTION
  from any images — WorldBuilder does **not** re-consume raw images, avoiding redundant
  vision cost), world_rules, trope blacklist file.
- Output (single call, two blocks) with hard delimiters for parsing. **Canon sheet is
  emitted FIRST, world-bible SECOND** — canon is short and load-bearing (threaded
  everywhere), so if the response ever hits the token cap, only the bible's tail is at
  risk, never the canon:
  ```
  === CANON SHEET ===
  <short authoritative rule list>
  === WORLD BIBLE ===
  <dense concrete sensory detail bank — textures, smells, sounds, body-sensations, objects>
  ```
  A splitter on those two headers yields `canon_sheet` and `world_bible`.
- **Raise `max_tokens`** for this call above the 8192 default (the bible is intentionally
  dense) so neither block truncates.
- **Model: Opus 4.8** (heavy front-loaded cognition, runs once — cost acceptable).

### 1b. Planner bible-revision pass (new method)
- `PlanningAgent.revise_with_world_bible(plan, world_bible, canon_sheet, target_length)` —
  runs only when `non_earth`, after WorldBuilder, before the first write. `target_length`
  is required: the rewrite must preserve the word-count target and keep per-section budgets
  summing to it, exactly as `run()` does — otherwise the rebudgeted plan blows the length.
- Rewrites the plan so its events, conflicts, and revelations exploit the now-stocked
  world (may refine section breakdown; writer marks the draft to match). Returns a **full
  narrative plan** in the same shape as `run()`. Its prompt must pin two negatives, or the
  writer gets a malformed plan: **do NOT re-emit `<<<WORLD_CLASS>>>`** (classification is
  already done and parsed) and **do NOT use the `===` diff-ops format** used by
  `plan_revision` (this is a narrative plan, not an ops list).
- **Model: Opus 4.8.** (The planner's reviewer-feedback `plan_revision` calls stay on
  their existing tier; only this new bible pass and the initial `run` are Opus.)

### 2. Trope blacklist
- `trope_blacklist.md` at repo root. Injected into WorldBuilder + Writer system prompts
  via `.format()`, mirroring `ai_writing_failure_modes.md`.
- Stub / near-empty initially; content filled later. No new `run()` parameter.
- **Must ship as a committed stub file in the same change as the code that reads it.** The
  readers use `path.read_text()` (like `DEFAULT_FAILURE_MODES_PATH`), which raises
  `FileNotFoundError` if absent. Reads are gated on `non_earth`, so EARTH never touches it.

### 3. Writer model elevation
- `WriterAgent.revise()` gains a `model` param (only `run()` has one today).
- When `non_earth`, the orchestrator passes **Opus 4.8** to ALL writer calls (initial
  write + every revise + prose-pass write). Planner is unchanged (Opus initial only).
- Writer also receives the **canon sheet** in-context on every call — removes write-time
  world-tracking load and the uncertainty that drives hedging.

### 4. StrangenessReviewerAgent (new, inverted)
- Added to the Inner-loop checker fan-out (today consistency ∥ ai_checker; becomes 4-way
  when `non_earth`). Active only when `non_earth`.
- Job is the inverse of the normalizing reviewers: flag where prose is too Earth-tame, the
  world is underexploited, or defamiliarization is missing. Gets the canon sheet.
- Output joins the `plan_revision_2` feedback list. Its findings carry the `[WORLD]` bucket
  tag so the planner referees the push/pull against the normalizing reviewers consistently
  (see Oscillation control below).
- **Model: Sonnet** (inversion judgment is subtler than pattern-matching).

### 5. SensoryQuotaAgent (new)
- Also in the Inner fan-out, `non_earth` only. Gets the canon sheet.
- Bans abstraction hedge-nouns (otherworldly, strange, shimmering, indescribable, alien);
  reports concrete-sensory-detail density per section (like existing tic-density
  reporting) and flags low-density sections.
- Output joins the `plan_revision_2` feedback list; findings carry the `[WORLD]` bucket tag.
- **Model: Sonnet**.

### 6. Reviewer recalibration
- Consistency, ai_checker, peer, editor, marketing, audience accept an optional canon
  sheet. When present:
  - Judge against **this world's** normal, not Earth normal.
  - **Bucket each finding `[CRAFT]` vs `[WORLD]`.**
  - Lower authority on intentional strangeness near canon-elements; keep full authority on
    rhythm, grammar, clarity.
- **PeerWriterAgent (agent 5) is exempt — full authority always** (it is the craft voice).
- **EARTH byte-identical guard (broad scope):** all new prompt text — reviewer canon +
  bucketing, **planner `plan_revision`/`plan_revision_prose` bucket-handling, and the
  writer's trope-blacklist injection** — is injected *conditionally* and appears only when
  `non_earth`. On an EARTH run every one of these prompt strings (six reviewers, planner
  revision methods, writer) must be byte-for-byte identical to today's, so existing
  characterization tests keep passing. The guard is not just the reviewers — it covers the
  planner revision prompts and the writer too.

### Oscillation control
Strangeness/sensory push toward more strangeness; consistency/ai_checker push toward
cutting and normalizing. All findings carry `[CRAFT]` / `[WORLD]` tags, and the planner is
the single referee: `plan_revision` / `plan_revision_prose` prompts are updated to fix
`[CRAFT]` findings and treat `[WORLD]` findings as authorial intent unless they name an
actual contradiction — so a section is not pushed strange one pass and tamed the next.

### Prose pass (`_run_prose_pass`)
- Its reviewers are separate entry points (`consistency.run`, `ai_checker.run_prose`) and
  must receive the canon sheet + bucketing too when `non_earth`.
- `plan_revision_prose` currently **forces every finding into a fix**. Update it to still
  drop `[WORLD]`-tagged strangeness even in force-all mode — otherwise the final polish
  normalizes exactly what the harness protects. `[CRAFT]` findings remain force-fixed.
- Strangeness + sensory do **not** run in the prose pass (Inner-loop only, per design).

### Inner fan-out when `non_earth`
`consistency ∥ ai_checker ∥ strangeness ∥ sensory` → all four feed `plan_revision_2`.
`_run_inner`'s `ThreadPoolExecutor(max_workers=2)` is hardcoded for the two-checker case;
bump it to 4 when `non_earth` so the two new agents run concurrently rather than queuing.

## Surface area

- No CLI or browser-UI changes required: `non_earth` is auto-detected, the blacklist is a
  file. `server.py` may log/surface `non_earth` for visibility only.
- Small footprint: one new file (`trope_blacklist.md`), three new agent classes
  (WorldBuilder, StrangenessReviewer, SensoryQuota), signature + orchestration changes,
  and prompt edits to six existing agents.

## Model tiers (per-component recommendations)

| Component | Model | Rationale |
|-----------|-------|-----------|
| WorldBuilderAgent | Opus 4.8 | Heavy front-loaded cognition, once per run |
| Planner bible-revision pass | Opus 4.8 | Rewrites plan against the bible (non_earth only) |
| StrangenessReviewer | Sonnet | Subtle inversion judgment |
| SensoryQuotaAgent | Sonnet | Density analysis + noun policing |
| Writer (non_earth, all passes) | Opus 4.8 | Craft under alien load |
| Planner (initial run) | Opus 4.8 | Unchanged — classify + first plan |
| Planner (reviewer-feedback plan_revision) | unchanged | Existing tier, no change |
| Reviewer prompt edits | unchanged | No model change |

## Cost (deliberate tradeoff)

A `non_earth` run is materially more expensive than an EARTH run of the same length. It
stacks **three Opus calls before the first word is written** (`planner.run` →
`WorldBuilder` → `planner.revise_with_world_bible`), runs **every** writer pass on Opus
(not just the initial two), and adds two Sonnet reviewers per Inner cycle plus canon-sheet
tokens on many calls. Rough order: 3–5× the token cost of the equivalent EARTH run. This
is accepted on purpose — alien-world quality is the whole point of the feature — but it is
a stated tradeoff, not an accident. EARTH runs are unaffected.

## Testing

Characterize with mocked LLM calls (existing convention — no real API calls):
- Classification tag parsed and stripped; `non_earth` derived correctly for both classes.
- WorldBuilder invoked only when `non_earth`; skipped for FAMILIAR.
- WorldBuilder output split correctly into `world_bible` / `canon_sheet` on the `===` headers.
- Planner bible-revision pass runs only when `non_earth`, on Opus, and its output (full
  plan, not diff-ops) is what reaches the writer.
- Canon sheet threaded into writer + all six reviewers + two new agents; world-bible into
  write passes only, never reviewers.
- Writer receives Opus model id on all passes when `non_earth`.
- Strangeness + Sensory present in the fan-out only when `non_earth`; their outputs reach
  `plan_revision_2`.
- Reviewer prompts include canon sheet and bucketing instructions when present; PeerWriter
  keeps full authority.
- EARTH path unchanged (regression).
