# Writing Council — Prompt and Orchestration Review

*2026-07-03 · branch `feature/prompt-improvements`*

This document records a full review of the council's agent prompts and orchestration
pipeline. Part 1 summarizes the prompt changes already applied in this branch. Part 2
proposes orchestration changes that need code, ranked by expected impact on story
quality. Part 3 covers implementation cost and sequencing.

---

## Part 1 — Prompt changes applied (this branch)

These are live in `agents/*.py`. They cost nothing at runtime beyond a few hundred
extra system-prompt tokens per call.

### The unifying change: section-number citations everywhere

The single largest structural weakness in the pipeline was that **no reviewer was told
the draft contains `<<<SECTION N>>>` markers**. The PlanningAgent's `plan_revision`
step must map every piece of feedback onto section numbers to produce its structured
revision plan — and it was doing that mapping by guesswork, because reviewers said
"the middle drags" instead of "section 4 drags." Every reviewer prompt (Consistency,
AI-Failure, Peer Writer, Editor, Marketing, Audience, Character-advocate) now requires
findings to be anchored to section numbers. This makes the feedback → revision-plan →
section-rewrite chain lossless.

### PlanningAgent — initial plan

- **Per-section word budgets that must sum to the target length.** The WriterAgent
  never sees `target_length` — only the plan. Previously nothing carried length
  information into the write step at all. Budgets in the plan close that gap without
  any code change.
- **Plan section numbers = draft section numbers.** The writer is now told to emit
  `<<<SECTION N>>>` markers matching the plan's numbering, so plan, draft, and all
  feedback share one coordinate system.
- **"What it costs" added to the per-section spec.** Turning points without a price
  render flat; requiring the planner to name the cost of each beat attacks the
  compressed-arc and helpful-villain failure modes at the source.
- **CHARACTERS section required** — name, want, fear, one line of voice guidance, arc
  endpoints, plus an opposition with coherent logic that wins at least once. This
  gives the writer differentiated dialogue voices and gives the ConsistencyAgent an
  implicit ground truth to check against.
- **Ending discipline.** The planner must plan the ending the premise demands and
  explicitly license ambiguity/irresolution when the material calls for it. Premature
  resolution is one of the strongest model priors; countering it at plan time is far
  cheaper than revising it out later.

### PlanningAgent — revision plan synthesis

- **One-line instruction constraint made explicit.** `_parse_section_revisions` in
  `writer_agent.py` only matches single lines; a multi-line instruction was being
  silently truncated. The prompt now says so and tells the model to use semicolons.
- **Self-containment rule.** The writer revising a section sees *only* that section
  and the instruction — not the draft, not the feedback. Instructions must therefore
  quote the exact phrases to cut/change and never reference feedback the writer can't
  see.
- **No mixing of structural ops and content revisions in one pass.** `revise()`
  applies MOVE/MERGE *first*, which renumbers sections, so SECTION revisions in the
  same plan would target the wrong prose (see Part 2, item 1 — this is a real code
  bug the prompt now works around).
- **General-notes discouragement.** Anything in GENERAL NOTES triggers the full-story
  rewrite fallback, which risks degrading sections that were working. The prompt now
  says to map feedback to sections whenever possible.
- **Prefer CUT over rework** for stylistic failures, and decide reviewer conflicts
  rather than passing them through.

### WriterAgent — initial write

- **Honor plan word budgets and prose-weight labels** (completes the length-control
  chain started in the planner prompt).
- **Voice differentiation from the plan's CHARACTERS section** — dialogue must be
  distinguishable without tags.
- **Embodiment instruction** ("write from inside a body, not behind a camera") —
  targets the sensory-gap failure mode, the most common weakness the AI checker can
  only fix expensively after the fact.
- **A compact tic budget**: the five highest-frequency AI sentence shapes
  (negation-then-correction, emotion-by-negation, explained metaphor, generalizing
  simile, accumulating polysyndeton) are each capped at once per story. This is
  prevention; the AIFailureCheckerAgent remains the cure.

### WriterAgent — section revision

- **Seam preservation.** The revising model sees isolated sections; it is now told to
  keep each section's opening/closing situation compatible with its unseen neighbors
  and to not introduce plot elements the surrounding story can't know about. This was
  the largest silent-corruption risk in the diff-revision path.
- **Length stability** unless the instruction says otherwise, and keep the given
  section numbers.

### ConsistencyAgent

