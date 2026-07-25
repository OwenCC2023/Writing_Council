# Final Prose-Cleanup Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a final line-level prose-cleanup pass to the Writing Council pipeline: a new prose mode of the AI failure checker finds the top-N most egregious surviving prose defects, a dedicated planner mode forces all of them into section revisions, and the writer applies them — then section markers are stripped as the final step of `run()`.

**Architecture:** After the Middle loop, `run()` loops `prose_passes` (default 1) times over a new `_run_prose_pass`, which runs `ConsistencyAgent.run` and `AIFailureCheckerAgent.run_prose` in parallel, feeds both into `PlanningAgent.plan_revision_prose`, and applies the result with the existing `WriterAgent.revise`. Section-marker stripping moves out of `document_writer` and into the tail of `run()`.

**Tech Stack:** Python 3.11, Anthropic SDK, `concurrent.futures.ThreadPoolExecutor`, pytest + `unittest.mock`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-03-prose-cleanup-pass-design.md`.
- Prose reviewer scope: IN = failure-modes Part II (Voice/Style) in full + line-level Part III items; OUT = Part I structural / plot / pacing / arc.
- `run_prose` default `top_n = 5`; `run()` defaults `prose_passes = 1`, `prose_top_n = 5`.
- `plan_revision_prose` output: STRUCTURAL OPERATIONS = NONE, GENERAL NOTES = NONE, every prose finding in SECTION REVISIONS, multiple same-section fixes merged into ONE `SECTION N:` line (semicolons).
- Generic `PlanningAgent.plan_revision` is NOT modified — inner/middle loops keep funnel behavior.
- All agent classes require env `ANTHROPIC_API_KEY` at construction (creates the Anthropic client). Tests set a dummy key via an autouse fixture.
- Existing call convention: `self._call_claude(system_prompt, user_prompt)` — positional. Agent methods return `{"agent": <name>, "output": <str>}` (writer also returns `"revised_sections"`).
- Frontend check already done: `static/` does not reference `<<<SECTION>>>`; moving the strip is safe.

---

### Task 1: Test fixture for API key

Agent constructors read `os.environ["ANTHROPIC_API_KEY"]`. New unit tests instantiate real agents (mocking only `_call_claude`), so every test needs the key present. Add one autouse fixture.

**Files:**
- Create: `tests/conftest.py`

**Interfaces:**
- Produces: an autouse pytest fixture setting `ANTHROPIC_API_KEY=test-key` for all tests in `tests/`.

- [ ] **Step 1: Write the conftest**

```python
# tests/conftest.py
import pytest


@pytest.fixture(autouse=True)
def _dummy_anthropic_key(monkeypatch):
    """Every agent constructor needs an API key to build its client.
    No network call is made; a placeholder is enough for unit tests."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
```

- [ ] **Step 2: Verify existing tests still pass**

Run: `python -m pytest tests/ -q`
Expected: PASS (existing `test_server.py`, `test_document_writer.py` unaffected).

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test: add autouse ANTHROPIC_API_KEY fixture for agent unit tests"
```

---

### Task 2: `AIFailureCheckerAgent.run_prose`

New prose mode: same taxonomy, reframed as a final surviving-residue polish, reporting the top-N most egregious prose (not structural) violations.

**Files:**
- Modify: `agents/ai_failure_checker.py`
- Test: `tests/test_ai_failure_checker.py` (create)

**Interfaces:**
- Consumes: `BaseAgent._call_claude(system_prompt, user_prompt)`, `DEFAULT_FAILURE_MODES_PATH`.
- Produces: `AIFailureCheckerAgent.run_prose(story: str, top_n: int = 5, failure_modes_path: str | Path = None) -> dict` returning `{"agent": "AIFailureCheckerAgent", "output": str}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ai_failure_checker.py
from unittest.mock import patch

from agents.ai_failure_checker import AIFailureCheckerAgent


def test_run_prose_returns_expected_shape():
    agent = AIFailureCheckerAgent()
    with patch.object(agent, "_call_claude", return_value="1. AI dialect — ...") as m:
        result = agent.run_prose(story="<<<SECTION 1>>>\nHello there.", top_n=5)
    assert result == {"agent": "AIFailureCheckerAgent", "output": "1. AI dialect — ..."}
    m.assert_called_once()


def test_run_prose_prompt_carries_scope_framing_and_top_n():
    agent = AIFailureCheckerAgent()
    with patch.object(agent, "_call_claude", return_value="x") as m:
        agent.run_prose(story="<<<SECTION 1>>>\nHi.", top_n=3)
    system_prompt = m.call_args.args[0]
    user_prompt = m.call_args.args[1]
    assert "surviv" in system_prompt.lower()        # residue framing
    assert "OUT OF SCOPE" in system_prompt           # structural exclusion
    assert "3" in system_prompt                      # top_n injected into system
    assert "3" in user_prompt                        # and into user ask
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ai_failure_checker.py -v`
Expected: FAIL with `AttributeError: 'AIFailureCheckerAgent' object has no attribute 'run_prose'`.

- [ ] **Step 3: Add the prose prompt template and method**

Append to `agents/ai_failure_checker.py` (after the existing `SYSTEM_PROMPT_TEMPLATE`, before the class define the template; add the method inside the class):

```python
PROSE_SYSTEM_PROMPT_TEMPLATE = """\
You are a line-level prose editor performing a FINAL polish pass. The story below \
has already been through multiple structural and stylistic revision rounds. Your job \
is NOT a fresh full audit — it is to catch the line-level prose defects that SURVIVED \
those passes: the sentences a reader trips over.

