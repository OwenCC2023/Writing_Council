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

An empty `source_story` leaves the existing pipeline's **prompt text** byte-for-byte
unchanged — which is what the repo's prompt-string tests actually guard. One deliberate
exception applies to every run, upload or not: writer `max_tokens` is derived from
`target_length` instead of the flat 8192 (see below). It is a ceiling raise, so no existing
run can produce less than it does today.

## Components

### `story_intake.py` (new, no LLM)

`load_story_text(path) -> str`

- `.txt` / `.md`: read as UTF-8.
- `.docx`: python-docx (already in `requirements.txt`, used by `document_writer`);
  paragraphs joined with a blank line between.
- Raises on unsupported extension, unreadable file, or empty text.

The 110,000-word cap does **not** live here. The server also accepts pasted `story_text`,
which never touches this function, so the guard belongs in `WritingCouncil.run` where both
paths converge. This function only loads.

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

### `agents/sectionizer_agent.py` (new) — revise mode only

Filed under `agents/` rather than at the repo root, following the "one class per agent"
convention. The pure marker-insertion helpers live in the same module as the agent that
feeds them.

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

`PlanningAgent.run` gains three optional parameters:

- `brief: str = ""` — the full `=== STORY BRIEF ===` block, injected as its own labelled
  section of the user prompt. **Both modes use this.** Mapping only SYNOPSIS into `idea`
  would strand CHARACTERS, PLOT, INTENT, and GENRE — the planner would reinvent exactly
  what intake was called to extract. The brief goes through whole; the merge governs only
  the craft params (length, audience, style, title, world_rules, framework).
- `rewrite_notes: str = ""` — rendered as its own `REWRITE DIRECTIVE:` block. Not folded
  into `framework`, which already carries the structure text. The prompt states that the
  directive **outranks TARGET LENGTH** when the two conflict: leaving length blank and
  writing "cut it to 3,000 words" in the notes otherwise hands the planner the brief's
  8,432-word LENGTH and a contradicting instruction.
- `source_story: str = ""` plus `plan_existing: bool = False` — revise mode only. A prompt
  addendum instructs the planner to plan the story that exists rather than invent one.

Output format is unchanged: `<<<WORLD_CLASS>>>` tag, `STORY ENGINE` block, per-section
"How it escalates". Everything downstream is untouched.

The `plan_existing` addendum must **override the section-chunking rule in
`CLASSIFY_ADDENDUM`**, which tells the planner to chunk into more, smaller sections when
NON-EARTH. On a revise run the section count has to come from the draft's actual scene
structure — otherwise the sectionizer is asked for more anchors than there are scenes and
the fallback fires on every run.

### `orchestrator.py` (changed)

`WritingCouncil.run` gains:

- `source_story: str = ""` — raw text of the uploaded story.
- `rewrite_mode: str = ""` — `"reimagine"` or `"revise"`; ignored when `source_story` is
  empty. Empty with a `source_story` present defaults to `"reimagine"`; any other value
  raises `ValueError` before an API call.
- `rewrite_notes: str = ""` — free-text rewrite directive.

Returns `intake_brief`, `rewrite_mode`, and the **resolved** `title` and `target_length`
alongside the existing keys. The resolved values matter: `/save` takes the title from the
client, so when the brief supplied it the browser has no other way to learn it.

### Writer `max_tokens` derived from `target_length` (changed, applies to every run)

Correction from the code: writer calls do **not** use the 8192 default. They already pass
`INITIAL_WRITE_MAX_TOKENS = 16000` (`agents/writer_agent.py:8`), about 10,000 words. The
8192 default applies to reviewers and the planner. So the ceiling is higher than the fourth
duck pass assumed, and a normal 8k-word run is in no danger — but a 20k-word upload still
overruns it and truncates mid-draft.

A helper `max_tokens_for(target_length, floor)` parses a word count out of `target_length`
and returns `clamp(words * 1.4, floor, 32000)`. Writer calls pass
`floor=INITIAL_WRITE_MAX_TOKENS`. Unparseable or absent `target_length` → the floor.

