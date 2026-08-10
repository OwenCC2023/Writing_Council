# Story Intake & Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user upload an existing story and have the council rewrite it, either as a fresh story on the original's bones (reimagine) or as a heavy revision of the original prose (revise).

**Architecture:** A new `IntakeAgent` digests the uploaded text into a fixed-shape `=== STORY BRIEF ===` block. `WritingCouncil.run` merges that brief with user-supplied fields (user wins when non-empty) and passes the whole brief to `PlanningAgent`, which keeps sole authority over the `<<<WORLD_CLASS>>>` tag that trips `non_earth`. Reimagine takes today's path. Revise adds `_run_revise_setup` (plan the existing story, classify, world-build, insert section markers) and a new seeded branch in `_run_inner` that skips the first write and starts at the checker fan-out.

**Tech Stack:** Python 3.11, `anthropic` SDK, Flask, python-docx (already a dependency), pytest with `unittest.mock`.

**Spec:** `docs/superpowers/specs/2026-08-09-story-intake-rewrite-design.md`

## Global Constraints

- Branch: `feature/story-intake-rewrite`. Commit after every task.
- **No real API calls in tests.** Mock with `unittest.mock.patch` / `MagicMock`, per repo convention. `tests/conftest.py` already sets a dummy `ANTHROPIC_API_KEY` for every test.
- **Never start a real council run to verify code.** Runs take minutes and are billed.
- Prompt strings use the repo's escaped-newline style: `"""\` opening, `\` at end of each continued line.
- When `source_story` is empty, the orchestrator must **omit** `brief`, `rewrite_notes`, and `source_story` from the `PlanningAgent.run` call — not pass `""`. This keeps existing call-args assertions green.
- Existing prompt text must not change. New behavior arrives as new addenda and new prompt blocks, appended only when the relevant parameter is non-empty.
- Word-count limits: refuse above 110,000 words; warn (and continue) above 20,000 words in revise mode.
- Run the full suite with `python -m pytest tests -q` before each commit. From Task 10 on, also `npm test` for the browser-page tests.
- **Every task ships automated tests, including the CLI, the prompt harness, and the browser page.** This overrides the repo's current state, where those three files have none. Task 10 stands up a vitest + jsdom harness for `static/index.html`.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `story_intake.py` (new) | Load `.txt`/`.md`/`.docx` into plain text; count words. No LLM, no policy. |
| `agents/intake_agent.py` (new) | `IntakeAgent` + `parse_brief`. Turns story text into the brief block and back into a dict. |
| `agents/sectionizer_agent.py` (new) | `SectionizerAgent` (anchors) + pure `insert_markers` / `fallback_sectionize`. |
| `agents/base_agent.py` (modify) | `max_tokens_for(target_length, floor)` helper. |
| `agents/writer_agent.py` (modify) | `run`/`revise` accept an optional `max_tokens`. |
| `agents/planning_agent.py` (modify) | `run` accepts `brief`, `rewrite_notes`, `source_story`, `plan_existing`; new `PLAN_EXISTING_ADDENDUM`. |
| `orchestrator.py` (modify) | Intake, merge, guards, `_run_revise_setup`, seeded `_run_inner`, new return keys. |
| `server.py` (modify) | `story_file`/`story_text` intake, shared temp cleanup, blank-means-blank defaults, new response keys. |
| `consult_the_council.py`, `prompt_harness.py` (modify) | CLI and interactive entry points. |
| `static/index.html` (modify) | Upload control, mode radio, notes box, blanked length/audience, title backfill. |

Tasks 1–3 are independent and touch only new files. Tasks 4–5 are independent agent changes. Task 6 depends on 1, 2, 5. Task 7 depends on 3, 4, 6. Tasks 8–10 depend on 6 and 7.

---

### Task 1: Story file loading

**Files:**
- Create: `story_intake.py`
- Test: `tests/test_story_intake.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `load_story_text(path: str | Path) -> str`, `word_count(text: str) -> int`, `SUPPORTED_SUFFIXES: set[str]`.

Note: the 110,000-word cap does **not** live here. The server also accepts pasted text that never touches this function, so the guard belongs in `WritingCouncil.run` (Task 6). Manuscript front matter is **not** stripped here either — that is the intake prompt's job (Task 2) and the sectionizer's (Task 3).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_story_intake.py
import pytest
from docx import Document

from story_intake import load_story_text, word_count


def test_loads_txt(tmp_path):
    p = tmp_path / "story.txt"
    p.write_text("Once upon a time.\n\nThe end.", encoding="utf-8")
    assert load_story_text(p) == "Once upon a time.\n\nThe end."


def test_loads_md(tmp_path):
    p = tmp_path / "story.md"
    p.write_text("# Title\n\nProse here.", encoding="utf-8")
    assert "Prose here." in load_story_text(p)


def test_loads_docx_joining_paragraphs_with_blank_lines(tmp_path):
    p = tmp_path / "story.docx"
    doc = Document()
    doc.add_paragraph("Owen Cardwell-Copenhefer")
    doc.add_paragraph("First line of narrative.")
    doc.save(p)
    text = load_story_text(p)
    assert "Owen Cardwell-Copenhefer\n\nFirst line of narrative." in text


def test_docx_front_matter_is_not_stripped(tmp_path):
    """Stripping is the intake prompt's job, not this function's."""
    p = tmp_path / "story.docx"
    doc = Document()
    doc.add_paragraph("approx. 8,000 words")
    doc.add_paragraph("Narrative starts.")
    doc.save(p)
    assert "approx. 8,000 words" in load_story_text(p)


def test_rejects_unsupported_extension(tmp_path):
    p = tmp_path / "story.pdf"
    p.write_bytes(b"%PDF-1.4")
    with pytest.raises(ValueError, match="Unsupported"):
        load_story_text(p)


def test_rejects_empty_file(tmp_path):
    p = tmp_path / "story.txt"
    p.write_text("   \n\n  ", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        load_story_text(p)


def test_word_count_counts_whitespace_separated_tokens():
    assert word_count("one two  three\nfour") == 4
    assert word_count("") == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_story_intake.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'story_intake'`

- [ ] **Step 3: Write the implementation**

```python
# story_intake.py
"""Load an existing story from disk into plain text.

No LLM, no policy: this module reads files. Length limits live in
WritingCouncil.run (pasted text never reaches this module), and manuscript
front matter is left in place for the intake prompt to ignore.
"""

from pathlib import Path

SUPPORTED_SUFFIXES = {".txt", ".md", ".docx"}


def word_count(text: str) -> int:
    """Whitespace-separated token count."""
    return len(text.split())


def _load_docx(path: Path) -> str:
    try:
        from docx import Document
    except ImportError as exc:  # pragma: no cover - dependency is in requirements.txt
        raise ImportError(
            "Reading .docx requires python-docx. Run: pip install python-docx"
        ) from exc
    doc = Document(str(path))
    return "\n\n".join(p.text for p in doc.paragraphs)


def load_story_text(path) -> str:
    """Return the plain text of a .txt, .md, or .docx story file."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(
            f"Unsupported story file type '{suffix or path.name}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_SUFFIXES))}"
        )
    if suffix == ".docx":
        text = _load_docx(path)
    else:
        text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"Story file '{path.name}' is empty.")
    return text.strip()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_story_intake.py -q`
Expected: PASS (7 tests)

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest tests -q`
Expected: PASS — nothing else touches this module yet.

- [ ] **Step 6: Commit**

```bash
git add story_intake.py tests/test_story_intake.py
git commit -m "feat: load uploaded stories from txt, md, and docx"
```

---

### Task 2: Intake agent and brief parsing

**Files:**
- Create: `agents/intake_agent.py`
- Modify: `agents/__init__.py`
- Test: `tests/test_intake_agent.py`

**Interfaces:**
- Consumes: `BaseAgent`, `DEFAULT_MODEL` from `agents/base_agent.py`.
- Produces:
  - `IntakeAgent().run(story: str, rewrite_notes: str = "", source_words: int = 0) -> dict` with keys `agent`, `output`.
  - `parse_brief(brief: str) -> dict` — keys are the field names in `BRIEF_FIELDS`; a missing field maps to `""`.
  - `BRIEF_FIELDS: list[str]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_intake_agent.py
from unittest.mock import patch

from agents.intake_agent import IntakeAgent, parse_brief, BRIEF_FIELDS

_BRIEF = """\
=== STORY BRIEF ===
TITLE: The Sforzato
WORLD_CLASS_GUESS: NON-EARTH — interstellar war, invented FTL physics
GENRE: military space opera
SETTING: a fallen empire's frontier systems
WORLD RULES: hyperlanes connect only certain systems; FTL comms need relay ships
CHARACTERS: Admiral Ligatto — wants vindication, fears irrelevance, drives the counteroffensive
PLOT: Ligatto launches the counteroffensive
  Republican forces fall back
  Frankfurt im Weltraum breaks the momentum
STORYLINE/STRUCTURE: third limited, past tense, chronological
INTENT: make the reader feel the cost of a turning point nobody chose
LENGTH: 8432 words
SYNOPSIS: A doomed empire's last offensive breaks on an accident of timing.
"""


def test_parse_brief_extracts_every_field():
    fields = parse_brief(_BRIEF)
    assert fields["TITLE"] == "The Sforzato"
    assert fields["GENRE"] == "military space opera"
    assert fields["LENGTH"] == "8432 words"
    assert fields["SYNOPSIS"].startswith("A doomed empire")


def test_parse_brief_keeps_multiline_field_bodies():
    fields = parse_brief(_BRIEF)
    assert "Republican forces fall back" in fields["PLOT"]
    assert "Frankfurt im Weltraum" in fields["PLOT"]
    # The next header ends the field.
    assert "STORYLINE" not in fields["PLOT"]


def test_parse_brief_missing_field_becomes_empty_string():
    fields = parse_brief("=== STORY BRIEF ===\nTITLE: Only This\n")
    assert fields["TITLE"] == "Only This"
    assert fields["PLOT"] == ""
    assert set(fields) == set(BRIEF_FIELDS)


def test_run_injects_computed_word_count_not_a_guess():
    agent = IntakeAgent()
    with patch.object(agent, "_call_claude", return_value=_BRIEF) as m:
        agent.run(story="the prose", source_words=8432)
    user_prompt = m.call_args.args[1]
    assert "8432" in user_prompt
    assert "the prose" in user_prompt