You are working from this taxonomy of AI writing failure modes:

---
{failure_modes}
---

SCOPE:
- IN SCOPE — prose-level failures only: Part II (Voice and Style) in full, plus the \
  line-level items in Part III (self-congratulatory simile, characterological action \
  simile, described insight, credentialed perception, scene as caption, dialogue as \
  exposition).
- OUT OF SCOPE — structural failures: Part I (compressed arc, premature resolution, \
  three-act skeleton, symmetrical structure) and anything about plot, pacing, or arc. \
  Do not report these; the story's structure is fixed.

Report the {top_n} MOST EGREGIOUS prose violations, ranked most-damaging first. If \
fewer than {top_n} genuine violations exist, report only those — do not pad the list.

For each violation:
- Name the failure mode.
- Quote the exact offending passage.
- Cite the <<<SECTION N>>> number it appears in. Only report violations inside a \
  numbered section — ignore any text before <<<SECTION 1>>>, which cannot be revised.
- Give a concrete fix direction (usually: cut, or the specific rewrite).

Output the ranked list and nothing else. No preamble, no separate priority summary — \
the order IS the priority.\
"""
```

Method (inside `AIFailureCheckerAgent`, after `run`):

```python
    def run_prose(self, story: str, top_n: int = 5,
                  failure_modes_path: str | Path = None) -> dict:
        path = Path(failure_modes_path) if failure_modes_path else DEFAULT_FAILURE_MODES_PATH
        failure_modes = path.read_text(encoding="utf-8")

        system_prompt = PROSE_SYSTEM_PROMPT_TEMPLATE.format(
            failure_modes=failure_modes, top_n=top_n
        )
        user_prompt = (
            f"STORY:\n{story}\n\n"
            f"Identify the {top_n} most egregious surviving prose violations."
        )
        output = self._call_claude(system_prompt, user_prompt)
        return {"agent": "AIFailureCheckerAgent", "output": output}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_ai_failure_checker.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add agents/ai_failure_checker.py tests/test_ai_failure_checker.py
git commit -m "feat: add AIFailureCheckerAgent.run_prose line-level polish mode"
```

---

### Task 3: `PlanningAgent.plan_revision_prose`

New planner mode that turns prose findings into a forced-all section-revision plan, pinning STRUCTURAL OPERATIONS and GENERAL NOTES to NONE and merging same-section fixes into one line.

**Files:**
- Modify: `agents/planning_agent.py`
- Test: `tests/test_planning_agent.py` (create)

**Interfaces:**
- Consumes: `BaseAgent._call_claude`, `re` (already imported in the module).
- Produces: `PlanningAgent.plan_revision_prose(story: str, plan: str, prose_feedback: str, consistency_feedback: str) -> dict` returning `{"agent": "PlanningAgent", "output": str}` (three-block format).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_planning_agent.py
from unittest.mock import patch

from agents.planning_agent import PlanningAgent

_THREE_BLOCK = (
    "=== STRUCTURAL OPERATIONS ===\nNONE\n"
    "=== SECTION REVISIONS ===\nSECTION 1: cut the simile\n"
    "=== GENERAL NOTES ===\nNONE"
)


def test_plan_revision_prose_returns_expected_shape():
    agent = PlanningAgent()
    with patch.object(agent, "_call_claude", return_value=_THREE_BLOCK):
        result = agent.plan_revision_prose(
            story="<<<SECTION 1>>>\nHi.",
            plan="the plan",
            prose_feedback="1. AI dialect in section 1",
            consistency_feedback="no issues",
        )
    assert result == {"agent": "PlanningAgent", "output": _THREE_BLOCK}


def test_plan_revision_prose_prompt_carries_force_and_pins():
    agent = PlanningAgent()
    with patch.object(agent, "_call_claude", return_value="x") as m:
        agent.plan_revision_prose(
            story="<<<SECTION 1>>>\nHi.", plan="p",
            prose_feedback="findings", consistency_feedback="cons",
        )
    system_prompt = m.call_args.args[0]
    user_prompt = m.call_args.args[1]
    assert "FORCE ALL FIXES" in system_prompt
    assert "ONE LINE PER SECTION" in system_prompt
    assert "STRUCTURAL OPERATIONS is always NONE" in system_prompt
    assert "GENERAL NOTES is always NONE" in system_prompt
    assert "findings" in user_prompt        # prose feedback threaded in
    assert "cons" in user_prompt            # consistency feedback threaded in
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_planning_agent.py -v`
Expected: FAIL with `AttributeError: 'PlanningAgent' object has no attribute 'plan_revision_prose'`.

- [ ] **Step 3: Add the prose revision-plan prompt and method**

Add to `agents/planning_agent.py` after `REVISION_PLAN_SYSTEM_PROMPT`:

```python
PROSE_REVISION_PLAN_SYSTEM_PROMPT = """\
You are a story architect converting a prose editor's findings into a structured \
revision plan for a writer. This is a final line-level polish pass.