This is a ceiling raise only, and for every target at or below ~11,400 words it computes
16000 — byte-for-byte today's behavior. Prompt text is untouched, so the prompt-string
regression tests are unaffected.

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
3. If `non_earth`: `WorldBuilderAgent.run(idea=<the merged idea>, plan=plan, world_rules=...)`
   → canon and bible. The merged idea, not the raw SYNOPSIS — a user-supplied idea still
   wins. `revise_with_world_bible` is **not** called (see below).
4. `sectionize(plan, source_story)` → the draft with `<<<SECTION N>>>` markers.
5. Build `planning_details` — the same input echo the initial branch builds, plus
   `rewrite_mode`, `rewrite_notes`, and the source word count. Without this a revise run
   returns `planning_details=""` and the log loses the run's inputs.

`run()` then calls `_run_inner(seeded=True, plan=..., story=..., non_earth=..., ...)` and
the outer loop proceeds exactly as it does today.

## Data flow

```
upload -> load_story_text -> IntakeAgent -> brief
       -> the whole brief is passed to PlanningAgent as `brief=` in both modes
       -> merge, for the craft params only: a non-empty user field wins,
          otherwise the brief fills it
          idea          <- SYNOPSIS
          world_rules   <- WORLD RULES
          framework     <- STORYLINE/STRUCTURE
          target_length <- LENGTH
          target_audience, style, constraint  <- user only; no brief fallback
          title         <- brief TITLE, else the uploaded filename stem
  reimagine -> _run_inner(idea=...)  — today's path; planner never sees the original prose
  revise    -> _run_revise_setup(...) -> plan, marked_story, non_earth, canon, bible
            -> _run_inner(seeded=True, plan=..., story=..., non_earth=...)
result += {"intake_brief": ..., "rewrite_mode": ..., "title": ..., "target_length": ...}
```

Intake and the merge both happen inside `WritingCouncil.run`, before `_run_inner` is
called, so the CLI, server, and UI all get the behavior from one place. The 110,000-word
guard lives here too, covering uploaded and pasted text alike.
`rewrite_notes` goes to both the intake agent and the planner.

When `source_story` is empty the orchestrator **omits** `brief`, `rewrite_notes`, and
`source_story` from the `PlanningAgent.run` call rather than passing `""`. That is what
keeps the existing planner call-args assertions green.

### Blank means blank

The merge only works if an untouched field arrives empty. Today it never does:
`static/index.html:148-152` hardcodes `value="8,000 words"` and
`value="Adult sci-fi readers"` and marks both required, and `server.py` re-defaults them
on top. Left as-is, every upload silently retargets to 8,000 words and the brief's LENGTH
can never win.

- **UI**: when a story file is attached, clear those two inputs, drop the required marker,
  and relabel them "(blank = match the original)".
- **Server**: skip the `data.get(..., <default>)` fallbacks when `source_story` is present —
  pass `""` through and let the merge decide.
- **CLI and prompt harness**: same rule; their defaults apply only to fresh runs.

## Entry points

- **`server.py` `POST /run`** — accepts `story_file: {data, filename}` (base64, written to a
  temp file, matching the image handling) or `story_text`, plus `rewrite_mode` and
  `rewrite_notes`. Existing fields are unchanged. Two things do **not** come for free:
  - The `finally` block only iterates `image_paths`. The story temp file has to join it —
    use one shared `temp_paths` list — or it leaks on every upload.
  - The response is an explicit allowlist dict, not a passthrough. `intake_brief`,
    `rewrite_mode`, `title`, and `target_length` must be added to it by hand.
- **`consult_the_council.py`** — `SOURCE_STORY_PATH`, `REWRITE_MODE`, `REWRITE_NOTES`
  inline constants beside `IDEA_PATH`. Prints the brief.