def test_run_threads_rewrite_notes_into_the_prompt():
    agent = IntakeAgent()
    with patch.object(agent, "_call_claude", return_value=_BRIEF) as m:
        agent.run(story="the prose", rewrite_notes="cut it to 3,000 words")
    assert "cut it to 3,000 words" in m.call_args.args[1]


def test_system_prompt_orders_front_matter_ignored():
    agent = IntakeAgent()
    with patch.object(agent, "_call_claude", return_value=_BRIEF) as m:
        agent.run(story="the prose")
    system_prompt = m.call_args.args[0]
    assert "front matter" in system_prompt
    assert "STORY BRIEF" in system_prompt


def test_run_returns_expected_shape():
    agent = IntakeAgent()
    with patch.object(agent, "_call_claude", return_value=_BRIEF):
        assert agent.run(story="x") == {"agent": "IntakeAgent", "output": _BRIEF}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_intake_agent.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'agents.intake_agent'`

- [ ] **Step 3: Write the implementation**

```python
# agents/intake_agent.py
import re

from .base_agent import BaseAgent

BRIEF_FIELDS = [
    "TITLE",
    "WORLD_CLASS_GUESS",
    "GENRE",
    "SETTING",
    "WORLD RULES",
    "CHARACTERS",
    "PLOT",
    "STORYLINE/STRUCTURE",
    "INTENT",
    "LENGTH",
    "SYNOPSIS",
]

SYSTEM_PROMPT = """\
You are a story analyst. You are given the full text of an existing story. Your job is to \
digest it into a brief that another agent will use to rebuild or revise it. You are not \
rewriting anything and you are not judging quality.

Ignore manuscript front matter entirely: an author byline, a contact block, a word-count \
line, a title page, a running header. Begin your reading from the first line of narrative. \
Take the title from the front matter only if the story names itself there.

Emit EXACTLY this block and nothing else. Every field must appear, in this order, each \
starting at the beginning of a line. A field body may run over several lines; the next \
field name ends it.

=== STORY BRIEF ===
TITLE: the story's own title, or leave blank if it has none
WORLD_CLASS_GUESS: EARTH or NON-EARTH, then an em dash and one line of why. EARTH means \
contemporary or familiar-historical Earth; NON-EARTH means off-Earth, or an Earth far \
enough from present-day common experience (far future, deep past, radically altered) that \
its sensory texture falls outside ordinary experience. This is advisory — a later agent \
makes the binding call.
GENRE: the genre as a publisher would shelve it
SETTING: where and when, concretely
WORLD RULES: every way this world departs from ours — physics, technology, biology, \
society. If it departs in no way, write NONE.
CHARACTERS: one line each for every recurring character — name, what they want, what \
they fear or have lost, and what they do for the story
PLOT: the beats in order, each on its own line, stated causally: what happens and what \
it forces next
STORYLINE/STRUCTURE: how the story is told — point of view, tense, chronology, frame, \
any document form
INTENT: what the story is trying to do to its reader. Name the effect, not the moral.
LENGTH: the word count you are given, verbatim
SYNOPSIS: one paragraph that states the premise the way a pitch would\
"""


def _brief_field_pattern() -> re.Pattern:
    names = "|".join(re.escape(f) for f in BRIEF_FIELDS)
    return re.compile(rf"^({names}):\s*(.*)$")


def parse_brief(brief: str) -> dict:
    """Split a STORY BRIEF block into {field: body}. Missing fields become ''."""
    pattern = _brief_field_pattern()
    fields = {name: "" for name in BRIEF_FIELDS}
    current = None
    for line in brief.splitlines():
        match = pattern.match(line.strip())
        if match:
            current = match.group(1)
            fields[current] = match.group(2).strip()
        elif current and line.strip() and not line.strip().startswith("==="):
            fields[current] = (fields[current] + "\n" + line.strip()).strip()
    return fields


class IntakeAgent(BaseAgent):
    """Digests an uploaded story into a fixed-shape STORY BRIEF block."""

    def run(self, story: str, rewrite_notes: str = "", source_words: int = 0) -> dict:
        user_prompt = f"SOURCE WORD COUNT: {source_words} words\n\n"
        if rewrite_notes:
            user_prompt += (
                "WHAT THE USER WANTS FROM THE REWRITE (let this direct what you "
                f"preserve and what you flag):\n{rewrite_notes}\n\n"
            )
        user_prompt += f"STORY TEXT:\n{story}\n\nProduce the STORY BRIEF."
        output = self._call_claude(SYSTEM_PROMPT, user_prompt)
        return {"agent": "IntakeAgent", "output": output}
```

- [ ] **Step 4: Export the agent**

Add to `agents/__init__.py`, following the existing import/`__all__` style in that file:

```python
from .intake_agent import IntakeAgent, parse_brief, BRIEF_FIELDS
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_intake_agent.py -q`
Expected: PASS (7 tests)

- [ ] **Step 6: Run the full suite and commit**

Run: `python -m pytest tests -q`

```bash
git add agents/intake_agent.py agents/__init__.py tests/test_intake_agent.py
git commit -m "feat: add IntakeAgent and brief parsing"
```

---

### Task 3: Sectionizer

**Files:**
- Create: `agents/sectionizer_agent.py`
- Modify: `agents/__init__.py`
- Test: `tests/test_sectionizer_agent.py`

**Interfaces:**
- Consumes: `BaseAgent`, `FEEDBACK_MODEL`.
- Produces:
  - `SectionizerAgent().run(plan: str, story: str, section_count: int) -> list[str]` — the anchor strings.
  - `insert_markers(story: str, anchors: list[str]) -> str | None` — `None` when any anchor is missing, duplicated, or out of order.
  - `fallback_sectionize(story: str, count: int) -> str`.
  - `sectionize(story: str, anchors: list[str], count: int) -> str` — `insert_markers`, else `fallback_sectionize`.

The marker contract, which must match `agents/writer_agent.py:103` and `_split_sections` at `:238`: `<<<SECTION N>>>` alone on its line, N from 1, incrementing by 1. Everything before anchor 1 is dropped — that is how a `document_writer` .docx round-trip loses its title page.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_sectionizer_agent.py
from unittest.mock import patch

from agents.sectionizer_agent import (
    SectionizerAgent, insert_markers, fallback_sectionize, sectionize,
)

_STORY = (
    "Owen Cardwell-Copenhefer\napprox. 900 words\n\n"
    "The fleet dropped out of the lane.\nLigatto watched the plot.\n\n"
    "By morning the line had bent.\nNobody called it a retreat.\n\n"
    "At Frankfurt the timing simply failed him."
)


def test_insert_markers_places_markers_and_drops_front_matter():
    out = insert_markers(_STORY, ["The fleet dropped out", "By morning the line",
                                  "At Frankfurt the timing"])
    assert out.startswith("<<<SECTION 1>>>\nThe fleet dropped out")
    assert "<<<SECTION 2>>>\nBy morning the line" in out
    assert "<<<SECTION 3>>>\nAt Frankfurt the timing" in out
    assert "Owen Cardwell-Copenhefer" not in out
    assert "approx. 900 words" not in out


def test_insert_markers_does_not_alter_the_prose():
    out = insert_markers(_STORY, ["The fleet dropped out", "At Frankfurt the timing"])
    assert "Ligatto watched the plot." in out
    assert "Nobody called it a retreat." in out


def test_insert_markers_rejects_a_missing_anchor():
    assert insert_markers(_STORY, ["The fleet dropped out", "no such text here"]) is None


def test_insert_markers_rejects_a_duplicate_anchor():
    story = "Alpha beta.\n\nAlpha beta.\n\nGamma delta."
    assert insert_markers(story, ["Alpha beta", "Gamma delta"]) is None


def test_insert_markers_rejects_out_of_order_anchors():
    assert insert_markers(_STORY, ["At Frankfurt the timing", "The fleet dropped out"]) is None


def test_fallback_sectionize_splits_on_glyph_breaks():
    story = "One.\n\n***\n\nTwo.\n\n***\n\nThree."
    out = fallback_sectionize(story, 3)
    assert out.count("<<<SECTION") == 3
    assert "One." in out and "Two." in out and "Three." in out
    assert "***" not in out


def test_fallback_sectionize_splits_on_blank_lines_when_no_glyphs():
    story = "One.\n\nTwo.\n\nThree.\n\nFour."
    out = fallback_sectionize(story, 2)
    assert out.count("<<<SECTION") == 2
    assert "Four." in out


def test_fallback_sectionize_never_emits_more_sections_than_chunks():
    out = fallback_sectionize("Only one paragraph.", 5)
    assert out.count("<<<SECTION") == 1


def test_sectionize_falls_back_when_anchors_do_not_match():
    out = sectionize(_STORY, ["nope", "still nope"], 2)
    assert out.count("<<<SECTION") == 2


def test_agent_run_returns_one_anchor_per_line():
    agent = SectionizerAgent()
    with patch.object(agent, "_call_claude",
                      return_value="The fleet dropped out\n\nBy morning the line\n"):
        anchors = agent.run(plan="p", story=_STORY, section_count=2)
    assert anchors == ["The fleet dropped out", "By morning the line"]


def test_agent_uses_the_feedback_model():
    from agents.base_agent import FEEDBACK_MODEL
    assert SectionizerAgent().model == FEEDBACK_MODEL
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_sectionizer_agent.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'agents.sectionizer_agent'`

- [ ] **Step 3: Write the implementation**

