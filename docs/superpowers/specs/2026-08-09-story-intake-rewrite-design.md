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

### `agents/intake_agent.py` (new) — `IntakeAgent(BaseAgent)`

Model: `DEFAULT_MODEL` (Sonnet 5). One call; the whole story goes in the user prompt.
`rewrite_notes` is included so extraction is directed (e.g. "original 8k, target 3k"
changes what the brief preserves). Word count is computed in Python and injected — never
guessed by the model.

Output is a fixed-shape block:

```
=== STORY BRIEF ===
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

Runtime model: `FEEDBACK_MODEL` (Haiku 4.5). A single call returns *anchors* (the first ~8 words of each section start). Python locates
each anchor in the original and inserts `<<<SECTION N>>>`. The model never re-emits prose,
so the text cannot mutate and no tokens are spent echoing the story.

Fallback when anchors don't all match: split on scene-break glyphs (`***`, `---`, `#`),
then on blank lines, to reach the plan's section count. If the count still differs, log it
and proceed — `plan_revision` works with whatever markers exist.

### `agents/planning_agent.py` (changed)

`PlanningAgent.run` gains optional `source_story: str = ""` and `plan_existing: bool = False`.
When set, a prompt addendum instructs it to plan the story that exists rather than invent
one. Output format is unchanged: `<<<WORLD_CLASS>>>` tag, `STORY ENGINE` block, per-section
"How it escalates". Everything downstream is untouched.

### `orchestrator.py` (changed)

`WritingCouncil.run` gains:

- `source_story: str = ""` — raw text of the uploaded story.
- `rewrite_mode: str = ""` — `"reimagine"` or `"revise"`; ignored when `source_story` is empty.
- `rewrite_notes: str = ""` — free-text rewrite directive.

Returns `intake_brief` and `rewrite_mode` alongside the existing keys.

## Data flow

```
upload -> load_story_text -> IntakeAgent -> brief
       -> merge: a non-empty user field wins; otherwise the brief fills it
          idea          <- SYNOPSIS
          world_rules   <- WORLD RULES
          framework     <- STORYLINE/STRUCTURE
          target_length <- LENGTH
          title         <- uploaded filename stem
  reimagine -> existing _run_inner (planner never sees the original prose)
  revise    -> PlanningAgent.run(plan_existing=True, source_story=...)
            -> sectionize the original
            -> enter Inner at the checker fan-out, skipping the first write
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
- **`static/index.html`** — file input (`.txt`/`.md`/`.docx`) with a filename chip and a
  remove button, a two-way mode radio (Reimagine / Revise), and a `rewrite_notes` textarea.
  All hidden until a file is attached. The brief renders in the result panel.

## Interaction with existing paths

- **`non_earth` + revise**: `WorldBuilderAgent` still runs (canon and bible feed the writer
  and reviewers), but `PlanningAgent.revise_with_world_bible` is **skipped** — that call
  rewrites the plan to exploit the world, which would pull the plan away from the draft it
  must describe. Reimagine mode keeps it.
- Revise mode skips the initial write, so `INITIAL_DRAFT_MODEL` (Opus) is used only for the
  plan there; a revise run costs less than a fresh run.
- `constraint` is unchanged; `constraints.check_constraint` still runs on the final output.

## Error handling

- Unsupported extension or empty text: raise before any API call.
- python-docx missing: ImportError naming `pip install python-docx`.
- Over ~150,000 words: refuse, reporting the count. Chunked intake is out of scope.
- Missing brief field: log a warning, leave it blank, continue; user-supplied fields still apply.
- Sectionizer anchor miss: glyph/blank-line fallback as described above.

## Testing

All tests mock LLM calls (`unittest.mock.patch`); no real API calls, per repo convention.

- `load_story_text`: txt, md, a `document_writer` .docx round-trip, empty file, bad extension.
- Brief parsing: complete block and a block with missing fields.
- Merge precedence: a user value wins; a blank falls back to the brief.
- `orchestrator.run` with `source_story=""` is unchanged — assert the planner is called with
  today's exact arguments. This is the EARTH byte-for-byte regression guard.
- Reimagine: the planner receives the synopsis-derived idea and never the original prose.
- Revise: the writer's first-write call is not made; checkers receive the marked original.
- Sectionizer: anchors insert markers without altering surrounding text; fallback path works.

## Model recommendation per part

| Part | Model |
| --- | --- |
| `story_intake.py` + tests | Sonnet 5 |
| `IntakeAgent` prompt, `plan_existing` addendum | Opus 5 (prompt text is the product) |
| `sectionizer.py` | Sonnet 5 |
| Orchestrator wiring | Opus 5 |
| Server, CLI, browser UI | Sonnet 5 |

## Out of scope

- Chunked / map-reduce intake for novel-length input.
- A review gate on the brief before the run starts (the brief is echoed in the result and
  the log instead).
- Reading images out of an uploaded .docx.