The draft uses <<<SECTION N>>> markers. All instructions reference sections by their \
current marker number as it appears in the draft.

Your output MUST follow this exact format — no text outside these three blocks:

=== STRUCTURAL OPERATIONS ===
NONE

=== SECTION REVISIONS ===
One per line:
  SECTION N: [specific instruction for what to change and why]

=== GENERAL NOTES ===
NONE

HARD RULES FOR THIS PASS:
- STRUCTURAL OPERATIONS is always NONE. Do not move or merge sections this pass.
- GENERAL NOTES is always NONE. Every fix maps to a numbered section.
- FORCE ALL FIXES: every prose violation in the PROSE FINDINGS list MUST appear as a \
  SECTION revision. Do not omit, downrank, or second-guess any of them — the list is a \
  fix list, not a candidate pool.
- ONE LINE PER SECTION: if multiple violations fall in the same section, combine them \
  into a SINGLE `SECTION N:` line, separating the individual fixes with semicolons. \
  NEVER write two lines for the same section — the second silently overwrites the first, \
  dropping a required fix.
- Be concrete and self-contained: the writer sees ONLY that section's text and your \
  instruction, not the findings or the rest of the draft. Quote the exact phrase to cut \
  or change and state the replacement or the effect it must achieve. Prefer CUT over \
  rework for stylistic tics.
- CONSISTENCY notes: fold any consistency finding that is a text-level continuity fix \
  (a name, a date, a timeline detail) into the relevant SECTION line as an added clause. \
  Drop any consistency finding that would require moving or merging sections — structure \
  is out of scope this pass.\