```python
# agents/sectionizer_agent.py
"""Insert <<<SECTION N>>> markers into an existing draft.

The model returns only anchors — the opening words of each section — and Python
does the insertion. The prose is never re-emitted, so it cannot mutate and no
tokens are spent echoing the story back.
"""

import re

from .base_agent import BaseAgent, FEEDBACK_MODEL

_GLYPH_BREAK = re.compile(r"^\s*(\*\s*\*\s*\*|-{3,}|#{1,6})\s*$", re.MULTILINE)

SYSTEM_PROMPT = """\
You are given a narrative plan and the full text of a draft that follows it. Return the \
anchor for each planned section: the first six to ten words of the draft passage where \
that section begins, copied EXACTLY from the draft — same words, same punctuation, same \
capitalisation.

Rules:
- One anchor per line. Nothing else: no numbering, no quotes, no commentary.
- Emit exactly as many anchors as the plan has sections, in story order.
- Every anchor must appear in the draft word for word, and must be unique in it. If an \
opening phrase repeats elsewhere in the draft, extend the anchor until it is unique.
- The first anchor marks where the narrative itself begins. Skip any manuscript front \
matter — byline, contact block, word count, title page.\
"""


def insert_markers(story: str, anchors: list) -> str:
    """Return the story with <<<SECTION N>>> markers, or None if anchors don't fit.

    Rejects an anchor that is absent, appears more than once, or arrives out of
    order. Text before the first anchor is dropped.
    """
    if not anchors:
        return None
    positions = []
    for anchor in anchors:
        first = story.find(anchor)
        if first < 0 or story.find(anchor, first + 1) != -1:
            return None
        positions.append(first)
    if positions != sorted(positions) or len(set(positions)) != len(positions):
        return None

    chunks = []
    for i, start in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(story)
        chunks.append(f"<<<SECTION {i + 1}>>>\n{story[start:end].strip()}")
    return "\n\n".join(chunks)


def _split_chunks(story: str) -> list:
    """Split on scene-break glyphs, then on blank lines if that wasn't enough."""
    chunks = [c.strip() for c in _GLYPH_BREAK.split(story) if c and c.strip()]
    chunks = [c for c in chunks if not _GLYPH_BREAK.match(c)]
    if len(chunks) > 1:
        return chunks
    return [c.strip() for c in re.split(r"\n\s*\n", story) if c.strip()]


def fallback_sectionize(story: str, count: int) -> str:
    """Group the draft into at most `count` sections without an LLM."""
    chunks = _split_chunks(story)
    count = max(1, min(count, len(chunks)))
    per = len(chunks) / count
    groups = []
    for i in range(count):
        start = int(round(i * per))
        end = int(round((i + 1) * per)) if i + 1 < count else len(chunks)
        groups.append("\n\n".join(chunks[start:end]).strip())
    return "\n\n".join(
        f"<<<SECTION {i + 1}>>>\n{g}" for i, g in enumerate(groups) if g
    )


def sectionize(story: str, anchors: list, count: int) -> str:
    """Anchor-based marking when it fits; deterministic fallback otherwise."""
    marked = insert_markers(story, anchors)
    if marked is not None:
        return marked
    print("[sectionizer] Anchors did not fit the draft — using structural fallback.")
    return fallback_sectionize(story, count)


class SectionizerAgent(BaseAgent):
    """Returns one anchor phrase per planned section."""

    def __init__(self, model: str = FEEDBACK_MODEL):
        super().__init__(model=model)

    def run(self, plan: str, story: str, section_count: int) -> list:
        user_prompt = (
            f"NARRATIVE PLAN:\n{plan}\n\n"
            f"DRAFT:\n{story}\n\n"
            f"Return exactly {section_count} anchors, one per line."
        )
        output = self._call_claude(SYSTEM_PROMPT, user_prompt)
        return [line.strip() for line in output.splitlines() if line.strip()]
```

- [ ] **Step 4: Export the agent**

Add to `agents/__init__.py`, matching the file's existing style:

```python
from .sectionizer_agent import SectionizerAgent, sectionize
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_sectionizer_agent.py -q`
Expected: PASS (11 tests)

- [ ] **Step 6: Run the full suite and commit**

Run: `python -m pytest tests -q`

```bash
git add agents/sectionizer_agent.py agents/__init__.py tests/test_sectionizer_agent.py
git commit -m "feat: add sectionizer for marking an existing draft"
```

---

### Task 4: Planner accepts the brief, the directive, and an existing story

**Files:**
- Modify: `agents/planning_agent.py` (add `PLAN_EXISTING_ADDENDUM` near `CLASSIFY_ADDENDUM` at line 97; extend `run` at line 261)
- Test: `tests/test_planning_agent.py` (append)

**Interfaces:**
- Consumes: nothing new.
- Produces: `PlanningAgent.run(..., brief: str = "", rewrite_notes: str = "", source_story: str = "", plan_existing: bool = False)`. Existing parameters and their order are unchanged; the new ones go on the end.

Each new block appears in the user prompt only when its parameter is non-empty, so a normal run's prompt text is byte-for-byte what it is today.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_planning_agent.py
from agents.planning_agent import PLAN_EXISTING_ADDENDUM


def test_run_without_new_params_leaves_prompts_unchanged():
    agent = PlanningAgent()
    with patch.object(agent, "_call_claude", return_value="plan") as m:
        agent.run(idea="i", target_length="1k", target_audience="a")
    user_prompt = m.call_args.args[1]
    assert "STORY BRIEF" not in user_prompt
    assert "REWRITE DIRECTIVE" not in user_prompt
    assert "ORIGINAL STORY TEXT" not in user_prompt
    assert PLAN_EXISTING_ADDENDUM not in m.call_args.args[0]


def test_run_threads_the_whole_brief_into_the_prompt():
    agent = PlanningAgent()
    brief = "=== STORY BRIEF ===\nCHARACTERS: Ligatto — wants vindication\nPLOT: he attacks"
    with patch.object(agent, "_call_claude", return_value="plan") as m:
        agent.run(idea="i", target_length="1k", target_audience="a", brief=brief)
    user_prompt = m.call_args.args[1]
    assert "Ligatto — wants vindication" in user_prompt
    assert "he attacks" in user_prompt


def test_run_renders_rewrite_notes_as_a_directive_block():
    agent = PlanningAgent()
    with patch.object(agent, "_call_claude", return_value="plan") as m:
        agent.run(idea="i", target_length="1k", target_audience="a",
                  rewrite_notes="cut it to 3,000 words")
    user_prompt = m.call_args.args[1]
    assert "REWRITE DIRECTIVE" in user_prompt
    assert "cut it to 3,000 words" in user_prompt
    assert "outranks" in user_prompt.lower()


def test_plan_existing_adds_addendum_and_source_story():
    agent = PlanningAgent()
    with patch.object(agent, "_call_claude", return_value="plan") as m:
        agent.run(idea="i", target_length="1k", target_audience="a",
                  source_story="The fleet dropped out of the lane.", plan_existing=True)
    assert PLAN_EXISTING_ADDENDUM in m.call_args.args[0]
    assert "The fleet dropped out of the lane." in m.call_args.args[1]


def test_plan_existing_addendum_overrides_non_earth_chunking():
    assert "MORE, SMALLER" in PLAN_EXISTING_ADDENDUM or "more, smaller" in PLAN_EXISTING_ADDENDUM
    assert "scene structure" in PLAN_EXISTING_ADDENDUM
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_planning_agent.py -q`
Expected: FAIL — `ImportError: cannot import name 'PLAN_EXISTING_ADDENDUM'`

- [ ] **Step 3: Add the addendum**

Insert after `CLASSIFY_ADDENDUM` (ends at `agents/planning_agent.py:109`):

```python
PLAN_EXISTING_ADDENDUM = """\

This plan is for a story that ALREADY EXISTS. Its full text is provided below. You are not \
inventing a story — you are writing the plan this story is built on, section by section, \
so that reviewers can hold it to its own intentions. Describe what is there. Name the \
STORY ENGINE the existing story actually runs on, not the one it should have run on.

Section numbering comes from the DRAFT'S OWN SCENE STRUCTURE — one planned section per \
scene or movement that is really in the text, in the order it appears. This OVERRIDES the \
instruction above to break a NON-EARTH world into more, smaller sections: a plan whose \
section count does not match the draft's scenes cannot be mapped onto it.

Still classify the world and still emit the WORLD_CLASS tag as your first line — the \
classification describes the world of the story as it stands, plus any change the rewrite \
directive calls for.\
"""
```

- [ ] **Step 4: Extend `run`**

Change the signature at `agents/planning_agent.py:261` to add the four parameters at the end, and build the new prompt blocks. The existing body up to `user_prompt += "\n\nProduce the full section-by-section plan."` is unchanged; insert before that line:

```python
        if brief:
            user_prompt += f"\n\nSTORY BRIEF (extracted from the original):\n{brief}"
        if rewrite_notes:
            user_prompt += (
                "\n\nREWRITE DIRECTIVE (what the user wants changed; this outranks "
                f"TARGET LENGTH where the two conflict):\n{rewrite_notes}"
            )
        if source_story:
            user_prompt += f"\n\nORIGINAL STORY TEXT:\n{source_story}"
```

and change the system-prompt line to:

```python
        system_prompt = (SYSTEM_PROMPT + CLASSIFY_ADDENDUM
                         + (PLAN_EXISTING_ADDENDUM if plan_existing else "")
                         + (IMAGE_PROMPT_ADDENDUM if image else ""))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_planning_agent.py -q`
Expected: PASS, including the pre-existing tests in that file.

- [ ] **Step 6: Run the full suite and commit**

Run: `python -m pytest tests -q`

```bash
git add agents/planning_agent.py tests/test_planning_agent.py
git commit -m "feat: planner accepts brief, rewrite directive, and an existing story"
```

---

### Task 5: Output budget derived from target length

**Files:**
- Modify: `agents/base_agent.py` (add helper near the model constants at the top)
- Modify: `agents/writer_agent.py` (`run` at :167, `revise` at :180, and the two fallback call sites at :191 and :224)
- Test: `tests/test_base_agent.py` (create), `tests/test_writer_agent.py` (append)

**Interfaces:**
- Consumes: nothing new.
- Produces: `max_tokens_for(target_length: str, floor: int) -> int` in `agents/base_agent.py`; `WriterAgent.run(..., max_tokens: int = None)` and `WriterAgent.revise(..., max_tokens: int = None)`.

Context: writer calls already pass `INITIAL_WRITE_MAX_TOKENS = 16000` (`agents/writer_agent.py:8`), roughly 10,000 words — not the 8192 default. A normal 8k-word run computes 11,200, below the floor, so it still gets exactly 16000 and nothing changes. Only genuinely long targets move.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_base_agent.py
from agents.base_agent import max_tokens_for


def test_returns_floor_for_a_typical_target():
    # 8,000 words * 1.4 = 11,200, below the writer's 16000 floor.
    assert max_tokens_for("8,000 words", 16000) == 16000


def test_scales_above_the_floor_for_a_long_target():
    assert max_tokens_for("20,000 words", 16000) == 28000


def test_strips_thousands_separators():
    assert max_tokens_for("15,000 words", 8192) == 21000


def test_clamps_to_the_ceiling():
    assert max_tokens_for("500,000 words", 16000) == 32000


def test_unparseable_or_missing_target_returns_the_floor():
    assert max_tokens_for("novella length", 16000) == 16000
    assert max_tokens_for("", 16000) == 16000
    assert max_tokens_for(None, 8192) == 8192
```

