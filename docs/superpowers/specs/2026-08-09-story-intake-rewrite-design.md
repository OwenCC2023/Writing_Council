# Story Intake & Rewrite — Design

Date: 2026-08-09
Branch: `feature/story-intake-rewrite`

## Goal

Upload an existing story and have the council rewrite it. An intake agent digests the
original — world, characters, plot, storyline, setting, intent, genre, length — merges it
with anything the user supplies, and hands the result to `PlanningAgent`, which classifies
the world and trips `non_earth` as it does today.

Two rewrite modes:

- **reimagine** — the council writes a new story on the original's bones. Original prose
  never enters writer context.
- **revise** — the original text is seeded as the initial draft and run through the
  review/revise loops. Author sentences survive where reviewers don't object.

An empty `source_story` leaves the existing pipeline byte-for-byte unchanged.

## Components

### `story_intake.py` (new, no LLM)

`load_story_text(path) -> str`

- `.txt` / `.md`: read as UTF-8.
- `.docx`: python-docx (new dependency); paragraphs joined with a blank line between.
- Raises on unsupported extension, unreadable file, or empty text.
- Raises above 110,000 words, reporting the count (see Error handling).

Manuscript front matter is **not** stripped here. A `.docx` produced by `document_writer`
opens with a byline, a contact block, a word count, and a title page; stripping those
deterministically is brittle across sources. `load_story_text` returns them verbatim and
the intake prompt is responsible for ignoring them (see below).

### `agents/intake_agent.py` (new) — `IntakeAgent(BaseAgent)`

Model: `DEFAULT_MODEL` (Sonnet 5). One call; the whole story goes in the user prompt.
`rewrite_notes` is included so extraction is directed (e.g. "original 8k, target 3k"
changes what the brief preserves). Word count is computed in Python and injected — never
guessed by the model.

The system prompt explicitly instructs the agent to ignore manuscript front matter — an
author byline, contact block, word-count line, title page, or running header — and to
begin from the first line of narrative.

Output is a fixed-shape block:

```
=== STORY BRIEF ===
TITLE:               <the original's own title, or blank if it has none>
WORLD_CLASS_GUESS: EARTH|NON-EARTH — <one line why>
GENRE:
SETTING:
WORLD RULES:         <deviations from our world; feeds world_rules>
CHARACTERS:          <name — want, wound, function>
PLOT:                <beat list, causal>
STORYLINE/STRUCTURE: <how it is told: POV, tense, frame, order>
INTENT:              <what the story is trying to do to the reader>
LENGTH: <n> words
SYNOPSIS:            <premise paragraph; feeds idea>
```

`WORLD_CLASS_GUESS` is advisory only. `PlanningAgent`'s `<<<WORLD_CLASS: ...>>>` tag
remains the sole authority that `_parse_world_class` reads, so `non_earth` keeps one
source of truth and `rewrite_notes` like "move it to a gas giant" flows through naturally.

### `sectionizer.py` (new) — revise mode only

Runtime model: `FEEDBACK_MODEL` (Haiku 4.5). A single call returns *anchors* (the first ~8
words of each section start). Python locates each anchor in the original and inserts
`<<<SECTION N>>>`. The model never re-emits prose, so the text cannot mutate and no tokens
are spent echoing the story.

Marker contract, which must match what `WriterAgent` already expects
(`agents/writer_agent.py:103`, `_split_sections` at :238):

- Exactly `<<<SECTION N>>>` on its own line, N starting at 1 and incrementing by 1.
- Plan section N becomes draft section N — the sectionizer is given the plan and asked for
  one anchor per plan section, in order.
- Anchors must be unique. An anchor matching zero or more than one location in the text is
  rejected (`_split_sections` warns on duplicate section numbers); that section falls back.
- The first anchor also skips manuscript front matter: everything before anchor 1 is
  dropped, which is how a `document_writer` .docx round-trip loses its title page.

Fallback when anchors don't all match: split on scene-break glyphs (`***`, `---`, `#`),
then on blank lines, to reach the plan's section count. If the count still differs, log it
and proceed — `plan_revision` reads section numbers off the draft and works with whatever
markers exist.