- **`prompt_harness.py`** — the interactive terminal harness asks the same three as
  questions: source-story path (blank to skip), mode (default reimagine), rewrite notes.
  When a path is given the harness stops asking for the idea, since the brief supplies it.
- **`static/index.html`** — file input (`.txt`/`.md`/`.docx`) with a filename chip and a
  remove button, a two-way mode radio (Reimagine / Revise), and a `rewrite_notes` textarea.
  All hidden until a file is attached. The brief renders in the result panel. The title
  input is backfilled from the response's resolved `title` before save is offered, since
  `/save` sends the title from the client.

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
- **Logging**: every step in this pipeline writes to `logs/run_<ts>.log` through
  `_log_start`/`_log_end`. The new steps do too — `outer.intake` (logging the brief in full)
  and `outer.sectionize` (logging the anchors). Neither logs the story text; it is already
  the run's largest input.

## Error handling

- Unsupported extension or empty text: raise before any API call.
- python-docx missing: ImportError naming `pip install python-docx`.
- Unrecognized `rewrite_mode`: `ValueError` before any API call. Empty defaults to
  `"reimagine"`.
- **Over 110,000 words: refuse in `WritingCouncil.run`, reporting the count.** Checked
  there, not in `load_story_text`, so pasted `story_text` is covered too. That is roughly 150k tokens, leaving
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

- `load_story_text`: txt, md, empty file, bad extension, and a `document_writer` .docx
  round-trip — which asserts the manuscript front matter **is** present in the output, since
  stripping is the intake prompt's and the sectionizer's job, not this function's.
- `/run` with a `story_file`: the temp file is deleted in `finally`, and the response
  carries `intake_brief`, `rewrite_mode`, `title`, and `target_length`.
- Writer `max_tokens`: `"20,000 words"` → 28,000; `"8,000 words"` → 11,200; `"200 words"`
  and an unparseable string → the 8192 floor; an absurd target clamps to 32,000.
- Brief parsing: complete block and a block with missing fields.
- Merge precedence: a user value wins; a blank falls back to the brief.
- `orchestrator.run` with `source_story=""` is unchanged — assert the planner is called with
  today's exact arguments and that the three new kwargs are absent, not `""`. This is the
  prompt-text regression guard.
- Reimagine: the planner receives the merged idea and the full brief, and never the
  original prose.
- Revise: the writer's first-write call is not made; checkers receive the marked original;
  `revise_with_world_bible` is not called on a `non_earth` revise run.
- Seeded `_run_inner`: reaches the checker fan-out with no `write_result` in scope —
  the guard against the `revised_sections` crash.
- Sectionizer: anchors insert markers without altering surrounding text; a duplicate anchor
  is rejected; the glyph and blank-line fallbacks work; text before anchor 1 is dropped.
- Word-count limits: 110k refuses via `run()` for both an uploaded file and pasted
  `story_text`; a 25k-word revise run warns but proceeds.
- Invalid `rewrite_mode` raises; empty mode with a `source_story` runs reimagine.
- The planner receives the full brief in both modes — assert CHARACTERS and PLOT text
  reaches `PlanningAgent.run`, not just the synopsis.
- Blank-means-blank: a `/run` payload with `source_story` and no `target_length` reaches
  the planner with the brief's LENGTH, not `"8,000 words"`.
- A revise run returns a non-empty `planning_details`.

## Model recommendation per part

| Part | Model |
| --- | --- |
| `story_intake.py` + tests | Sonnet 5 |
| `IntakeAgent` prompt, `plan_existing` addendum | Opus 5 (prompt text is the product) |
| `agents/sectionizer_agent.py` | Sonnet 5 |
| Orchestrator wiring (`_run_revise_setup`, seeded `_run_inner`) | Opus 5 |
| Server, CLI, prompt harness, browser UI | Sonnet 5 |

## Out of scope

- Chunked / map-reduce intake for novel-length input.
- A review gate on the brief before the run starts (the brief is echoed in the result and
  the log instead).
- Reading images out of an uploaded .docx.