```python
# append to tests/test_writer_agent.py
from unittest.mock import patch

from agents.writer_agent import WriterAgent, INITIAL_WRITE_MAX_TOKENS


def test_run_defaults_to_the_existing_write_budget():
    agent = WriterAgent()
    with patch.object(agent, "_call_claude", return_value="story") as m:
        agent.run(plan="p")
    assert m.call_args.kwargs["max_tokens"] == INITIAL_WRITE_MAX_TOKENS


def test_run_honors_an_explicit_budget():
    agent = WriterAgent()
    with patch.object(agent, "_call_claude", return_value="story") as m:
        agent.run(plan="p", max_tokens=28000)
    assert m.call_args.kwargs["max_tokens"] == 28000


def test_revise_fallback_honors_an_explicit_budget():
    """No section markers in the draft -> full-rewrite fallback path."""
    agent = WriterAgent()
    with patch.object(agent, "_call_claude", return_value="story") as m:
        agent.revise(plan="p", story="no markers here", feedback="f", max_tokens=28000)
    assert m.call_args.kwargs["max_tokens"] == 28000
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_base_agent.py tests/test_writer_agent.py -q`
Expected: FAIL — `ImportError: cannot import name 'max_tokens_for'`

- [ ] **Step 3: Add the helper**

In `agents/base_agent.py`, after `INITIAL_DRAFT_MODEL` (line 13):

```python
import re

# Output ceiling. Prose runs ~1.4 tokens per word; the ceiling keeps a runaway
# target from requesting more than the API will return.
_TOKENS_PER_WORD = 1.4
MAX_OUTPUT_TOKENS = 32000


def max_tokens_for(target_length: str, floor: int) -> int:
    """Derive an output budget from a target length like "8,000 words".

    Returns `floor` when no count can be parsed, so an unrecognised target
    behaves exactly as it does today. Never returns less than `floor`.
    """
    match = re.search(r"[\d,]+", target_length or "")
    if not match:
        return floor
    words = int(match.group().replace(",", ""))
    return max(floor, min(int(words * _TOKENS_PER_WORD), MAX_OUTPUT_TOKENS))
```

- [ ] **Step 4: Thread `max_tokens` through the writer**

In `agents/writer_agent.py`, add `max_tokens: int = None` to the end of the `run` and `revise` signatures, and replace each of the three `max_tokens=INITIAL_WRITE_MAX_TOKENS` arguments (lines 177, 191, 224) with:

```python
                max_tokens=max_tokens or INITIAL_WRITE_MAX_TOKENS,
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_base_agent.py tests/test_writer_agent.py -q`
Expected: PASS

- [ ] **Step 6: Run the full suite and commit**

Run: `python -m pytest tests -q`

```bash
git add agents/base_agent.py agents/writer_agent.py tests/test_base_agent.py tests/test_writer_agent.py
git commit -m "feat: derive writer output budget from target length"
```

---

### Task 6: Orchestrator intake, merge, and guards (reimagine path)

**Files:**
- Modify: `orchestrator.py` (imports; `__init__` agent list at :50-69; `run` at :72; `_run_inner` at :165)
- Test: `tests/test_orchestrator_intake.py` (create)

**Interfaces:**
- Consumes: `load_story_text`/`word_count` (Task 1), `IntakeAgent`/`parse_brief` (Task 2), `PlanningAgent.run(brief=, rewrite_notes=)` (Task 4), `max_tokens_for` (Task 5).
- Produces:
  - `WritingCouncil.run(..., source_story: str = "", rewrite_mode: str = "", rewrite_notes: str = "", source_filename: str = "")`, returning `intake_brief`, `rewrite_mode`, `title`, `target_length` in addition to today's keys.
  - `WritingCouncil._merge_brief(fields: dict, *, idea, world_rules, framework, target_length, title, filename_stem) -> dict` with keys `idea`, `world_rules`, `framework`, `target_length`, `title`.
  - `MAX_SOURCE_WORDS = 110_000`, `REVISE_WARN_WORDS = 20_000` module constants.
  - `_run_inner(..., brief: str = "", rewrite_notes: str = "")`, which passes those to the planner **only when non-empty**.

Revise mode is wired in Task 7; here `rewrite_mode="revise"` may still route to the reimagine path.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_orchestrator_intake.py
import pytest
from unittest.mock import MagicMock

from orchestrator import WritingCouncil, MAX_SOURCE_WORDS

_BRIEF = """\
=== STORY BRIEF ===
TITLE: The Sforzato
WORLD_CLASS_GUESS: NON-EARTH — interstellar
GENRE: space opera
SETTING: frontier systems
WORLD RULES: hyperlanes connect only certain systems
CHARACTERS: Ligatto — wants vindication
PLOT: he attacks and the timing fails him
STORYLINE/STRUCTURE: third limited, past tense
INTENT: the cost of a turning point
LENGTH: 8432 words
SYNOPSIS: A doomed empire's last offensive breaks on an accident of timing.
"""


def _mock_council():
    council = WritingCouncil()
    council.intake.run = MagicMock(return_value={"agent": "IntakeAgent", "output": _BRIEF})
    council.planner.run = MagicMock(return_value={"agent": "PlanningAgent", "output": "plan"})
    council.writer.run = MagicMock(
        return_value={"agent": "WriterAgent", "output": "story", "revised_sections": None})
    council.consistency.run = MagicMock(return_value={"agent": "ConsistencyAgent", "output": "c"})
    council.ai_checker.run = MagicMock(return_value={"agent": "AIFailureCheckerAgent", "output": "a"})
    council.engine.run = MagicMock(return_value={"agent": "EngineReviewerAgent", "output": "e"})
    council.planner.plan_revision = MagicMock(return_value={"agent": "PlanningAgent", "output": "rp"})
    council.writer.revise = MagicMock(
        return_value={"agent": "WriterAgent", "output": "final", "revised_sections": None})
    return council


def test_merge_prefers_a_non_empty_user_value():
    council = WritingCouncil()
    from agents.intake_agent import parse_brief
    merged = council._merge_brief(
        parse_brief(_BRIEF), idea="my own idea", world_rules="", framework="",
        target_length="3,000 words", title="", filename_stem="upload")
    assert merged["idea"] == "my own idea"
    assert merged["target_length"] == "3,000 words"


def test_merge_falls_back_to_the_brief_when_a_field_is_blank():
    council = WritingCouncil()
    from agents.intake_agent import parse_brief
    merged = council._merge_brief(
        parse_brief(_BRIEF), idea="", world_rules="", framework="",
        target_length="", title="", filename_stem="upload")
    assert merged["idea"].startswith("A doomed empire")
    assert merged["target_length"] == "8432 words"
    assert "hyperlanes" in merged["world_rules"]
    assert merged["title"] == "The Sforzato"


def test_merge_uses_the_filename_stem_when_the_brief_has_no_title():
    council = WritingCouncil()
    from agents.intake_agent import parse_brief
    fields = parse_brief(_BRIEF)
    fields["TITLE"] = ""
    merged = council._merge_brief(fields, idea="", world_rules="", framework="",
                                  target_length="", title="", filename_stem="my_upload")
    assert merged["title"] == "my_upload"


def test_reimagine_sends_the_whole_brief_and_never_the_prose():
    council = _mock_council()
    council.run(idea="", target_length="", target_audience="Adults",
                source_story="The fleet dropped out of the lane.", prose_passes=0)
    kwargs = council.planner.run.call_args.kwargs
    assert "Ligatto — wants vindication" in kwargs["brief"]
    assert "he attacks and the timing fails him" in kwargs["brief"]
    assert "The fleet dropped out of the lane." not in str(kwargs)


def test_plain_run_omits_the_new_planner_kwargs_entirely():
    council = _mock_council()
    council.run(idea="a fresh idea", target_length="8,000 words",
                target_audience="Adults", prose_passes=0)
    kwargs = council.planner.run.call_args.kwargs
    assert "brief" not in kwargs
    assert "rewrite_notes" not in kwargs
    assert "source_story" not in kwargs
    council.intake.run.assert_not_called()


def test_result_carries_the_brief_mode_and_resolved_fields():
    council = _mock_council()
    result = council.run(idea="", target_length="", target_audience="Adults",
                         source_story="prose", prose_passes=0)
    assert result["intake_brief"] == _BRIEF
    assert result["rewrite_mode"] == "reimagine"
    assert result["title"] == "The Sforzato"
    assert result["target_length"] == "8432 words"


def test_empty_mode_with_a_source_story_defaults_to_reimagine():
    council = _mock_council()
    result = council.run(idea="", target_length="", target_audience="Adults",
                         source_story="prose", rewrite_mode="", prose_passes=0)
    assert result["rewrite_mode"] == "reimagine"


def test_unknown_mode_raises_before_any_api_call():
    council = _mock_council()
    with pytest.raises(ValueError, match="rewrite_mode"):
        council.run(idea="", target_length="", target_audience="Adults",
                    source_story="prose", rewrite_mode="polish", prose_passes=0)
    council.intake.run.assert_not_called()


def test_oversized_source_refuses_with_the_count():
    council = _mock_council()
    huge = "word " * (MAX_SOURCE_WORDS + 1)
    with pytest.raises(ValueError, match=str(MAX_SOURCE_WORDS)):
        council.run(idea="", target_length="", target_audience="Adults",
                    source_story=huge, prose_passes=0)
    council.intake.run.assert_not_called()


def test_rewrite_notes_reach_both_intake_and_the_planner():
    council = _mock_council()
    council.run(idea="", target_length="", target_audience="Adults",
                source_story="prose", rewrite_notes="cut to 3,000 words", prose_passes=0)
    assert council.intake.run.call_args.kwargs["rewrite_notes"] == "cut to 3,000 words"
    assert council.planner.run.call_args.kwargs["rewrite_notes"] == "cut to 3,000 words"


def test_writer_budget_scales_with_a_long_target():
    council = _mock_council()
    council.run(idea="a fresh idea", target_length="20,000 words",
                target_audience="Adults", prose_passes=0)
    assert council.writer.run.call_args.kwargs["max_tokens"] == 28000
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_orchestrator_intake.py -q`
Expected: FAIL — `ImportError: cannot import name 'MAX_SOURCE_WORDS' from 'orchestrator'`

- [ ] **Step 3: Add the constants, the agent, and the merge**

In `orchestrator.py`, extend the imports:

```python
from agents.base_agent import max_tokens_for
from agents.intake_agent import IntakeAgent, parse_brief
from agents.writer_agent import INITIAL_WRITE_MAX_TOKENS
from story_intake import word_count

