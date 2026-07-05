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

## Components

### 1. WorldBuilderAgent (new)
- Runs once, immediately after the planner, only when `non_earth`.
- Input: idea, plan, world_rules / image-deduction text, trope blacklist file.
- Output (single call, two blocks): **world-bible** (dense concrete sensory detail bank —
  textures, smells, sounds, body-sensations, daily objects) and **canon sheet** (short
  authoritative rule list threaded downstream).
- **Model: Opus 4.8** (heavy front-loaded cognition, runs once — cost acceptable).

### 2. Trope blacklist
- `trope_blacklist.md` at repo root. Injected into WorldBuilder + Writer system prompts
  via `.format()`, mirroring `ai_writing_failure_modes.md`.
- Stub / near-empty initially; content filled later. No new `run()` parameter.

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
- Output joins the `plan_revision_2` feedback list.
- **Model: Sonnet** (inversion judgment is subtler than pattern-matching).

### 5. SensoryQuotaAgent (new)
- Also in the Inner fan-out, `non_earth` only. Gets the canon sheet.
- Bans abstraction hedge-nouns (otherworldly, strange, shimmering, indescribable, alien);
  reports concrete-sensory-detail density per section (like existing tic-density
  reporting) and flags low-density sections.
- Output joins the `plan_revision_2` feedback list.
- **Model: Sonnet**.

### 6. Reviewer recalibration
- Consistency, ai_checker, peer, editor, marketing, audience accept an optional canon
  sheet. When present:
  - Judge against **this world's** normal, not Earth normal.
  - **Bucket each finding `[CRAFT]` vs `[WORLD]`.**
  - Lower authority on intentional strangeness near canon-elements; keep full authority on
    rhythm, grammar, clarity.
- **PeerWriterAgent (agent 5) is exempt — full authority always** (it is the craft voice).
- plan_revision / plan_revision_prose prompts updated: fix `[CRAFT]` findings; treat
  `[WORLD]` findings as authorial intent unless they name an actual contradiction.

### Inner fan-out when `non_earth`
`consistency ∥ ai_checker ∥ strangeness ∥ sensory` → all four feed `plan_revision_2`.

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
| StrangenessReviewer | Sonnet | Subtle inversion judgment |
| SensoryQuotaAgent | Sonnet | Density analysis + noun policing |
| Writer (non_earth, all passes) | Opus 4.8 | Craft under alien load |
| Planner | unchanged | Opus initial, Sonnet revisions |
| Reviewer prompt edits | unchanged | No model change |

## Testing

Characterize with mocked LLM calls (existing convention — no real API calls):
- Classification tag parsed and stripped; `non_earth` derived correctly for both classes.
- WorldBuilder invoked only when `non_earth`; skipped for FAMILIAR.
- Canon sheet threaded into writer + all six reviewers + two new agents.
- Writer receives Opus model id on all passes when `non_earth`.
- Strangeness + Sensory present in the fan-out only when `non_earth`; their outputs reach
  `plan_revision_2`.
- Reviewer prompts include canon sheet and bucketing instructions when present; PeerWriter
  keeps full authority.
- EARTH path unchanged (regression).