- **Two-quote evidence standard**: every finding must quote both the establishing
  passage and the contradicting passage. This directly counters the main risk of
  running a "skeptical by default" persona on Haiku — hallucinated findings that then
  drive pointless revision churn. "Finding nothing is an acceptable result."
- **World-rule checking** from what the text itself establishes.
- **Severity ordering + section-number format.**

### AIFailureCheckerAgent

- **Instance vs. pattern distinction with counts.** Most Part-II failure modes are
  legitimate craft at low density; the checker now counts tic occurrences so one
  harmless instance doesn't trigger a revision.
- **PRIORITY top-3 list.** The revision process can only fix a few things per pass;
  the checker now does the triage instead of handing the planner an undifferentiated
  list.
- **Quote-or-it-didn't-happen** rule, matching the ConsistencyAgent standard.

### PeerWriterAgent

- **Capped at 2–3 weakest sections** — depth over coverage.
- **Alternatives must be revision-scale**, executable within the existing structure,
  with the first beat or line sketched so the difference is audible. Premise-level
  objections are allowed once, as a separate note, without withholding section-level
  help.

### EditorAgent

- **Openings and endings always reviewed** — the two places model priors are worst.
- **Strengths as protection**: praised passages should survive revision untouched,
  which gives the revision planner a "do not touch" signal, not just a "fix this" one.
- **Top 3–4 weaknesses only**, all section-anchored.

### MarketingAgent

- **Reframed from marketing-department output to writer-actionable feedback.** Cover
  copy and pitch angles were unactionable by the WriterAgent and diluted the revision
  plan. Every observation must now end in something the writer can change on the page.
- **First-section-as-sample check** — does the opening make the promise this audience
  buys on?

### AudienceAgent

- **Where-and-when precision** ("I started skimming in section 4") plus a
  put-it-down-moment question. Explicitly relieved of explaining *why* — that's the
  critics' job; the reader's job is location and honesty.

### CharacterAgent (not currently wired into the orchestrator)

- Query mode: arc-position grounding (answer from where the character is *now*, not
  their endpoint), body-over-words interiority, brevity ("a compass, not a scene").
- Advocate mode: concrete failure checklist (voice, knowledge, plot-convenience,
  unearned arc beats, character-as-furniture), section citations, and permission to
  report "the draft gets me right" instead of inventing grievances.

---

## Part 2 — Orchestration changes (require code)

Ranked by expected quality impact per unit of implementation effort.

### 1. Fix the structural-op / section-revision ordering bug — *bug fix, do first*

`WriterAgent.revise()` applies MOVE/MERGE ops first, renumbering sections, then
applies SECTION revisions using the *original* numbers from the same revision plan.
Any plan combining both silently revises the wrong sections. The revision-plan prompt
now forbids combining them, but prompts are not guarantees.

**Fix (choose one):**
- Apply section revisions *before* structural ops in `revise()` (both reference the
  same pre-op numbering the planner saw). ~5-line reorder.
- Or: if `structural_ops` is non-empty, drop `section_revisions` for that pass with a
  warning, matching the prompt's contract exactly.

The first option is better — it makes combined plans valid and lets the prompt
restriction be removed later.

### 2. Deterministic word-count guard — *pure Python, zero LLM cost*

Nothing in the pipeline ever measures the draft's length. Parse the numeric target
from `target_length`, `len(story.split())` after each write, and when the draft is
off by more than ±20%, append a synthetic feedback string to the next `plan_revision`
call: `"Draft is 4,210 words against a target of 8,000. Expand sections marked
extended in the plan; do not pad existing scenes."` Length failure is one of the most
common and most mechanical failures — it should never consume reviewer attention.

### 3. Label reviewer feedback by role — *one-line change*

`plan_revision` receives feedback as anonymous `[Reviewer 1] … [Reviewer 4]`. The
planner cannot weight a continuity contradiction (must fix) differently from a
marketing concern (may fix) if it doesn't know who is speaking. Pass
`f"[{agent_name}]\n{feedback}"` instead — the orchestrator already has the names.
Then add one line to `REVISION_PLAN_SYSTEM_PROMPT` establishing precedence:
consistency > AI-failure > editor/peer > audience > marketing.

### 4. Give the ConsistencyAgent the plan — *one-parameter change*