MAX_SOURCE_WORDS = 110_000   # ~150k tokens; leaves window headroom for prompts
REVISE_WARN_WORDS = 20_000   # cost cliff: revise re-sends the draft every pass
REWRITE_MODES = ("reimagine", "revise")
```

Add to `__init__`, beside the other agents:

```python
        self.intake = IntakeAgent()
```

Add the merge method to `WritingCouncil`:

```python
    def _merge_brief(self, fields: dict, *, idea: str, world_rules: str,
                     framework: str, target_length: str, title: str,
                     filename_stem: str = "") -> dict:
        """A non-empty user value wins; otherwise the brief fills it in.

        Craft params only. target_audience, style, and constraint have no brief
        fallback — the user owns them.
        """
        return {
            "idea": idea or fields.get("SYNOPSIS", ""),
            "world_rules": world_rules or fields.get("WORLD RULES", ""),
            "framework": framework or fields.get("STORYLINE/STRUCTURE", ""),
            "target_length": target_length or fields.get("LENGTH", ""),
            "title": title or fields.get("TITLE", "") or filename_stem,
        }
```

- [ ] **Step 4: Wire intake into `run`**

Add `source_story: str = ""`, `rewrite_mode: str = ""`, `rewrite_notes: str = ""`, and `source_filename: str = ""` to the `run` signature. After the log file is created and **before** the inner loop starts:

```python
        brief_text = ""
        if source_story:
            mode = rewrite_mode or "reimagine"
            if mode not in REWRITE_MODES:
                raise ValueError(
                    f"Unknown rewrite_mode {mode!r}; expected one of {REWRITE_MODES}."
                )
            words = word_count(source_story)
            if words > MAX_SOURCE_WORDS:
                raise ValueError(
                    f"Source story is {words:,} words; the limit is "
                    f"{MAX_SOURCE_WORDS:,}. Chunked intake is not supported."
                )
            if mode == "revise" and words > REVISE_WARN_WORDS:
                print(f"[outer] WARNING: {words:,}-word revise run. The full draft is "
                      f"re-sent to the writer and every checker on each pass; expect "
                      f"cost to scale with length.")

            print("[outer] Running IntakeAgent on the uploaded story...")
            self._log_start("outer.intake", "IntakeAgent",
                            f"words: {words}\nrewrite_notes: {rewrite_notes or '(none)'}")
            intake_result = self.intake.run(story=source_story,
                                            rewrite_notes=rewrite_notes,
                                            source_words=words)
            self._log_end(intake_result, step="outer.intake")
            brief_text = intake_result["output"]

            merged = self._merge_brief(
                parse_brief(brief_text), idea=idea, world_rules=world_rules,
                framework=framework, target_length=target_length, title=title,
                filename_stem=Path(source_filename).stem if source_filename else "")
            idea = merged["idea"]
            world_rules = merged["world_rules"]
            framework = merged["framework"]
            target_length = merged["target_length"]
            title = merged["title"]
        else:
            mode = ""
```

Add `from pathlib import Path` to the imports if it isn't already there.

- [ ] **Step 5: Thread the brief and the budget into `_run_inner`**

Add `brief: str = ""` and `rewrite_notes: str = ""` to the `_run_inner` signature, and pass `brief=brief_text, rewrite_notes=rewrite_notes` from `run`'s call. Inside the initial branch, build the planner kwargs conditionally so a plain run's call is unchanged:

```python
            extra = {}
            if brief:
                extra["brief"] = brief
            if rewrite_notes:
                extra["rewrite_notes"] = rewrite_notes
            result = self.planner.run(
                idea=idea,
                target_length=target_length,
                target_audience=target_audience,
                world_rules=world_rules,
                framework=framework,
                style=style,
                image=image,
                model=INITIAL_DRAFT_MODEL,
                title=title,
                constraint=constraint,
                **extra,
            )
```

Compute the writer budget once in `_run_inner` and pass it to both writer call sites (`writer.run` in the initial branch and `writer.revise` in the middle branch):

```python
        write_max_tokens = max_tokens_for(target_length, INITIAL_WRITE_MAX_TOKENS)
```

`target_length` is `None` on the middle-loop path, which `max_tokens_for` handles by returning the floor.

- [ ] **Step 6: Extend the return dict**

```python
        return {"story": story, "non_earth": non_earth,
                "planning_details": planning_details,
                "constraint_check": check_constraint(constraint, story),
                "intake_brief": brief_text,
                "rewrite_mode": mode,
                "title": title,
                "target_length": target_length,
                "log": list(self._log)}
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python -m pytest tests/test_orchestrator_intake.py -q`
Expected: PASS (11 tests)

- [ ] **Step 8: Run the full suite and commit**

Run: `python -m pytest tests -q`
Expected: PASS — `tests/test_orchestrator.py` in particular, which asserts today's planner and writer call args.

```bash
git add orchestrator.py tests/test_orchestrator_intake.py
git commit -m "feat: intake, brief merge, and rewrite guards in the orchestrator"
```

---

### Task 7: Revise mode — seeded inner loop

**Files:**
- Modify: `orchestrator.py` (`__init__`; `run`; `_run_inner` at :165-285)
- Test: `tests/test_orchestrator_revise.py` (create)

**Interfaces:**
- Consumes: everything from Task 6, plus `SectionizerAgent`/`sectionize` (Task 3).
- Produces:
  - `WritingCouncil._run_revise_setup(brief, source_story, rewrite_notes, target_length, target_audience, world_rules, framework, style, title, constraint) -> tuple` of `(plan, marked_story, non_earth, canon_sheet, world_bible, planning_details)`.
  - `_run_inner(..., seeded: bool = False)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_orchestrator_revise.py
from unittest.mock import MagicMock

from orchestrator import WritingCouncil

_BRIEF = """\
=== STORY BRIEF ===
TITLE: The Sforzato
WORLD_CLASS_GUESS: NON-EARTH — interstellar
GENRE: space opera
SETTING: frontier systems
WORLD RULES: hyperlanes
CHARACTERS: Ligatto
PLOT: he attacks
STORYLINE/STRUCTURE: third limited
INTENT: cost
LENGTH: 900 words
SYNOPSIS: A last offensive breaks on an accident of timing.
"""

_STORY = ("The fleet dropped out of the lane.\n\n"
          "By morning the line had bent.\n\n"
          "At Frankfurt the timing failed him.")


def _revise_council(plan_output="<<<WORLD_CLASS: EARTH>>>\nplan text"):
    council = WritingCouncil()
    council.intake.run = MagicMock(return_value={"agent": "IntakeAgent", "output": _BRIEF})
    council.planner.run = MagicMock(
        return_value={"agent": "PlanningAgent", "output": plan_output})
    council.planner.revise_with_world_bible = MagicMock(
        return_value={"agent": "PlanningAgent", "output": "bible plan"})
    council.world_builder.run = MagicMock(
        return_value={"canon_sheet": "canon", "world_bible": "bible"})
    council.sectionizer.run = MagicMock(
        return_value=["The fleet dropped out", "By morning the line",
                      "At Frankfurt the timing"])
    council.writer.run = MagicMock(
        return_value={"agent": "WriterAgent", "output": "SHOULD NOT BE CALLED",
                      "revised_sections": None})
    council.consistency.run = MagicMock(return_value={"agent": "ConsistencyAgent", "output": "c"})
    council.ai_checker.run = MagicMock(return_value={"agent": "AIFailureCheckerAgent", "output": "a"})
    council.engine.run = MagicMock(return_value={"agent": "EngineReviewerAgent", "output": "e"})
    council.strangeness.run = MagicMock(return_value={"agent": "StrangenessReviewerAgent", "output": "s"})
    council.sensory.run = MagicMock(return_value={"agent": "SensoryQuotaAgent", "output": "q"})
    council.planner.plan_revision = MagicMock(return_value={"agent": "PlanningAgent", "output": "rp"})
    council.writer.revise = MagicMock(
        return_value={"agent": "WriterAgent", "output": "final", "revised_sections": None})
    return council


def test_revise_never_calls_the_initial_write():
    council = _revise_council()
    council.run(idea="", target_length="", target_audience="Adults",
                source_story=_STORY, rewrite_mode="revise", prose_passes=0)
    council.writer.run.assert_not_called()


def test_revise_plans_the_existing_story():
    council = _revise_council()
    council.run(idea="", target_length="", target_audience="Adults",
                source_story=_STORY, rewrite_mode="revise", prose_passes=0)
    kwargs = council.planner.run.call_args.kwargs
    assert kwargs["plan_existing"] is True
    assert kwargs["source_story"] == _STORY


def test_revise_feeds_checkers_the_marked_original():
    council = _revise_council()
    council.run(idea="", target_length="", target_audience="Adults",
                source_story=_STORY, rewrite_mode="revise", prose_passes=0)
    checked = council.consistency.run.call_args.kwargs["story"]
    assert "<<<SECTION 1>>>" in checked
    assert "The fleet dropped out of the lane." in checked
    assert "At Frankfurt the timing failed him." in checked


def test_revise_seeded_branch_survives_with_no_write_result():
    """The checker fan-out reads revised_sections; nothing wrote it on this path."""
    council = _revise_council()
    result = council.run(idea="", target_length="", target_audience="Adults",
                         source_story=_STORY, rewrite_mode="revise", prose_passes=0)
    assert result["story"]  # completed without an UnboundLocalError


def test_non_earth_revise_builds_the_world_but_skips_the_bible_plan_revision():
    council = _revise_council(plan_output="<<<WORLD_CLASS: NON-EARTH>>>\nplan text")
    result = council.run(idea="", target_length="", target_audience="Adults",
                         source_story=_STORY, rewrite_mode="revise", prose_passes=0)
    assert result["non_earth"] is True
    council.world_builder.run.assert_called_once()
    council.planner.revise_with_world_bible.assert_not_called()


def test_world_builder_receives_the_merged_idea():
    council = _revise_council(plan_output="<<<WORLD_CLASS: NON-EARTH>>>\nplan text")
    council.run(idea="my own idea", target_length="", target_audience="Adults",
                source_story=_STORY, rewrite_mode="revise", prose_passes=0)
    assert council.world_builder.run.call_args.kwargs["idea"] == "my own idea"