### `agents/planning_agent.py` (changed)

`PlanningAgent.run` gains optional `source_story: str = ""` and `plan_existing: bool = False`.
When set, a prompt addendum instructs it to plan the story that exists rather than invent
one. Output format is unchanged: `<<<WORLD_CLASS>>>` tag, `STORY ENGINE` block, per-section
"How it escalates". Everything downstream is untouched.

### `orchestrator.py` (changed)

`WritingCouncil.run` gains:

- `source_story: str = ""` — raw text of the uploaded story.
- `rewrite_mode: str = ""` — `"reimagine"` or `"revise"`; ignored when `source_story` is
  empty. Empty with a `source_story` present defaults to `"reimagine"`; any other value
  raises `ValueError` before an API call.
- `rewrite_notes: str = ""` — free-text rewrite directive.

Returns `intake_brief` and `rewrite_mode` alongside the existing keys.

### `_run_inner` gains a seeded branch (changed)

Today `_run_inner` forks on `idea is not None`: the initial branch plans and writes, the
`else` branch assumes `middle_feedbacks` and runs `plan_revision` + `writer.revise`. Revise
mode needs a third shape — plan and story supplied, no first write.

- New parameter `seeded: bool = False`. When true (plan and story given,
  `middle_feedbacks is None`), both agent calls are skipped and execution starts at the
  checker fan-out.
- `orchestrator.py:280` reads `write_result.get("revised_sections")` after both branches;
  `write_result` does not exist on the seeded path. Initialize `revised_sections = None`
  (and therefore `check_text = story`, `check_label = "full story"`) before the fork so
  every branch is safe.
- The initial branch opens with `non_earth, canon_sheet, world_bible = False, "", ""` — it
  owns classification and WorldBuilder. The seeded branch must not; those values are passed
  in and used as given.

### `_run_revise_setup` (new private method on `WritingCouncil`)

Everything revise mode needs before the loops, kept out of `_run_inner`:

`_run_revise_setup(brief, source_story, ...) -> (plan, marked_story, non_earth, canon_sheet, world_bible, planning_details)`

1. `PlanningAgent.run(plan_existing=True, source_story=..., model=INITIAL_DRAFT_MODEL, ...)`.
2. `_parse_world_class` on the result → `non_earth`, tag stripped.
3. If `non_earth`: `WorldBuilderAgent.run(idea=<brief SYNOPSIS>, plan=plan, world_rules=...)`
   → canon and bible. `revise_with_world_bible` is **not** called (see below).
4. `sectionize(plan, source_story)` → the draft with `<<<SECTION N>>>` markers.

`run()` then calls `_run_inner(seeded=True, plan=..., story=..., non_earth=..., ...)` and
the outer loop proceeds exactly as it does today.

## Data flow

```
upload -> load_story_text -> IntakeAgent -> brief
       -> merge: a non-empty user field wins; otherwise the brief fills it
          idea          <- SYNOPSIS
          world_rules   <- WORLD RULES
          framework     <- STORYLINE/STRUCTURE
          target_length <- LENGTH
          title         <- brief TITLE, else the uploaded filename stem
  reimagine -> _run_inner(idea=...)  — today's path; planner never sees the original prose
  revise    -> _run_revise_setup(...) -> plan, marked_story, non_earth, canon, bible
            -> _run_inner(seeded=True, plan=..., story=..., non_earth=...)
result += {"intake_brief": ..., "rewrite_mode": ...}
```

Intake and the merge both happen inside `WritingCouncil.run`, before `_run_inner` is
called, so the CLI, server, and UI all get the behavior from one place.
`rewrite_notes` goes to both the intake agent and the planner as an explicit directive.

## Entry points

- **`server.py` `POST /run`** — accepts `story_file: {data, filename}` (base64, written to a
  temp file and deleted after the run, matching the image handling) or `story_text`, plus
  `rewrite_mode` and `rewrite_notes`. Existing fields are unchanged.
- **`consult_the_council.py`** — `SOURCE_STORY_PATH`, `REWRITE_MODE`, `REWRITE_NOTES`
  inline constants beside `IDEA_PATH`. Prints the brief.