The ConsistencyAgent checks the story against rules it infers from the story itself,
but the authoritative world rules, character sheet, and arc live in the plan (which
the orchestrator holds at every call site). Pass `plan=` into `consistency.run()` and
include it in the user prompt as `AUTHORITATIVE PLAN (world rules and characters)`.
This upgrades it from self-consistency checking to plan-conformance checking, and
makes the new CHARACTERS section do double duty.

### 5. Adjacent-section context in the diff-revision path — *moderate*

The seam-preservation prompt (Part 1) mitigates but cannot eliminate continuity drift
when sections are revised in isolation. In `_build_section_revision_prompt`, include
the last ~150 words of section N−1 and the first ~150 words of section N+1 as clearly
marked read-only context. Cheap in tokens, large reduction in seam errors. Guard the
parse step so read-only context is never merged back.

### 6. Convergence-gated middle loop — *the biggest quality lever, costs money*

The pipeline runs exactly one middle pass, always, regardless of the draft's state.
Two changes:

- `WritingCouncil.run(..., max_middle_passes: int = 1)` and loop `_run_middle`.
- After each inner loop, gate on the checkers: have ConsistencyAgent and
  AIFailureCheckerAgent end their output with a single machine-readable line
  (`VERDICT: CLEAN` / `VERDICT: ISSUES`), regex it, and stop early when both are
  clean two runs in a row or `max_middle_passes` is reached.

Each additional middle pass costs roughly one full pipeline iteration (4 Haiku
reviews + 2 plan_revisions + 2 writes + 2 checks), so expose it as a knob in the
harness UI rather than raising the default. The verdict line also gives you free
telemetry: log it per pass and you can see whether revision is actually converging.

### 7. Model tiering for the moments that matter — *config change*

Current split (Sonnet for plan/write, Haiku for feedback) is the right shape. Two
refinements:

- **Final revise on a stronger model.** The last `writer.revise()` call is the one
  whose output ships. A single Opus/Fable call there is a fixed, small cost for the
  highest-leverage tokens in the run: `self.writer.revise(..., model=PREMIUM_MODEL)`
  (thread a `model` kwarg through `revise` → `_call_claude`, which already accepts it).
- **`plan_revision` should not follow the feedback agents down to Haiku** if further
  cost-cutting is considered. Synthesis-under-conflict is the single most
  judgment-heavy step in the pipeline; it should stay at Sonnet or above.

### 8. Wire in CharacterAgent advocates — *optional, after 1–7*

`a409967` removed CharacterAgent from the loops, but the new CHARACTERS plan section
makes re-wiring cheap: parse character names/profiles from the plan, instantiate one
`CharacterAgent` per major character (cap at 2–3, Haiku), and run `advocate()` in the
middle-loop parallel wave alongside the other four reviewers. Character drift across
revisions is currently checked only generically by the ConsistencyAgent; advocates
give it a dedicated, cheap voice. Skip if token budget is tight — the improved
ConsistencyAgent covers ~70% of this.

---

## Part 3 — Implementation cost and sequencing

| # | Change | Type | LLM cost delta | Effort |
|---|--------|------|----------------|--------|
| — | Prompt changes (Part 1) | prompts | ~0 (system-prompt tokens only) | done |
| 1 | Revision ordering bug | code | 0 | ~5 lines + test |
| 2 | Word-count guard | code | 0 | ~15 lines + test |
| 3 | Labeled feedback + precedence | code + prompt | 0 | ~5 lines |
| 4 | Plan into ConsistencyAgent | code | ~1–2k input tokens/call | ~5 lines |
| 5 | Adjacent-section context | code | ~300 tokens/revision call | ~20 lines + test |
| 6 | Convergence loop | code + prompt | 0 by default; ~1 pipeline-pass per extra iteration | ~40 lines |
| 7 | Model tiering | code | one premium call/run | ~10 lines |
| 8 | Character advocates | code | 2–3 Haiku calls/middle pass | ~40 lines |

**Suggested order:** 1 → 3 → 2 → 4 (one small PR: all zero/near-zero cost, all
correctness) then 5 → 7 (quality PR), then 6 (knob + UI field in the prompt
harness), then 8 if desired.

**Validation:** the cheapest meaningful test is A/B on the same idea/seed inputs:
run the pipeline before and after each PR with an identical prompt, hand both
manuscripts to a fresh AIFailureCheckerAgent pass, and compare finding counts and
the priority lists. The `logs/run_*.log` files already capture every intermediate
artifact needed for this comparison.