def test_revise_returns_populated_planning_details():
    council = _revise_council()
    result = council.run(idea="", target_length="", target_audience="Adults",
                         source_story=_STORY, rewrite_mode="revise",
                         rewrite_notes="darker ending", prose_passes=0)
    details = result["planning_details"]
    assert details
    assert "revise" in details
    assert "darker ending" in details
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_orchestrator_revise.py -q`
Expected: FAIL — `AttributeError: 'WritingCouncil' object has no attribute 'sectionizer'`

- [ ] **Step 3: Add the sectionizer agent**

In `orchestrator.py`, import and instantiate it beside the others:

```python
from agents.sectionizer_agent import SectionizerAgent, sectionize
```

```python
        self.sectionizer = SectionizerAgent()
```

- [ ] **Step 4: Add `_run_revise_setup`**

```python
    def _count_plan_sections(self, plan: str) -> int:
        """How many numbered sections the plan declares. At least 1."""
        nums = re.findall(r'^\s*(?:SECTION\s+)?(\d+)[.:)]', plan, re.MULTILINE | re.IGNORECASE)
        return max(1, len(set(nums)))

    def _run_revise_setup(self, brief: str, source_story: str, rewrite_notes: str,
                          target_length: str, target_audience: str, world_rules: str,
                          framework: str, style: str, title: str, constraint: str,
                          idea: str, label: str = "revise") -> tuple:
        """Plan the existing story, classify it, world-build, and mark sections.

        Returns (plan, marked_story, non_earth, canon_sheet, world_bible,
        planning_details). Kept out of _run_inner, whose initial branch owns
        classification for fresh runs and would reset these values.
        """
        input_text = (
            f"title: {title or '(none)'}\n"
            f"rewrite_mode: revise\n"
            f"rewrite_notes: {rewrite_notes or '(none)'}\n"
            f"source_words: {word_count(source_story)}\n"
            f"idea: {idea}\ntarget_length: {target_length}\n"
            f"target_audience: {target_audience}\n"
            f"world_rules: {world_rules or '(none)'}\n"
            f"framework: {framework or '(none)'}\n"
            f"style: {style or '(none)'}\n"
            f"constraint: {constraint or '(none)'}"
        )

        print(f"[{label}] Running PlanningAgent over the existing story...")
        self._log_start(f"{label}.plan", "PlanningAgent", input_text)
        result = self.planner.run(
            idea=idea, target_length=target_length, target_audience=target_audience,
            world_rules=world_rules, framework=framework, style=style,
            model=INITIAL_DRAFT_MODEL, title=title, constraint=constraint,
            brief=brief, rewrite_notes=rewrite_notes,
            source_story=source_story, plan_existing=True,
        )
        self._log_end(result, step=f"{label}.plan")
        non_earth, plan = self._parse_world_class(result["output"])

        canon_sheet, world_bible = "", ""
        if non_earth:
            print(f"[{label}] NON-EARTH world — running WorldBuilder...")
            self._log_start(f"{label}.world_builder", "WorldBuilderAgent",
                            f"idea:\n{idea}\n\nplan:\n{plan}")
            wb = self.world_builder.run(idea=idea, plan=plan, world_rules=world_rules)
            self._log_end(wb, step=f"{label}.world_builder")
            canon_sheet, world_bible = wb["canon_sheet"], wb["world_bible"]
            # revise_with_world_bible is deliberately NOT called: it rewrites the
            # plan to exploit the world, pulling it away from the draft it must
            # describe.

        section_count = self._count_plan_sections(plan)
        print(f"[{label}] Marking {section_count} sections in the original draft...")
        self._log_start(f"{label}.sectionize", "SectionizerAgent",
                        f"section_count: {section_count}")
        anchors = self.sectionizer.run(plan=plan, story=source_story,
                                       section_count=section_count)
        self._log_end({"agent": "SectionizerAgent", "output": "\n".join(anchors)},
                      step=f"{label}.sectionize")
        marked_story = sectionize(source_story, anchors, section_count)

        return plan, marked_story, non_earth, canon_sheet, world_bible, input_text
```

Add `import re` to `orchestrator.py` if it is not already imported.

- [ ] **Step 5: Add the seeded branch to `_run_inner`**

Add `seeded: bool = False` to the signature. Restructure the fork so no branch leaves `revised_sections` undefined — initialize it before the fork and only read `write_result` where one exists:

```python
        planning_details = ""
        revised_sections = None

        if seeded:
            # Revise mode: plan and marked draft come from _run_revise_setup.
            # No plan call, no write call — start at the checker fan-out.
            print(f"[{label}] Seeded with an existing draft; skipping the initial write.")
        elif idea is not None:
            ...  # unchanged initial branch, ending with:
            #     story = write_result["output"]
            revised_sections = write_result.get("revised_sections")
        else:
            ...  # unchanged middle branch, ending with:
            #     story = write_result["output"]
            revised_sections = write_result.get("revised_sections")
```

Then replace the existing `revised_sections = write_result.get("revised_sections")` line at `orchestrator.py:280` — it must no longer run unconditionally.

- [ ] **Step 6: Route revise mode in `run`**

Replace the single `_run_inner` call in `run` with:

```python
        if mode == "revise":
            plan, story, non_earth, canon_sheet, world_bible, planning_details = \
                self._run_revise_setup(
                    brief=brief_text, source_story=source_story,
                    rewrite_notes=rewrite_notes, target_length=target_length,
                    target_audience=target_audience, world_rules=world_rules,
                    framework=framework, style=style, title=title,
                    constraint=constraint, idea=idea)
            plan, story, non_earth, canon_sheet, world_bible, _ = self._run_inner(
                seeded=True, plan=plan, story=story, non_earth=non_earth,
                canon_sheet=canon_sheet, world_bible=world_bible,
                target_length=target_length, target_audience=target_audience,
                constraint=constraint, label="outer.inner")
        else:
            plan, story, non_earth, canon_sheet, world_bible, planning_details = \
                self._run_inner(
                    idea=idea, target_length=target_length,
                    target_audience=target_audience, world_rules=world_rules,
                    framework=framework, style=style, image=image, title=title,
                    constraint=constraint, brief=brief_text,
                    rewrite_notes=rewrite_notes, label="outer.inner")
```

Note `_run_inner`'s seeded call must not pass `idea`, which stays `None` so the initial branch cannot fire.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python -m pytest tests/test_orchestrator_revise.py -q`
Expected: PASS (7 tests)

- [ ] **Step 8: Run the full suite and commit**

Run: `python -m pytest tests -q`

```bash
git add orchestrator.py tests/test_orchestrator_revise.py
git commit -m "feat: revise mode seeds the inner loop with the uploaded draft"
```

---

### Task 8: Server endpoint

**Files:**
- Modify: `server.py` (`/run` at :31-75)
- Test: `tests/test_server.py` (append)

**Interfaces:**
- Consumes: `load_story_text` (Task 1), the new `run` signature (Task 6).
- Produces: `/run` accepting `story_file: {data, filename}`, `story_text`, `rewrite_mode`, `rewrite_notes`; response gains `intake_brief`, `rewrite_mode`, `title`, `target_length`.

Two things the existing code does not give for free: the `finally` block iterates `image_paths` only, and the response is an explicit allowlist dict rather than a passthrough.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_server.py
import base64
import os


def _b64(text: str) -> str:
    return "data:text/plain;base64," + base64.b64encode(text.encode()).decode()


def test_run_accepts_story_text_and_returns_the_brief(client):
    with patch("server.WritingCouncil") as MockCouncil:
        MockCouncil.return_value.run.return_value = {
            "story": "s", "log": [], "intake_brief": "=== STORY BRIEF ===",
            "rewrite_mode": "reimagine", "title": "The Sforzato",
            "target_length": "8432 words",
        }
        resp = client.post("/run", data=json.dumps({
            "story_text": "The fleet dropped out of the lane.",
            "rewrite_mode": "reimagine",
            "rewrite_notes": "darker ending",
        }), content_type="application/json")
    data = json.loads(resp.data)
    assert data["intake_brief"] == "=== STORY BRIEF ==="
    assert data["rewrite_mode"] == "reimagine"
    assert data["title"] == "The Sforzato"
    assert data["target_length"] == "8432 words"
    kwargs = MockCouncil.return_value.run.call_args.kwargs
    assert kwargs["source_story"] == "The fleet dropped out of the lane."
    assert kwargs["rewrite_notes"] == "darker ending"


def test_run_accepts_an_uploaded_story_file_and_deletes_the_temp(client):
    seen = {}

    def _fake_loader(path):
        seen["path"] = path
        return "loaded prose"

    with patch("server.WritingCouncil") as MockCouncil:
        MockCouncil.return_value.run.return_value = {"story": "s", "log": []}
        with patch("server.load_story_text", side_effect=_fake_loader):
            resp = client.post("/run", data=json.dumps({
                "story_file": {"data": _b64("prose here"), "filename": "sforzato.txt"},
            }), content_type="application/json")
    assert resp.status_code == 200
    kwargs = MockCouncil.return_value.run.call_args.kwargs
    assert kwargs["source_story"] == "loaded prose"
    assert kwargs["source_filename"] == "sforzato.txt"
    assert not os.path.exists(seen["path"])  # cleaned up in finally


def test_run_skips_its_defaults_when_a_story_is_supplied(client):
    with patch("server.WritingCouncil") as MockCouncil:
        MockCouncil.return_value.run.return_value = {"story": "s", "log": []}
        client.post("/run", data=json.dumps({
            "story_text": "prose",
        }), content_type="application/json")
    kwargs = MockCouncil.return_value.run.call_args.kwargs
    assert kwargs["target_length"] == ""
    assert kwargs["target_audience"] == ""


def test_run_keeps_its_defaults_for_a_fresh_run(client):
    with patch("server.WritingCouncil") as MockCouncil:
        MockCouncil.return_value.run.return_value = {"story": "s", "log": []}
        client.post("/run", data=json.dumps({"idea": "fresh"}),
                    content_type="application/json")
    kwargs = MockCouncil.return_value.run.call_args.kwargs
    assert kwargs["target_length"] == "8,000 words"
    assert kwargs["target_audience"] == "Adult sci-fi readers"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_server.py -q`
Expected: FAIL — `KeyError: 'intake_brief'` / `AttributeError: module 'server' has no attribute 'load_story_text'`

- [ ] **Step 3: Implement the endpoint changes**

In `server.py`, import the loader and generalize the temp-file handling:

```python
from story_intake import load_story_text
```

Rename `image_paths` to `temp_paths` throughout `/run` so every temp file shares one cleanup list, and add the story handling after the image block:

```python
        source_story = data.get("story_text", "") or ""
        source_filename = ""
        story_file = data.get("story_file")
        if story_file:
            source_filename = story_file.get("filename", "")
            story_path = _write_temp_image(story_file["data"], source_filename)
            temp_paths.append(story_path)
            source_story = load_story_text(story_path)