"""
```

Method (inside `PlanningAgent`, after `plan_revision`):

```python
    def plan_revision_prose(self, story: str, plan: str,
                            prose_feedback: str, consistency_feedback: str) -> dict:
        """Turn prose-editor findings into a forced-all section revision plan.

        Every prose finding must become a SECTION revision; structural ops and
        general notes are pinned to NONE. Used only by the final prose pass.
        """
        section_nums = sorted(int(m) for m in re.findall(r'<<<SECTION\s+(\d+)>>>', story))
        section_list = (
            f"Current sections in draft: {', '.join(str(n) for n in section_nums)}"
            if section_nums
            else "Current sections in draft: (no section markers found)"
        )
        user_prompt = (
            f"ORIGINAL PLAN:\n{plan}\n\n"
            f"CURRENT DRAFT:\n{story}\n\n"
            f"{section_list}\n\n"
            f"PROSE FINDINGS (every one MUST be fixed):\n{prose_feedback}\n\n"
            f"CONSISTENCY NOTES (fold in text-level fixes only):\n{consistency_feedback}\n\n"
            "Produce the structured revision plan using the exact format specified."
        )
        output = self._call_claude(PROSE_REVISION_PLAN_SYSTEM_PROMPT, user_prompt)
        return {"agent": "PlanningAgent", "output": output}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_planning_agent.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add agents/planning_agent.py tests/test_planning_agent.py
git commit -m "feat: add PlanningAgent.plan_revision_prose forced-all revision mode"
```

---

### Task 4: Guard the same-section overwrite hazard in the writer parser

No code change to the writer — this task locks in the contract the prose planner prompt must honor: one semicolon-packed line per section survives; two lines for the same section overwrite. These characterization tests fail loudly if `_parse_section_revisions` behavior ever changes.

**Files:**
- Test: `tests/test_writer_agent.py` (create)

**Interfaces:**
- Consumes: `WriterAgent._parse_revision_plan(revision_plan) -> (structural_ops, section_revisions, general_notes)`.

- [ ] **Step 1: Write the tests**

```python
# tests/test_writer_agent.py
from agents.writer_agent import WriterAgent


def test_single_line_semicolon_fixes_both_survive():
    """The prose planner packs multiple same-section fixes into one line —
    confirm both survive parsing."""
    agent = WriterAgent()
    _ops, revisions, _notes = agent._parse_revision_plan(
        "=== STRUCTURAL OPERATIONS ===\nNONE\n"
        "=== SECTION REVISIONS ===\n"
        "SECTION 3: cut the simile in paragraph 2; delete the final sentence\n"
        "=== GENERAL NOTES ===\nNONE"
    )
    assert 3 in revisions
    assert "cut the simile" in revisions[3]
    assert "delete the final sentence" in revisions[3]


def test_two_lines_same_section_second_overwrites_first():
    """Documents the hazard the prose prompt must avoid: a second SECTION 3
    line silently replaces the first."""
    agent = WriterAgent()
    _ops, revisions, _notes = agent._parse_revision_plan(
        "=== STRUCTURAL OPERATIONS ===\nNONE\n"
        "=== SECTION REVISIONS ===\n"
        "SECTION 3: fix A\n"
        "SECTION 3: fix B\n"
        "=== GENERAL NOTES ===\nNONE"
    )
    assert revisions[3] == "fix B"
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `python -m pytest tests/test_writer_agent.py -v`
Expected: PASS (both — this documents existing behavior).

- [ ] **Step 3: Commit**

```bash
git add tests/test_writer_agent.py
git commit -m "test: characterize same-section revision parsing (force-all-N guard)"
```

---

### Task 5: Orchestrator — `_run_prose_pass`, `_strip_section_markers`, `run()` wiring

Add the prose pass, the marker-strip helper, and wire both into `run()` with the new params.

**Files:**
- Modify: `orchestrator.py` (`run` signature + tail; new methods)
- Test: `tests/test_orchestrator.py` (create)

**Interfaces:**
- Consumes: `PlanningAgent.plan_revision_prose`, `AIFailureCheckerAgent.run_prose`, `ConsistencyAgent.run`, `WriterAgent.revise`, existing `_log_start`/`_log_end`, `ThreadPoolExecutor`, `re`.
- Produces:
  - `WritingCouncil._run_prose_pass(plan: str, story: str, top_n: int = 5, label: str = "prose") -> str` (returns revised story).
  - `WritingCouncil._strip_section_markers(story: str) -> str` (staticmethod).
  - `run(..., prose_passes: int = 1, prose_top_n: int = 5)` — returns a marker-free story.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_orchestrator.py
from unittest.mock import MagicMock

from orchestrator import WritingCouncil


def test_strip_section_markers_removes_markers_keeps_prose():
    council = WritingCouncil()
    story = "<<<SECTION 1>>>\nHello.\n\n<<<SECTION 2>>>\nWorld."
    out = council._strip_section_markers(story)
    assert "<<<SECTION" not in out
    assert "Hello." in out and "World." in out


def test_run_prose_pass_calls_agents_in_order():
    council = WritingCouncil()
    council.consistency.run = MagicMock(
        return_value={"agent": "ConsistencyAgent", "output": "cons"})
    council.ai_checker.run_prose = MagicMock(
        return_value={"agent": "AIFailureCheckerAgent", "output": "prose"})
    council.planner.plan_revision_prose = MagicMock(
        return_value={"agent": "PlanningAgent", "output": "revplan"})
    council.writer.revise = MagicMock(
        return_value={"agent": "WriterAgent", "output": "final", "revised_sections": None})

    out = council._run_prose_pass(plan="plan", story="story", top_n=5, label="prose.1")

    assert out == "final"
    council.ai_checker.run_prose.assert_called_once_with(story="story", top_n=5)
    council.consistency.run.assert_called_once_with(story="story")
    council.planner.plan_revision_prose.assert_called_once_with(
        story="story", plan="plan", prose_feedback="prose", consistency_feedback="cons")
    council.writer.revise.assert_called_once_with(
        plan="plan", story="story", feedback="revplan")


def test_run_applies_one_prose_pass_and_strips_markers():
    council = WritingCouncil()
    council._run_inner = MagicMock(return_value=("plan", "<<<SECTION 1>>>\nDraft."))
    council._run_middle = MagicMock(return_value="<<<SECTION 1>>>\nMiddle.")
    council._run_prose_pass = MagicMock(return_value="<<<SECTION 1>>>\nProse out.")

    result = council.run(idea="i", target_length="1k", target_audience="a")

    assert council._run_prose_pass.call_count == 1
    assert "<<<SECTION" not in result["story"]
    assert "Prose out." in result["story"]


def test_run_respects_prose_passes_and_top_n():
    council = WritingCouncil()
    council._run_inner = MagicMock(return_value=("plan", "s"))
    council._run_middle = MagicMock(return_value="s")
    council._run_prose_pass = MagicMock(
        side_effect=lambda plan, story, top_n, label: story + "+")

    result = council.run(idea="i", target_length="1k", target_audience="a",
                         prose_passes=3, prose_top_n=7)

    assert council._run_prose_pass.call_count == 3
    assert council._run_prose_pass.call_args.kwargs["top_n"] == 7
    assert "<<<SECTION" not in result["story"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_orchestrator.py -v`
Expected: FAIL — `AttributeError: ... has no attribute '_strip_section_markers'` / `_run_prose_pass`, and `run()` does not yet accept `prose_passes`.

- [ ] **Step 3: Add the two new methods**

In `orchestrator.py`, add inside `WritingCouncil` after `_run_middle` (before the `_extract_sections_text` section helper):

```python
    # ------------------------------------------------------------------
    # Final prose-cleanup pass: (4 ∥ 3_prose) → 1(plan_revision_prose) → 2
    # ------------------------------------------------------------------
    def _run_prose_pass(self, plan: str, story: str, top_n: int = 5,
                        label: str = "prose") -> str:
        """One line-level polish pass. Runs consistency + prose-mode checker in
        parallel, forces all prose findings into a section-revision plan, and
        applies it. Returns the revised story (markers intact)."""
        print(f"[{label}] Running ConsistencyAgent and AIFailureCheckerAgent "
              f"(prose mode, top {top_n}) in parallel...")
        self._log_start(f"{label}.consistency", "ConsistencyAgent")
        self._log_start(f"{label}.prose_check", "AIFailureCheckerAgent")
        with ThreadPoolExecutor(max_workers=2) as executor:
            f_cons = executor.submit(self.consistency.run, story=story)
            f_prose = executor.submit(self.ai_checker.run_prose, story=story, top_n=top_n)
            cons_result = f_cons.result()
            prose_result = f_prose.result()
        self._log_end(cons_result, step=f"{label}.consistency")
        self._log_end(prose_result, step=f"{label}.prose_check")

        print(f"[{label}] Running PlanningAgent (prose revision plan)...")
        self._log_start(f"{label}.plan_revision", "PlanningAgent")
        plan_result = self.planner.plan_revision_prose(
            story=story,
            plan=plan,
            prose_feedback=prose_result["output"],
            consistency_feedback=cons_result["output"],
        )
        self._log_end(plan_result, step=f"{label}.plan_revision")
        revision_plan = plan_result["output"]

        print(f"[{label}] Running WriterAgent (prose revise)...")
        self._log_start(f"{label}.write", "WriterAgent")
        write_result = self.writer.revise(plan=plan, story=story, feedback=revision_plan)
        self._log_end(write_result, step=f"{label}.write")
        return write_result["output"]

    @staticmethod
    def _strip_section_markers(story: str) -> str:
        """Remove <<<SECTION N>>> markers. Called once at the end of run(),
        after all prose passes — the passes need the markers intact."""
        return re.sub(r'<<<SECTION\s+\d+>>>\n?', '', story)
```

- [ ] **Step 4: Wire the prose loop into `run()`**

In `orchestrator.py`, change the `run` signature to add the two params:

```python
    def run(
        self,
        idea: str,
        target_length: str,
        target_audience: str,
        world_rules: str = "",
        framework: str = "",
        style: str = "",
        image: str = "",
        prose_passes: int = 1,
        prose_top_n: int = 5,
    ) -> dict:
```

Then replace the tail of `run()` — the current:

```python
        # Middle
        print("[outer] Starting middle loop...")
        story = self._run_middle(plan, story, target_audience)

        return {"story": story, "log": list(self._log)}
```

with:

```python
        # Middle
        print("[outer] Starting middle loop...")
        story = self._run_middle(plan, story, target_audience)

        # Final prose-cleanup pass(es)
        for i in range(prose_passes):
            print(f"[outer] Starting prose-cleanup pass {i + 1}/{prose_passes}...")
            story = self._run_prose_pass(
                plan, story, top_n=prose_top_n, label=f"prose.{i + 1}")

        # Section markers survive until here (the prose passes need them); strip last.
        story = self._strip_section_markers(story)
        return {"story": story, "log": list(self._log)}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_orchestrator.py -v`
Expected: PASS (all four).

Note: `test_run_*` tests call the real `run()`, which writes an empty log file under `logs/`. That is expected and harmless.

- [ ] **Step 6: Commit**

```bash
git add orchestrator.py tests/test_orchestrator.py
git commit -m "feat: add final prose-cleanup pass and move marker strip into run()"
```

---

### Task 6: Remove marker stripping from `document_writer`

Markers are now stripped in `run()`. Remove the redundant strip (and its now-unused `import re`) from `document_writer.py`, and add a regression test proving a marker-free story still saves cleanly.

**Files:**
- Modify: `document_writer.py` (delete line `import re`; delete the `re.sub` strip line)
- Test: `tests/test_document_writer.py` (add one test)

**Interfaces:**
- Consumes: `document_writer.save_as_manuscript(story, title, author, output)`.

- [ ] **Step 1: Add the regression test**

Append to `tests/test_document_writer.py`:

```python
def test_save_as_manuscript_handles_marker_free_story():
    """run() now strips <<<SECTION>>> markers before document_writer sees the
    story. Confirm a marker-free story still produces a valid .docx."""
    import io
    from document_writer import save_as_manuscript

    buf = io.BytesIO()
    save_as_manuscript(
        story="First paragraph.\n\nSecond paragraph.",
        title="Test",
        author="Author",
        output=buf,
    )
    assert buf.getvalue()[:4] == b"PK\x03\x04"   # .docx is a ZIP
```

- [ ] **Step 2: Run the test (passes before the change too)**

Run: `python -m pytest tests/test_document_writer.py::test_save_as_manuscript_handles_marker_free_story -v`
Expected: PASS (marker-free input already works).

- [ ] **Step 3: Remove the strip and unused import**

In `document_writer.py`:
- Delete line 2: `import re`.
- Delete the body-paragraph strip line: `story = re.sub(r'<<<SECTION\s+\d+>>>\n?', '', story)`.

The `# --- Body paragraphs ---` block then begins directly with:

```python
    # --- Body paragraphs ---
    chunks = [c.strip() for c in story.split("\n\n") if c.strip()]
```

- [ ] **Step 4: Run the full test suite**

Run: `python -m pytest tests/ -q`
Expected: PASS (all tests, including the new regression and existing document-writer tests).

- [ ] **Step 5: Commit**

```bash
git add document_writer.py tests/test_document_writer.py
git commit -m "refactor: move section-marker stripping out of document_writer into run()"
```

---

### Task 7: Full-suite verification

- [ ] **Step 1: Run everything**

Run: `python -m pytest tests/ -v`
Expected: PASS — `test_ai_failure_checker.py` (2), `test_planning_agent.py` (2), `test_writer_agent.py` (2), `test_orchestrator.py` (4), `test_document_writer.py` (existing + 1), `test_server.py` (existing).

- [ ] **Step 2: Confirm no stray `re.sub` marker strip remains outside `orchestrator.py`**

Run: `grep -rn "SECTION" document_writer.py`
Expected: no output (marker handling fully removed from `document_writer`).

---

## Notes for the implementer

- Do NOT touch the generic `PlanningAgent.plan_revision` or the existing inner/middle loop code — the prose mode is additive.
- Keep the `_call_claude` calls positional (`system_prompt, user_prompt`) to match every other agent and the tests' `call_args.args[0/1]` assertions.
- `prose_passes`/`prose_top_n` are not surfaced in `server.py`/CLI in this plan (spec Non-Goal). Existing callers keep working on defaults.