- **`prompt_harness.py`** — the interactive terminal harness asks the same three as
  questions: source-story path (blank to skip), mode (default reimagine), rewrite notes.
  When a path is given the harness stops asking for the idea, since the brief supplies it.
- **`static/index.html`** — file input (`.txt`/`.md`/`.docx`) with a filename chip and a
  remove button, a two-way mode radio (Reimagine / Revise), and a `rewrite_notes` textarea.
  All hidden until a file is attached. The brief renders in the result panel.

## Interaction with existing paths

- **`non_earth` + revise**: `WorldBuilderAgent` still runs (canon and bible feed the writer
  and reviewers), but `PlanningAgent.revise_with_world_bible` is **skipped** — that call
  rewrites the plan to exploit the world, which would pull the plan away from the draft it
  must describe. Reimagine mode keeps it. `WorldBuilderAgent.run` takes `idea=` — in revise
  mode it receives the brief's SYNOPSIS, since there is no user idea.
- Revise mode skips the initial write, so `INITIAL_DRAFT_MODEL` (Opus) is spent on the plan
  but never on a write. That saves one Opus write on pass one only; every later pass costs
  what it does today, and on `non_earth` the writer is Opus throughout regardless.
- `constraint` is unchanged; `constraints.check_constraint` still runs on the final output.

## Error handling

- Unsupported extension or empty text: raise before any API call.
- python-docx missing: ImportError naming `pip install python-docx`.
- Unrecognized `rewrite_mode`: `ValueError` before any API call. Empty defaults to
  `"reimagine"`.
- **Over 110,000 words: refuse, reporting the count.** That is roughly 150k tokens, leaving
  headroom in a 200k window for the system prompt and the brief. Chunked intake is out of
  scope.
- **Revise mode above 20,000 words: print a cost warning and continue.** Revise mode re-sends
  the full draft to the writer and to 3–5 checkers on every pass, so length multiplies
  across the whole run. This is a cost cliff, not a correctness limit.
- Missing brief field: log a warning, leave it blank, continue; user-supplied fields still apply.
- Sectionizer anchor miss (no match, or more than one match): glyph/blank-line fallback as
  described above.

## Testing

All tests mock LLM calls (`unittest.mock.patch`); no real API calls, per repo convention.

- `load_story_text`: txt, md, a `document_writer` .docx round-trip, empty file, bad extension.
- Brief parsing: complete block and a block with missing fields.
- Merge precedence: a user value wins; a blank falls back to the brief.
- `orchestrator.run` with `source_story=""` is unchanged — assert the planner is called with
  today's exact arguments. This is the EARTH byte-for-byte regression guard.
- Reimagine: the planner receives the synopsis-derived idea and never the original prose.
- Revise: the writer's first-write call is not made; checkers receive the marked original;
  `revise_with_world_bible` is not called on a `non_earth` revise run.
- Seeded `_run_inner`: reaches the checker fan-out with no `write_result` in scope —
  the guard against the `revised_sections` crash.
- Sectionizer: anchors insert markers without altering surrounding text; a duplicate anchor
  is rejected; the glyph and blank-line fallbacks work; text before anchor 1 is dropped.
- Word-count limits: 110k refuses; a 25k-word revise run warns but proceeds.
- Invalid `rewrite_mode` raises; empty mode with a `source_story` runs reimagine.

## Model recommendation per part

| Part | Model |
| --- | --- |
| `story_intake.py` + tests | Sonnet 5 |
| `IntakeAgent` prompt, `plan_existing` addendum | Opus 5 (prompt text is the product) |
| `sectionizer.py` | Sonnet 5 |
| Orchestrator wiring (`_run_revise_setup`, seeded `_run_inner`) | Opus 5 |
| Server, CLI, prompt harness, browser UI | Sonnet 5 |

## Out of scope

- Chunked / map-reduce intake for novel-length input.
- A review gate on the brief before the run starts (the brief is echoed in the result and
  the log instead).
- Reading images out of an uploaded .docx.