```

`_write_temp_image` already does exactly the right thing — base64 decode, suffix from the filename, write, return the path. Rename it to `_write_temp_upload` and update its docstring and the two image call sites; the body does not change.

Apply blank-means-blank to the defaults, then pass the new arguments:

```python
        has_source = bool(source_story)
        council = WritingCouncil()
        result = council.run(
            idea=data.get("idea", ""),
            target_length=data.get("target_length", "" if has_source else "8,000 words"),
            target_audience=data.get("target_audience",
                                     "" if has_source else "Adult sci-fi readers"),
            ...
            source_story=source_story,
            source_filename=source_filename,
            rewrite_mode=data.get("rewrite_mode", ""),
            rewrite_notes=data.get("rewrite_notes", ""),
        )
```

Extend the response dict:

```python
        return jsonify({
            "story": result["story"],
            "log": result["log"],
            "non_earth": result.get("non_earth", False),
            "planning_details": result.get("planning_details", ""),
            "constraint_check": result.get("constraint_check"),
            "intake_brief": result.get("intake_brief", ""),
            "rewrite_mode": result.get("rewrite_mode", ""),
            "title": result.get("title", ""),
            "target_length": result.get("target_length", ""),
        })
```

And the cleanup:

```python
    finally:
        for path in temp_paths:
            if os.path.exists(path):
                os.unlink(path)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_server.py -q`
Expected: PASS, including the existing server tests.

- [ ] **Step 5: Run the full suite and commit**

Run: `python -m pytest tests -q`

```bash
git add server.py tests/test_server.py
git commit -m "feat: accept an uploaded story at POST /run"
```

---

### Task 9: CLI and prompt harness

**Files:**
- Modify: `consult_the_council.py` (config constants at the top; the `run` call)
- Modify: `prompt_harness.py` (the question sequence; the `run` call)
- Test: `tests/test_consult_the_council.py` (create), `tests/test_prompt_harness.py` (create)

Both entry points expose a `main()` guarded by `__main__`, so both are testable by patching `WritingCouncil` and `save_as_manuscript` in the module under test. No real run occurs.

**Interfaces:**
- Consumes: `load_story_text` (Task 1), the new `run` signature (Task 6).
- Produces: nothing other tasks depend on.

- [ ] **Step 1: Add the CLI constants**

In `consult_the_council.py`, beside `IDEA_PATH`:

```python
SOURCE_STORY_PATH = ""   # path to an existing .txt/.md/.docx story, or "" for a fresh run
REWRITE_MODE = ""        # "reimagine" (new story on the original's bones) or
                         # "revise" (edit the original prose). "" defaults to reimagine.
REWRITE_NOTES = ""       # e.g. "cut it to 3,000 words", "second person", "darker ending"
```

Note in a comment that with `SOURCE_STORY_PATH` set, leaving `TARGET_LENGTH` blank keeps the original's length.

- [ ] **Step 2: Load and pass it**

```python
from story_intake import load_story_text

source_story = load_story_text(SOURCE_STORY_PATH) if SOURCE_STORY_PATH else ""
```

Add to the `council.run(...)` call:

```python
    source_story=source_story,
    source_filename=SOURCE_STORY_PATH,
    rewrite_mode=REWRITE_MODE,
    rewrite_notes=REWRITE_NOTES,
```

- [ ] **Step 3: Print the brief after the run**

```python
if result.get("intake_brief"):
    print("\n--- STORY BRIEF (extracted from the original) ---")
    print(result["intake_brief"])
```

- [ ] **Step 4: Add the harness questions**

In `prompt_harness.py`, before the idea question:

```python
    source_path = _ask("Path to an existing story to rewrite (blank for a new story)")
    source_story, rewrite_mode, rewrite_notes = "", "", ""
    if source_path:
        source_story = load_story_text(source_path)
        rewrite_mode = _ask("Rewrite mode — reimagine or revise", default="reimagine")
        rewrite_notes = _ask("Anything you want changed in the rewrite")
```

Then make the idea question conditional, since the brief supplies it:

```python
    idea = "" if source_story else _ask_multiline("Story idea", required=True)
```

Prompt for target length and audience with no default when `source_story` is set, so blank means "match the original". Pass the four new arguments to `council.run(...)` exactly as in Step 2, and print the brief as in Step 3.

- [ ] **Step 5: Write the CLI tests**

```python
# tests/test_consult_the_council.py
from unittest.mock import MagicMock, patch

import consult_the_council as cli


def _result():
    return {"story": "s", "log": [], "planning_details": "d",
            "constraint_check": None, "intake_brief": "=== STORY BRIEF ==="}


def test_fresh_run_passes_no_source_story(monkeypatch):
    monkeypatch.setattr(cli, "SOURCE_STORY_PATH", "")
    with patch.object(cli, "WritingCouncil") as MockCouncil, \
            patch.object(cli, "save_as_manuscript", return_value="out.docx"):
        MockCouncil.return_value.run.return_value = _result()
        cli.main()
    kwargs = MockCouncil.return_value.run.call_args.kwargs
    assert kwargs["source_story"] == ""
    assert kwargs["rewrite_mode"] == ""


def test_source_story_path_is_loaded_and_threaded(monkeypatch, tmp_path):
    story = tmp_path / "sforzato.txt"
    story.write_text("The fleet dropped out of the lane.", encoding="utf-8")
    monkeypatch.setattr(cli, "SOURCE_STORY_PATH", str(story))
    monkeypatch.setattr(cli, "REWRITE_MODE", "revise")
    monkeypatch.setattr(cli, "REWRITE_NOTES", "darker ending")
    with patch.object(cli, "WritingCouncil") as MockCouncil, \
            patch.object(cli, "save_as_manuscript", return_value="out.docx"):
        MockCouncil.return_value.run.return_value = _result()
        cli.main()
    kwargs = MockCouncil.return_value.run.call_args.kwargs
    assert kwargs["source_story"] == "The fleet dropped out of the lane."
    assert kwargs["source_filename"] == str(story)
    assert kwargs["rewrite_mode"] == "revise"
    assert kwargs["rewrite_notes"] == "darker ending"


def test_brief_is_printed_when_present(monkeypatch, capsys, tmp_path):
    story = tmp_path / "s.txt"
    story.write_text("prose", encoding="utf-8")
    monkeypatch.setattr(cli, "SOURCE_STORY_PATH", str(story))
    with patch.object(cli, "WritingCouncil") as MockCouncil, \
            patch.object(cli, "save_as_manuscript", return_value="out.docx"):
        MockCouncil.return_value.run.return_value = _result()
        cli.main()
    assert "STORY BRIEF" in capsys.readouterr().out
```

- [ ] **Step 6: Write the harness tests**

`_ask` and `_ask_multiline` both pass their prompt text to `input()`, so the fake keys off a substring of the prompt rather than a rigid answer order.

```python
# tests/test_prompt_harness.py
from unittest.mock import patch

import prompt_harness as harness


def _answers(mapping, default=""):
    """Fake input(): match the prompt against mapping keys by substring."""
    def _fake(prompt=""):
        for key, value in mapping.items():
            if key.lower() in prompt.lower():
                return value
        return default
    return _fake


def _result():
    return {"story": "s", "log": [], "planning_details": "d",
            "intake_brief": "=== STORY BRIEF ==="}


def test_rewrite_answers_are_threaded_into_the_run(tmp_path):
    story = tmp_path / "sforzato.txt"
    story.write_text("The fleet dropped out of the lane.", encoding="utf-8")
    answers = {
        "story title": "The Sforzato",
        "author": "Owen",
        "existing story": str(story),
        "rewrite mode": "revise",
        "changed in the rewrite": "darker ending",
        "target audience": "Adults",
        "launch": "y",
    }
    with patch("builtins.input", _answers(answers)), \
            patch.object(harness, "WritingCouncil") as MockCouncil, \
            patch.object(harness, "save_as_manuscript", return_value="out.docx"):
        MockCouncil.return_value.run.return_value = _result()
        harness.main()
    kwargs = MockCouncil.return_value.run.call_args.kwargs
    assert kwargs["source_story"] == "The fleet dropped out of the lane."
    assert kwargs["rewrite_mode"] == "revise"
    assert kwargs["rewrite_notes"] == "darker ending"


def test_idea_is_not_asked_when_a_source_story_is_given(tmp_path):
    story = tmp_path / "s.txt"
    story.write_text("prose", encoding="utf-8")
    seen = []

    def _fake(prompt=""):
        seen.append(prompt)
        if "existing story" in prompt.lower():
            return str(story)
        if "title" in prompt.lower():
            return "T"
        if "author" in prompt.lower():
            return "A"
        if "audience" in prompt.lower():
            return "Adults"
        if "launch" in prompt.lower():
            return "y"
        return ""

    with patch("builtins.input", _fake), \
            patch.object(harness, "WritingCouncil") as MockCouncil, \
            patch.object(harness, "save_as_manuscript", return_value="out.docx"):
        MockCouncil.return_value.run.return_value = _result()
        harness.main()
    assert not any("story idea" in p.lower() for p in seen)
    assert MockCouncil.return_value.run.call_args.kwargs["idea"] == ""


def test_a_fresh_run_still_asks_for_the_idea():
    seen = []

    def _fake(prompt=""):
        seen.append(prompt)
        if "title" in prompt.lower():
            return "T"
        if "author" in prompt.lower():
            return "A"
        if "audience" in prompt.lower():
            return "Adults"
        if "launch" in prompt.lower():
            return "y"
        return ""

    # _ask_multiline reads bare input() lines after printing its prompt; the
    # blank return above terminates it, so seed the idea through the printed
    # prompt instead and assert only that it was asked.
    with patch("builtins.input", _fake), \
            patch.object(harness, "WritingCouncil") as MockCouncil, \
            patch.object(harness, "save_as_manuscript", return_value="out.docx"), \
            patch.object(harness, "_ask_multiline", return_value="a fresh idea"):
        MockCouncil.return_value.run.return_value = _result()
        harness.main()
    kwargs = MockCouncil.return_value.run.call_args.kwargs
    assert kwargs["idea"] == "a fresh idea"
    assert kwargs["source_story"] == ""
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python -m pytest tests/test_consult_the_council.py tests/test_prompt_harness.py -q`
Expected: PASS (6 tests). If `main()` blocks on an unexpected `input()` call, the fake's default `""` is being consumed by a required field — add that prompt to the mapping rather than reordering the questions.

- [ ] **Step 8: Run the full suite and commit**

Run: `python -m pytest tests -q`

```bash
git add consult_the_council.py prompt_harness.py tests/test_consult_the_council.py tests/test_prompt_harness.py
git commit -m "feat: rewrite an existing story from the CLI and the prompt harness"
```

---

### Task 10: Browser UI

**Files:**
- Modify: `static/index.html` (the form around :148-152, the payload builder at :317, the result rendering near :383)
- Create: `package.json`, `tests/js/index.test.js`, `.gitignore` entry for `node_modules/`
- Test: vitest + jsdom. This repo has no JS test infrastructure today; Task 10 stands it up. Node 24 / npm 11 are available.

The page is one self-contained file with inline JS, so the tests drive it the way a browser does: load the HTML into jsdom with scripts enabled, dispatch real events, and assert on the DOM and on a stubbed `fetch`. Nothing is exported or refactored for testability.

**Interfaces:**
- Consumes: the `/run` contract from Task 8.
- Produces: nothing other tasks depend on.

Follow the existing conventions in this file: inline CSS driven by the custom properties on `body.light`, inline JS, and the `uploadedPhotos` array pattern for held-then-sent files.

- [ ] **Step 1: Add the upload control**

Above the idea field, add a file input accepting `.txt,.md,.docx`, a filename chip with an X button that clears it, a two-radio mode selector (Reimagine / Revise, Reimagine checked), and a `rewrite_notes` textarea. Wrap the mode radios and the notes box in a container that is hidden until a file is chosen, matching how the photo strip appears only when photos are held. Hold the loaded file in a module-level `uploadedStory = {data, filename}` variable, mirroring `uploadedPhotos`.

Label the radios so the difference is legible: "Reimagine — a new story on the original's bones" and "Revise — edit the original prose".

- [ ] **Step 2: Apply blank-means-blank**

When a story file is attached, clear the `target_length` and `target_audience` inputs, remove their required markers, and set their placeholders to "blank = match the original". Restore both values and the markers when the file is removed.

- [ ] **Step 3: Extend the payload**

At the payload builder (`:317`), add:

```javascript
      story_file:    uploadedStory ? {data: uploadedStory.data, filename: uploadedStory.filename} : null,
      rewrite_mode:  document.querySelector('input[name="rewrite_mode"]:checked')?.value || '',
      rewrite_notes: document.getElementById('rewrite_notes').value.trim(),
```

- [ ] **Step 4: Render the brief and backfill the title**

When the response carries `intake_brief`, render it in the result panel in the same collapsible style the planning details use. Then backfill the title input from `data.title` when it is non-empty — `/save` sends the title from the client, so without this a brief-supplied title never reaches the .docx.

- [ ] **Step 5: Stand up the JS test harness**

```bash
npm init -y
npm install --save-dev vitest@^2 jsdom@^25
```

Then set `package.json`'s scripts and remove the generated `main` field:

```json
{
  "name": "writing-council-ui-tests",
  "private": true,
  "type": "module",
  "scripts": {
    "test": "vitest run"
  }
}
```

Add `node_modules/` to `.gitignore` (create the file if the repo has none). Do **not** commit `package-lock.json` conflicts — commit the lockfile as generated.

- [ ] **Step 6: Write the UI tests**

```javascript
// tests/js/index.test.js
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const HTML = readFileSync(new URL('../../static/index.html', import.meta.url), 'utf-8');

function loadPage() {
  const dom = new JSDOM(HTML, { runScripts: 'dangerously', url: 'http://localhost:5000' });
  return dom.window;
}

/** Attach a story file the way the browser does: set files, dispatch change. */
async function attachStory(win, name = 'sforzato.txt', body = 'The fleet dropped out.') {
  const input = win.document.getElementById('story_file');
  const file = new win.File([body], name, { type: 'text/plain' });
  Object.defineProperty(input, 'files', { value: [file], configurable: true });
  input.dispatchEvent(new win.Event('change', { bubbles: true }));
  // FileReader is async; let its load event settle.
  await new Promise((resolve) => win.setTimeout(resolve, 0));
}

describe('story upload controls', () => {
  it('hides the rewrite controls until a story is attached', () => {
    const win = loadPage();
    const controls = win.document.getElementById('rewrite_controls');
    expect(controls).not.toBeNull();
    expect(controls.hidden || controls.style.display === 'none').toBe(true);
  });

  it('reveals the mode radios and notes box once a story is attached', async () => {
    const win = loadPage();
    await attachStory(win);
    const controls = win.document.getElementById('rewrite_controls');
    expect(controls.hidden || controls.style.display === 'none').toBe(false);
    expect(win.document.querySelector('input[name="rewrite_mode"]:checked').value)
      .toBe('reimagine');
  });

  it('blanks target length and audience when a story is attached', async () => {
    const win = loadPage();
    expect(win.document.getElementById('target_length').value).toBe('8,000 words');
    await attachStory(win);
    expect(win.document.getElementById('target_length').value).toBe('');
    expect(win.document.getElementById('target_audience').value).toBe('');
    expect(win.document.getElementById('target_length').required).toBe(false);
  });

  it('restores the defaults when the story is removed', async () => {
    const win = loadPage();
    await attachStory(win);
    win.document.getElementById('story_remove').click();
    expect(win.document.getElementById('target_length').value).toBe('8,000 words');
    expect(win.document.getElementById('target_audience').value).toBe('Adult sci-fi readers');
    const controls = win.document.getElementById('rewrite_controls');
    expect(controls.hidden || controls.style.display === 'none').toBe(true);
  });
});

describe('run payload', () => {
  let win;
  let sent;

  beforeEach(async () => {
    win = loadPage();
    sent = null;
    win.fetch = vi.fn(async (url, opts) => {
      sent = { url, body: JSON.parse(opts.body) };
      return {
        ok: true,
        json: async () => ({
          story: 'a story', log: [], intake_brief: '=== STORY BRIEF ===',
          rewrite_mode: 'revise', title: 'The Sforzato', target_length: '8432 words',
        }),
      };
    });
  });

  it('sends story_file, rewrite_mode, and rewrite_notes', async () => {
    await attachStory(win);
    win.document.querySelector('input[name="rewrite_mode"][value="revise"]').click();
    win.document.getElementById('rewrite_notes').value = 'darker ending';
    win.document.getElementById('run').click();
    await vi.waitFor(() => expect(sent).not.toBeNull());

    expect(sent.url).toContain('/run');
    expect(sent.body.story_file.filename).toBe('sforzato.txt');
    expect(sent.body.story_file.data).toContain('base64,');
    expect(sent.body.rewrite_mode).toBe('revise');
    expect(sent.body.rewrite_notes).toBe('darker ending');
  });

  it('omits story_file on a fresh run', async () => {
    win.document.getElementById('idea').value = 'a fresh idea';
    win.document.getElementById('run').click();
    await vi.waitFor(() => expect(sent).not.toBeNull());
    expect(sent.body.story_file).toBeFalsy();
  });

  it('renders the brief and backfills the title from the response', async () => {
    await attachStory(win);
    win.document.getElementById('run').click();
    await vi.waitFor(() =>
      expect(win.document.getElementById('title').value).toBe('The Sforzato'));
    expect(win.document.body.textContent).toContain('STORY BRIEF');
  });
});
```

Give the new elements these exact ids, since the tests address them: `story_file`, `story_remove`, `rewrite_controls`, `rewrite_notes`. The radios share `name="rewrite_mode"` with values `reimagine` and `revise`. If the existing run button or title input uses different ids than `run` and `title`, keep the page's ids and update the test file to match — do not rename existing elements.

- [ ] **Step 7: Run the JS tests**

Run: `npm test`
Expected: PASS (7 tests)

- [ ] **Step 8: Verify by hand**

Start the server (`python server.py`) and confirm the page still works in a real browser — jsdom does not catch layout or CSS mistakes:

1. Attaching a `.txt` reveals the mode radios and the notes box, and blanks the length and audience fields.
2. The X button clears the file, hides the controls, and restores both defaults.
3. With DevTools open, submitting sends `story_file`, `rewrite_mode`, and `rewrite_notes` in the payload — cancel the request once you have seen it; there is no need to let a billed run proceed.

- [ ] **Step 9: Run both suites and commit**

Run: `python -m pytest tests -q` and `npm test`

```bash
git add static/index.html package.json package-lock.json .gitignore tests/js/index.test.js
git commit -m "feat: upload a story to rewrite from the browser UI"
```

---

### Task 11: Documentation

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add a section**

Add a "Story intake and rewrite" section after "Images", covering: the two modes and what each preserves; that `IntakeAgent` produces the brief and `PlanningAgent` keeps sole authority over `<<<WORLD_CLASS>>>`; that the whole brief reaches the planner while the merge governs craft params only; the seeded `_run_inner` branch and `_run_revise_setup`; the 110k refusal and the 20k revise warning; and that revise mode skips `revise_with_world_bible`.

Update the "Running" section to mention `SOURCE_STORY_PATH` in `consult_the_council.py`.

- [ ] **Step 2: Check the length**

Run: `wc -c CLAUDE.md`
If the result is over 40,000 characters, ask whether to split sections into their own `.md` files before going further.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document story intake and rewrite in CLAUDE.md"
```

- [ ] **Step 4: Open the PR**

```bash
git push -u origin feature/story-intake-rewrite
gh pr create --base feature/prompt-harness --title "Story intake and rewrite" --body "$(cat <<'EOF'
Upload an existing story (.txt/.md/.docx) and have the council rewrite it.

- **reimagine** — a new story on the original's bones; the original prose never
  reaches the writer.
- **revise** — the original is seeded as the initial draft and run through the
  review/revise loops.

A new IntakeAgent digests the upload into a STORY BRIEF; the whole brief reaches
PlanningAgent, which keeps sole authority over the WORLD_CLASS tag that trips
non_earth. A fresh run's prompt text is unchanged.

Spec: docs/superpowers/specs/2026-08-09-story-intake-rewrite-design.md
Plan: docs/superpowers/plans/2026-08-09-story-intake-rewrite.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_019DMCveGPSieu8ixZsEJXQw
EOF
)"
```

Base the PR on `feature/prompt-harness`, the branch this work builds on — per the repo's convention of targeting the branch a feature builds on rather than a default branch. Confirm with `git log --oneline origin/feature/prompt-harness -1` that it is still the right parent before opening.
