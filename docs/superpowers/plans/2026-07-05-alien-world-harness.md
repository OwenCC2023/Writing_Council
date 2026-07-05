# Alien-World Quality Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the world being written is out-of-distribution ("alien"), front-load it into a precomputed world-bible + canon sheet and recalibrate the pipeline (higher models, inverted reviewers, world-aware feedback) so prose quality stops degrading with world strangeness.

**Architecture:** A `non_earth` flag, classified by the planner, gates a set of otherwise-inert additions: a WorldBuilder stage (bible + canon), a bible-informed plan rewrite, Opus on all writer passes, two new Inner-loop reviewers (strangeness + sensory), and canon-aware recalibration of the six existing reviewers. Every addition is conditional — an EARTH run is byte-for-byte today's pipeline.

**Tech Stack:** Python 3.11, `anthropic` SDK, `pytest` + `unittest.mock` (all tests mock LLM calls — no real API calls, ever).

## Global Constraints

- **No real API calls in tests.** Mock every `_call_claude` / `_call_claude_with_image` / agent `.run` with `unittest.mock`. (Existing convention.)
- **EARTH byte-identical guard.** All new prompt text (reviewer canon + bucketing, planner revision bucket-handling, writer blacklist injection) is injected *only* when a non-empty `canon_sheet` is present. With `canon_sheet=""` every prompt string must equal today's exactly — trailing spaces, newlines, and the escaped-newline (`"""\`) string style included.
- **Model IDs** (from `agents/base_agent.py`): `DEFAULT_MODEL = "claude-sonnet-4-6"`, `FEEDBACK_MODEL = "claude-haiku-4-5-20251001"`, `INITIAL_DRAFT_MODEL = "claude-opus-4-8"`. Opus for WorldBuilder, bible-revision, and all writer passes when `non_earth`. Sonnet (`DEFAULT_MODEL`) for the two new reviewers.
- **Section markers** are `<<<SECTION N>>>`; the classification tag is `<<<WORLD_CLASS: EARTH|NON-EARTH>>>`. Strip the class tag from the plan before it goes downstream.
- **Prompt style:** module-level string constants, `"""\` escaped-newline style, matching every existing agent file.
- **Commit after every task.** Branch: `feature/alien-world-harness` (already created).

---

## File Structure

**New files:**
- `trope_blacklist.md` — repo-root stub, injected like `ai_writing_failure_modes.md`.
- `agents/world_builder_agent.py` — `WorldBuilderAgent`: plan text → canon sheet + world-bible.
- `agents/world_calibration.py` — shared helpers/constants for canon injection + bucketing (DRY across six reviewers).
- `agents/strangeness_agent.py` — `StrangenessReviewerAgent`: inverted reviewer (too-tame detector).
- `agents/sensory_agent.py` — `SensoryQuotaAgent`: abstraction-noun ban + sensory-density report.
- Test files: `tests/test_world_builder_agent.py`, `tests/test_world_calibration.py`, `tests/test_strangeness_agent.py`, `tests/test_sensory_agent.py`.

**Modified files:**
- `agents/planning_agent.py` — classification+chunking addendum; `revise_with_world_bible`; bucket-handling in `plan_revision`/`plan_revision_prose`.
- `agents/writer_agent.py` — `canon_sheet`/`world_bible`/`model` params on `run`+`revise`; gated blacklist injection.
- `agents/consistency_agent.py`, `ai_failure_checker.py`, `peer_writer_agent.py`, `editor_agent.py`, `marketing_agent.py`, `audience_agent.py` — optional `canon_sheet` param via the shared helper.
- `agents/__init__.py` — export the three new agents.
- `orchestrator.py` — classify/parse/strip, `non_earth` propagation, WorldBuilder + bible-revision in initial inner, 4-way fan-out, thread canon/bible/model everywhere, prose-pass canon.
- `server.py` — surface `non_earth` in the response (minor).
- `tests/test_orchestrator.py` — update mocks for the new `_run_inner` return shape.

---

## Task 1: Trope blacklist stub + WorldBuilderAgent

**Files:**
- Create: `trope_blacklist.md`
- Create: `agents/world_builder_agent.py`
- Modify: `agents/__init__.py`
- Test: `tests/test_world_builder_agent.py`

**Interfaces:**
- Produces: `WorldBuilderAgent().run(idea: str, plan: str, world_rules: str = "", blacklist_path=None) -> {"agent","output","canon_sheet","world_bible"}`. Model defaults to `INITIAL_DRAFT_MODEL`. Output text has `=== CANON SHEET ===` first, `=== WORLD BIBLE ===` second; `run` splits them into `canon_sheet` / `world_bible`.

- [ ] **Step 1: Create the blacklist stub**

`trope_blacklist.md`:
```markdown
# Trope Blacklist

Default science-fiction and fantasy clichés the world-builder and writer must avoid.
This list is intentionally minimal for now; add entries over time.

- (none yet)
```

- [ ] **Step 2: Write the failing test**

`tests/test_world_builder_agent.py`:
```python
from unittest.mock import patch
from agents.world_builder_agent import WorldBuilderAgent
from agents.base_agent import INITIAL_DRAFT_MODEL


def test_run_splits_canon_and_bible_and_uses_opus():
    fake = (
        "=== CANON SHEET ===\n"
        "Gravity is half Earth-normal.\n"
        "=== WORLD BIBLE ===\n"
        "The air smells of hot iron and ozone.\n"
    )
    agent = WorldBuilderAgent()
    with patch.object(agent, "_call_claude", return_value=fake) as m:
        result = agent.run(idea="i", plan="PLAN TEXT", world_rules="low gravity")

    assert "Gravity is half Earth-normal." in result["canon_sheet"]
    assert "Gravity is half Earth-normal." not in result["world_bible"]
    assert "hot iron and ozone" in result["world_bible"]
    assert "===" not in result["canon_sheet"]
    # Opus, with headroom above the 8192 default so neither block truncates.
    assert m.call_args.kwargs["model"] == INITIAL_DRAFT_MODEL
    assert m.call_args.kwargs["max_tokens"] > 8192


def test_run_handles_missing_bible_header_gracefully():
    agent = WorldBuilderAgent()
    with patch.object(agent, "_call_claude", return_value="=== CANON SHEET ===\nRule."):
        result = agent.run(idea="i", plan="p")
    assert "Rule." in result["canon_sheet"]
    assert result["world_bible"] == ""
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_world_builder_agent.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'agents.world_builder_agent'`.

- [ ] **Step 4: Implement the agent**

`agents/world_builder_agent.py`:
```python
import re
from pathlib import Path
from .base_agent import BaseAgent, INITIAL_DRAFT_MODEL

DEFAULT_BLACKLIST_PATH = Path(__file__).parent.parent / "trope_blacklist.md"
WORLD_BUILDER_MAX_TOKENS = 16000  # bible is intentionally dense; keep both blocks intact

SYSTEM_PROMPT_TEMPLATE = """\
You are a world-builder. You are given a story idea and a narrative plan set in a world \
that is NOT contemporary Earth. Your job is to precompute that world so a writer never has \
to invent it mid-sentence. Produce two artifacts, in this exact order and with these exact \
delimiters, and NOTHING else:

=== CANON SHEET ===
A short, authoritative list of the world's load-bearing rules: physics that differ from \
Earth, biology, technology level, social structure, what characters can and cannot do. \
Each rule one concrete, usable line (e.g. "Noon light is deep red; shadows point three \
ways from the three suns"). This block is threaded into every later stage; keep it tight.

=== WORLD BIBLE ===
A dense bank of CONCRETE SENSORY detail this world affords: textures, smells, sounds, \
temperatures, weights, the feel of daily objects, what bodies do here. Not rules — raw \
specific material the writer draws from so prose stays grounded instead of abstract. Anchor \
every entry to a human-legible sensation, then distort it; do not describe things as merely \
"strange" or "otherworldly".

Avoid the clichés in this blacklist:
---
{blacklist}
---

Emit the CANON SHEET block first so it is never at risk of truncation. Use the two \
delimiter lines verbatim.\
"""


class WorldBuilderAgent(BaseAgent):
    """Precomputes an out-of-distribution world into a canon sheet + world-bible."""

    def __init__(self, model: str = INITIAL_DRAFT_MODEL):
        super().__init__(model=model)

    def run(self, idea: str, plan: str, world_rules: str = "",
            blacklist_path=None) -> dict:
        path = Path(blacklist_path) if blacklist_path else DEFAULT_BLACKLIST_PATH
        blacklist = path.read_text(encoding="utf-8")
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(blacklist=blacklist)
        user_prompt = (
            f"IDEA:\n{idea}\n\n"
            f"NARRATIVE PLAN (already contains any image-derived WORLD DEDUCTION):\n{plan}\n\n"
            f"WORLD RULES (text):\n{world_rules or '(none)'}\n\n"
            "Produce the CANON SHEET and WORLD BIBLE."
        )
        output = self._call_claude(system_prompt, user_prompt,
                                   model=self.model, max_tokens=WORLD_BUILDER_MAX_TOKENS)
        canon_sheet, world_bible = self._split(output)
        return {"agent": "WorldBuilderAgent", "output": output,
                "canon_sheet": canon_sheet, "world_bible": world_bible}

    @staticmethod
    def _split(text: str) -> tuple:
        """Split on the two headers. Returns (canon_sheet, world_bible)."""
        canon = re.search(
            r'===\s*CANON SHEET\s*===\s*(.*?)(?===\s*WORLD BIBLE\s*===|$)',
            text, re.IGNORECASE | re.DOTALL)
        bible = re.search(
            r'===\s*WORLD BIBLE\s*===\s*(.*)$', text, re.IGNORECASE | re.DOTALL)
        return (canon.group(1).strip() if canon else text.strip(),
                bible.group(1).strip() if bible else "")
```

- [ ] **Step 5: Export it**

In `agents/__init__.py`, add `from .world_builder_agent import WorldBuilderAgent` with the other imports and `"WorldBuilderAgent",` to `__all__`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_world_builder_agent.py -q`
Expected: PASS (2 passed).

- [ ] **Step 7: Commit**

```bash
git add trope_blacklist.md agents/world_builder_agent.py agents/__init__.py tests/test_world_builder_agent.py
git commit -m "feat: add WorldBuilderAgent + trope blacklist stub"
```

---

## Task 2: Shared canon-calibration helper

**Files:**
- Create: `agents/world_calibration.py`
- Test: `tests/test_world_calibration.py`

**Interfaces:**
- Produces: `with_canon(base_prompt: str, canon_sheet: str, lower_authority: bool = True) -> str`. Returns `base_prompt` UNCHANGED when `canon_sheet` is falsy. When present, appends a canon block + `[CRAFT]`/`[WORLD]` bucketing instructions; `lower_authority=False` (for PeerWriter) omits the authority-lowering clause.

- [ ] **Step 1: Write the failing test**

`tests/test_world_calibration.py`:
```python
from agents.world_calibration import with_canon


def test_empty_canon_returns_base_prompt_unchanged():
    base = "You are a reviewer.\\nDo your job."
    assert with_canon(base, "") == base
    assert with_canon(base, "", lower_authority=False) == base


def test_canon_present_appends_rules_and_bucketing():
    out = with_canon("BASE", "Gravity is halved.")
    assert out.startswith("BASE")
    assert "Gravity is halved." in out
    assert "[CRAFT]" in out and "[WORLD]" in out
    assert "authority" in out.lower()


def test_peer_variant_omits_authority_lowering():
    out = with_canon("BASE", "Rule.", lower_authority=False)
    assert "[WORLD]" in out            # still buckets + judges against world
    assert "lower your authority" not in out.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_world_calibration.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`agents/world_calibration.py`:
```python
"""Shared helpers for making reviewers world-aware when a canon sheet exists.

The whole point is conditional injection: with no canon sheet the caller's prompt is
returned byte-for-byte unchanged, so EARTH runs keep today's exact prompt strings.
"""

_CANON_HEADER = """\


---
WORLD CANON (authoritative rules for THIS world — judge against this world's normal, \
not Earth's):
{canon}
---

This world is deliberately unlike Earth. Prose that reads "strange" may be correct, not a \
defect. Tag every finding you report with one of two buckets:
- [CRAFT]: a genuine craft flaw (rhythm, grammar, clarity, an actual continuity \
  contradiction, an AI tic). These get fixed.
- [WORLD]: the passage only reads odd because it commits to a canon rule. This is usually \
  authorial intent, not a bug.\
"""

_AUTHORITY_CLAUSE = """
Near world-elements, lower your authority: do not demand that intentional strangeness be \
normalized. Keep full authority on rhythm, grammar, and clarity.\
"""


def with_canon(base_prompt: str, canon_sheet: str, lower_authority: bool = True) -> str:
    """Append canon + bucketing to base_prompt, or return it unchanged if no canon."""
    if not canon_sheet:
        return base_prompt
    block = _CANON_HEADER.format(canon=canon_sheet)
    if lower_authority:
        block += _AUTHORITY_CLAUSE
    return base_prompt + block
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_world_calibration.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add agents/world_calibration.py tests/test_world_calibration.py
git commit -m "feat: add shared canon-calibration helper (with_canon)"
```

---

## Task 3: Planner classification + chunking + tag parsing

**Files:**
- Modify: `agents/planning_agent.py` (add classification addendum to `SYSTEM_PROMPT` usage in `run`)
- Modify: `orchestrator.py` (add `_parse_world_class` static helper — parse only, wiring comes in Task 9)
- Test: `tests/test_planning_agent.py`, `tests/test_orchestrator.py`

**Interfaces:**
- Produces: `WritingCouncil._parse_world_class(plan: str) -> (non_earth: bool, stripped_plan: str)`. Matches `<<<WORLD_CLASS: EARTH|NON-EARTH>>>` (case-insensitive), returns whether it was NON-EARTH and the plan with the tag line removed. Missing tag → `(False, plan)`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_orchestrator.py`:
```python
def test_parse_world_class_non_earth():
    council = WritingCouncil()
    plan = "<<<WORLD_CLASS: NON-EARTH>>>\n<<<SECTION 1>>>\nBody."
    non_earth, stripped = council._parse_world_class(plan)
    assert non_earth is True
    assert "WORLD_CLASS" not in stripped
    assert stripped.startswith("<<<SECTION 1>>>")


def test_parse_world_class_earth_and_missing():
    council = WritingCouncil()
    assert council._parse_world_class("<<<WORLD_CLASS: EARTH>>>\nx")[0] is False
    non_earth, stripped = council._parse_world_class("no tag here")
    assert non_earth is False and stripped == "no tag here"
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_orchestrator.py::test_parse_world_class_non_earth -q`
Expected: FAIL — `AttributeError: 'WritingCouncil' object has no attribute '_parse_world_class'`.

- [ ] **Step 3: Add the parse helper to `orchestrator.py`**

Add as a `@staticmethod` on `WritingCouncil` (near `_strip_section_markers`):
```python
    @staticmethod
    def _parse_world_class(plan: str) -> tuple:
        """Return (non_earth, plan_without_tag). Missing tag → (False, plan)."""
        m = re.search(r'<<<WORLD_CLASS:\s*(EARTH|NON-EARTH)>>>\n?', plan, re.IGNORECASE)
        if not m:
            return False, plan
        non_earth = m.group(1).upper() == "NON-EARTH"
        return non_earth, plan[:m.start()] + plan[m.end():]
```

- [ ] **Step 4: Add the classification addendum in `planning_agent.py`**

Add a module-level constant and append it to the system prompt inside `run()`. The addendum must instruct: emit the tag as the very first line, and when NON-EARTH, chunk into more/smaller sections.
```python
CLASSIFY_ADDENDUM = """\

Before anything else, classify this world by DISTRIBUTIONAL DISTANCE from present-day \
human experience — not by geography. Emit exactly one tag as the VERY FIRST LINE of your \
output, before any WORLD DEDUCTION or PROSE STYLE section:
<<<WORLD_CLASS: EARTH>>>      if the world is contemporary or familiar-historical Earth.
<<<WORLD_CLASS: NON-EARTH>>>  if it is off-Earth OR an Earth far enough from present-day \
common experience (far future, deep past such as the Cretaceous, radically altered) that \
its sensory texture falls outside ordinary experience.
If and only if NON-EARTH, break the story into MORE, SMALLER numbered sections than you \
otherwise would, so the writer holds less world-state per section. Per-section word budgets \
must still sum to the target length.\
"""
```
In `run()`, change the system-prompt assembly line:
```python
        system_prompt = SYSTEM_PROMPT + CLASSIFY_ADDENDUM + (IMAGE_PROMPT_ADDENDUM if image else "")
```

- [ ] **Step 5: Add a planner test that the addendum is present**

Add to `tests/test_planning_agent.py`:
```python
from unittest.mock import patch
from agents.planning_agent import PlanningAgent


def test_run_system_prompt_includes_world_class_instruction():
    agent = PlanningAgent()
    with patch.object(agent, "_call_claude", return_value="out") as m:
        agent.run(idea="i", target_length="1k", target_audience="a")
    system_prompt = m.call_args.args[0]
    assert "<<<WORLD_CLASS: NON-EARTH>>>" in system_prompt
```

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/test_orchestrator.py tests/test_planning_agent.py -q`
Expected: PASS (new tests pass; existing planner tests still pass).

- [ ] **Step 7: Commit**

```bash
git add agents/planning_agent.py orchestrator.py tests/test_orchestrator.py tests/test_planning_agent.py
git commit -m "feat: planner world classification + chunking; class-tag parser"
```

---

## Task 4: Planner bible-revision method

**Files:**
- Modify: `agents/planning_agent.py`
- Test: `tests/test_planning_agent.py`

**Interfaces:**
- Produces: `PlanningAgent.revise_with_world_bible(plan: str, world_bible: str, canon_sheet: str, target_length: str) -> {"agent","output"}`. Calls `_call_claude` on `INITIAL_DRAFT_MODEL`. Output is a full narrative plan (same shape as `run`), NOT the `===` diff-ops format, and carries no `<<<WORLD_CLASS>>>` tag.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_planning_agent.py`:
```python
from agents.base_agent import INITIAL_DRAFT_MODEL


def test_revise_with_world_bible_uses_opus_and_passes_inputs():
    agent = PlanningAgent()
    with patch.object(agent, "_call_claude", return_value="REVISED PLAN") as m:
        result = agent.revise_with_world_bible(
            plan="OLD PLAN", world_bible="smells of iron",
            canon_sheet="halved gravity", target_length="8,000 words")
    assert result["output"] == "REVISED PLAN"
    assert m.call_args.kwargs["model"] == INITIAL_DRAFT_MODEL
    user_prompt = m.call_args.args[1]
    assert "OLD PLAN" in user_prompt
    assert "smells of iron" in user_prompt
    assert "halved gravity" in user_prompt
    assert "8,000 words" in user_prompt
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_planning_agent.py::test_revise_with_world_bible_uses_opus_and_passes_inputs -q`
Expected: FAIL — `AttributeError: ... has no attribute 'revise_with_world_bible'`.

- [ ] **Step 3: Implement**

Add the constant and method to `planning_agent.py`:
```python
BIBLE_REVISION_SYSTEM_PROMPT = """\
You are a story architect revising a narrative plan now that the story's world has been \
fully precomputed. You are given the original plan, a CANON SHEET of the world's rules, and \
a WORLD BIBLE of concrete sensory material. Rewrite the plan so its events, conflicts, and \
revelations genuinely exploit this world — a chase uses this world's transport, a conflict \
arises from its social tensions, a revelation is legible only within its rules. Draw \
specific material from the bible into the section beats.

Output a FULL narrative plan in the same format the original used (CHARACTERS section, then \
numbered sections with what/when/where/why/how/cost and prose-weight + word budgets). \
HARD RULES:
- Preserve the target length; per-section word budgets must still sum to it.
- Do NOT emit a <<<WORLD_CLASS>>> tag — classification is already done.
- Do NOT use the "=== STRUCTURAL OPERATIONS ===" diff-ops format; this is a full plan, \
  not a revision-ops list.\
"""

    def revise_with_world_bible(self, plan: str, world_bible: str,
                                canon_sheet: str, target_length: str) -> dict:
        user_prompt = (
            f"ORIGINAL PLAN:\n{plan}\n\n"
            f"CANON SHEET:\n{canon_sheet}\n\n"
            f"WORLD BIBLE:\n{world_bible}\n\n"
            f"TARGET LENGTH: {target_length}\n\n"
            "Rewrite the full plan to exploit this world."
        )
        output = self._call_claude(BIBLE_REVISION_SYSTEM_PROMPT, user_prompt,
                                   model=INITIAL_DRAFT_MODEL)
        return {"agent": "PlanningAgent", "output": output}
```
Ensure `INITIAL_DRAFT_MODEL` is imported at the top of `planning_agent.py`:
`from .base_agent import BaseAgent, INITIAL_DRAFT_MODEL`.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_planning_agent.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agents/planning_agent.py tests/test_planning_agent.py
git commit -m "feat: add PlanningAgent.revise_with_world_bible (Opus)"
```

---

## Task 5: Bucket-handling in planner revision prompts (conditional)

**Files:**
- Modify: `agents/planning_agent.py` (`plan_revision`, `plan_revision_prose` accept `non_earth=False`)
- Test: `tests/test_planning_agent.py`

**Interfaces:**
- Modifies: `plan_revision(story, plan, feedbacks, non_earth=False)` and `plan_revision_prose(story, plan, prose_feedback, consistency_feedback, non_earth=False)`. When `non_earth` is False the system prompt is unchanged (byte-identical). When True, a bucket-handling clause is appended: fix `[CRAFT]`, treat `[WORLD]` as intent unless a real contradiction; in `plan_revision_prose`, drop `[WORLD]`-tagged strangeness even under force-all.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_planning_agent.py`:
```python
def test_plan_revision_earth_prompt_unchanged():
    from agents.planning_agent import REVISION_PLAN_SYSTEM_PROMPT
    agent = PlanningAgent()
    with patch.object(agent, "_call_claude", return_value="out") as m:
        agent.plan_revision(story="s", plan="p", feedbacks=["f"])
    assert m.call_args.args[0] == REVISION_PLAN_SYSTEM_PROMPT   # exact, unchanged


def test_plan_revision_non_earth_adds_bucket_clause():
    from agents.planning_agent import REVISION_PLAN_SYSTEM_PROMPT
    agent = PlanningAgent()
    with patch.object(agent, "_call_claude", return_value="out") as m:
        agent.plan_revision(story="s", plan="p", feedbacks=["f"], non_earth=True)
    sp = m.call_args.args[0]
    assert sp != REVISION_PLAN_SYSTEM_PROMPT
    assert "[WORLD]" in sp and "[CRAFT]" in sp


def test_plan_revision_prose_non_earth_drops_world_tag():
    agent = PlanningAgent()
    with patch.object(agent, "_call_claude", return_value="out") as m:
        agent.plan_revision_prose(story="s", plan="p", prose_feedback="pf",
                                  consistency_feedback="cf", non_earth=True)
    assert "[WORLD]" in m.call_args.args[0]
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_planning_agent.py -k bucket -q`
Expected: FAIL — `plan_revision() got an unexpected keyword argument 'non_earth'`.

- [ ] **Step 3: Implement**

Add the clause constants near the prompts:
```python
_REVISION_BUCKET_CLAUSE = """\

BUCKETED FEEDBACK: reviewers may tag findings [CRAFT] or [WORLD]. Fix [CRAFT] findings. \
Treat [WORLD] findings as authorial intent for a deliberately non-Earth world — act on one \
only if it names an actual contradiction, never merely because a passage "reads strange".\
"""

_PROSE_BUCKET_CLAUSE = """\

BUCKETED FEEDBACK: findings may be tagged [CRAFT] or [WORLD]. Force-fix every [CRAFT] \
finding as instructed above. DROP any [WORLD]-tagged "reads strange" finding even though \
this pass otherwise forces all findings — the world's strangeness is intentional. Still \
fold in [WORLD] findings that are genuine text-level contradictions.\
"""
```
Change the two method signatures to accept `non_earth: bool = False`, and select the system prompt:
```python
    def plan_revision(self, story, plan, feedbacks, non_earth: bool = False) -> dict:
        ...
        system_prompt = REVISION_PLAN_SYSTEM_PROMPT + (_REVISION_BUCKET_CLAUSE if non_earth else "")
        output = self._call_claude(system_prompt, user_prompt)
        ...

    def plan_revision_prose(self, story, plan, prose_feedback,
                            consistency_feedback, non_earth: bool = False) -> dict:
        ...
        system_prompt = PROSE_REVISION_PLAN_SYSTEM_PROMPT + (_PROSE_BUCKET_CLAUSE if non_earth else "")
        output = self._call_claude(system_prompt, user_prompt)
        ...
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_planning_agent.py -q`
Expected: PASS (including the pre-existing planner tests, proving EARTH byte-identity).

- [ ] **Step 5: Commit**

```bash
git add agents/planning_agent.py tests/test_planning_agent.py
git commit -m "feat: conditional [CRAFT]/[WORLD] bucketing in planner revision prompts"
```

---

## Task 6: Writer canon/bible/model threading + gated blacklist

**Files:**
- Modify: `agents/writer_agent.py`
- Test: `tests/test_writer_agent.py`

**Interfaces:**
- Modifies: `WriterAgent.run(plan, model=None, canon_sheet="", world_bible="")` and `WriterAgent.revise(plan, story, feedback, model=None, canon_sheet="", world_bible="")`. When `canon_sheet` is empty, every `_call_claude` system prompt equals today's exactly. When present, the write prompts gain a canon + bible + trope-blacklist block. `model` is forwarded to every `_call_claude` in both methods.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_writer_agent.py`:
```python
from unittest.mock import patch
from agents.writer_agent import WriterAgent, SYSTEM_PROMPT


def test_run_earth_prompt_unchanged_and_no_model():
    agent = WriterAgent()
    with patch.object(agent, "_call_claude", return_value="story") as m:
        agent.run(plan="PLAN")
    assert m.call_args.args[0] == SYSTEM_PROMPT           # byte-identical
    assert m.call_args.kwargs.get("model") is None


def test_run_non_earth_injects_world_and_model():
    agent = WriterAgent()
    with patch.object(agent, "_call_claude", return_value="story") as m:
        agent.run(plan="PLAN", model="claude-opus-4-8",
                  canon_sheet="halved gravity", world_bible="smells of iron")
    sp = m.call_args.args[0]
    assert sp != SYSTEM_PROMPT
    assert "halved gravity" in sp and "smells of iron" in sp
    assert m.call_args.kwargs["model"] == "claude-opus-4-8"


def test_revise_forwards_model_on_fallback():
    agent = WriterAgent()
    # No section markers -> fallback rewrite path, single _call_claude.
    with patch.object(agent, "_call_claude", return_value="revised") as m:
        agent.revise(plan="p", story="no markers", feedback="notes",
                     model="claude-opus-4-8")
    assert m.call_args.kwargs["model"] == "claude-opus-4-8"
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_writer_agent.py -k "world or model" -q`
Expected: FAIL — `run() got an unexpected keyword argument 'canon_sheet'`.

- [ ] **Step 3: Implement**

At the top of `writer_agent.py` add the blacklist path + world-block builder:
```python
from pathlib import Path

DEFAULT_BLACKLIST_PATH = Path(__file__).parent.parent / "trope_blacklist.md"

def _world_block(canon_sheet: str, world_bible: str) -> str:
    """Return the appended write-time world block, or '' when no canon sheet."""
    if not canon_sheet:
        return ""
    blacklist = DEFAULT_BLACKLIST_PATH.read_text(encoding="utf-8")
    return (
        "\n\n---\n"
        f"WORLD CANON (obey these rules exactly; they are already resolved, so commit "
        f"boldly and do not hedge):\n{canon_sheet}\n\n"
        f"WORLD BIBLE (draw concrete sensory detail from here instead of inventing or "
        f"reaching for abstractions like 'strange' or 'otherworldly'):\n{world_bible}\n\n"
        f"AVOID THESE TROPES:\n---\n{blacklist}\n---"
    )
```
Thread `model`, `canon_sheet`, `world_bible` through both public methods. `run`:
```python
    def run(self, plan: str, model: str = None,
            canon_sheet: str = "", world_bible: str = "") -> dict:
        system_prompt = SYSTEM_PROMPT + _world_block(canon_sheet, world_bible)
        user_prompt = (
            f"NARRATIVE PLAN:\n{plan}\n\n"
            "Write the full story based on this plan."
        )
        output = self._call_claude(system_prompt, user_prompt,
                                   model=model, max_tokens=INITIAL_WRITE_MAX_TOKENS)
        return {"agent": "WriterAgent", "output": output, "revised_sections": None}
```
`revise`: add the same three params. Build `world = _world_block(canon_sheet, world_bible)` once. For the **fallback** path use `REVISION_FALLBACK_SYSTEM_PROMPT + world` and pass `model=model`. For the **section-revision** path use `REVISION_SYSTEM_PROMPT + world` and pass `model=model`. For the **general-notes** fallback use `REVISION_FALLBACK_SYSTEM_PROMPT + world` and `model=model`. Every `_call_claude` in `revise` gains `model=model`; the system prompt in each gains `+ world`. (When `canon_sheet=""`, `world=""`, so all three prompts are byte-identical to today and `model=None`.)

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_writer_agent.py -q`
Expected: PASS — new tests pass, all existing writer tests still pass (EARTH byte-identity).

- [ ] **Step 5: Commit**

```bash
git add agents/writer_agent.py tests/test_writer_agent.py
git commit -m "feat: thread canon/bible/model + gated blacklist through WriterAgent"
```

---

## Task 7: StrangenessReviewerAgent

**Files:**
- Create: `agents/strangeness_agent.py`
- Modify: `agents/__init__.py`
- Test: `tests/test_strangeness_agent.py`

**Interfaces:**
- Produces: `StrangenessReviewerAgent().run(story: str, canon_sheet: str = "") -> {"agent","output"}`. Model defaults to `DEFAULT_MODEL` (Sonnet). System prompt built via `with_canon(SYSTEM_PROMPT, canon_sheet, lower_authority=False)` so it stays world-aware but the inverted reviewer keeps full authority. Findings are `[WORLD]`-bucketed and cite `<<<SECTION N>>>`.

- [ ] **Step 1: Write the failing test**

`tests/test_strangeness_agent.py`:
```python
from unittest.mock import patch
from agents.strangeness_agent import StrangenessReviewerAgent
from agents.base_agent import DEFAULT_MODEL


def test_default_model_is_sonnet():
    assert StrangenessReviewerAgent().model == DEFAULT_MODEL


def test_run_includes_canon_when_present():
    agent = StrangenessReviewerAgent()
    with patch.object(agent, "_call_claude", return_value="findings") as m:
        out = agent.run(story="s", canon_sheet="three suns")
    assert out["output"] == "findings"
    assert "three suns" in m.call_args.args[0]
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_strangeness_agent.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`agents/strangeness_agent.py`:
```python
from .base_agent import BaseAgent, DEFAULT_MODEL
from .world_calibration import with_canon

SYSTEM_PROMPT = """\
You are a defamiliarization advocate. Every other reviewer on this council pulls the prose \
toward Earth-normal; your job is the opposite. This story is set in a deliberately \
non-Earth world, and your concern is that it is not strange ENOUGH — that the writer has \
fallen back on Earth defaults and left the world underexploited.

Find the two or three sections — by <<<SECTION N>>> number — where the prose is tamest: \
where a scene could be lifted into a contemporary Earth setting without changing a word, \
where sensory detail defaults to Earth (coffee, asphalt, ordinary weather) instead of this \
world's material, where the world's rules are established but not FELT on the page. For \
each, name what was left on the table and give a concrete alternative that commits to the \
world's canon.

Do not invent new world rules; work only from the established canon. Do not ask for \
change that would break continuity — you want the existing world rendered harder, not a \
different world. Tag each finding [WORLD]. Reward commitment; flag retreat.\
"""


class StrangenessReviewerAgent(BaseAgent):
    """Inverted reviewer: flags where a non-Earth story reads too Earth-tame."""

    def __init__(self, model: str = DEFAULT_MODEL):
        super().__init__(model=model)

    def run(self, story: str, canon_sheet: str = "") -> dict:
        system_prompt = with_canon(SYSTEM_PROMPT, canon_sheet, lower_authority=False)
        user_prompt = (
            f"STORY:\n{story}\n\n"
            "Identify the sections where this world is underexploited and prose reads "
            "too Earth-tame."
        )
        output = self._call_claude(system_prompt, user_prompt)
        return {"agent": "StrangenessReviewerAgent", "output": output}
```
Add export in `agents/__init__.py` (import + `__all__`).

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_strangeness_agent.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agents/strangeness_agent.py agents/__init__.py tests/test_strangeness_agent.py
git commit -m "feat: add StrangenessReviewerAgent (inverted, Sonnet)"
```

---

## Task 8: SensoryQuotaAgent

**Files:**
- Create: `agents/sensory_agent.py`
- Modify: `agents/__init__.py`
- Test: `tests/test_sensory_agent.py`

**Interfaces:**
- Produces: `SensoryQuotaAgent().run(story: str, canon_sheet: str = "") -> {"agent","output"}`. Model `DEFAULT_MODEL`. System prompt via `with_canon(SYSTEM_PROMPT, canon_sheet, lower_authority=False)`. Bans abstraction hedge-nouns, reports per-section concrete-sensory density, findings `[WORLD]`-bucketed, cite `<<<SECTION N>>>`.

- [ ] **Step 1: Write the failing test**

`tests/test_sensory_agent.py`:
```python
from unittest.mock import patch
from agents.sensory_agent import SensoryQuotaAgent
from agents.base_agent import DEFAULT_MODEL


def test_default_model_is_sonnet():
    assert SensoryQuotaAgent().model == DEFAULT_MODEL


def test_run_passes_story_and_canon():
    agent = SensoryQuotaAgent()
    with patch.object(agent, "_call_claude", return_value="report") as m:
        out = agent.run(story="STORY BODY", canon_sheet="ammonia seas")
    assert out["output"] == "report"
    assert "STORY BODY" in m.call_args.args[1]
    assert "ammonia seas" in m.call_args.args[0]
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_sensory_agent.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`agents/sensory_agent.py`:
```python
from .base_agent import BaseAgent, DEFAULT_MODEL
from .world_calibration import with_canon

SYSTEM_PROMPT = """\
You are a sensory-density auditor for a non-Earth story. Alien worlds tempt a writer into \
abstraction — hedge-nouns that gesture at strangeness instead of rendering it. Your job is \
to force concreteness.

Do two things:
1. BANNED ABSTRACTIONS. Hunt these hedge-words and their kin: "otherworldly", "alien", \
   "strange", "indescribable", "shimmering", "eldritch", "unknowable", "surreal". Quote \
   every instance with its <<<SECTION N>>> number and demand a concrete replacement drawn \
   from the world's canon — a specific texture, smell, sound, weight, or temperature.
2. SENSORY DENSITY. For each <<<SECTION N>>>, report an approximate count of concrete \
   non-visual sensory details (smell, sound, touch, temperature, weight, taste). Flag any \
   section running thin — especially set-pieces that should be saturated. Report density as \
   a per-section line, the way a tic-density report reads.

Tag every finding [WORLD]. Be specific: a demand the writer can execute without guessing, \
naming the exact word to cut and the kind of concrete detail to reach for.\
"""


class SensoryQuotaAgent(BaseAgent):
    """Bans abstraction hedge-nouns and reports concrete-sensory density per section."""

    def __init__(self, model: str = DEFAULT_MODEL):
        super().__init__(model=model)

    def run(self, story: str, canon_sheet: str = "") -> dict:
        system_prompt = with_canon(SYSTEM_PROMPT, canon_sheet, lower_authority=False)
        user_prompt = (
            f"STORY:\n{story}\n\n"
            "Flag banned abstractions and report concrete-sensory density per section."
        )
        output = self._call_claude(system_prompt, user_prompt)
        return {"agent": "SensoryQuotaAgent", "output": output}
```
Add export in `agents/__init__.py` (import + `__all__`).

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_sensory_agent.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agents/sensory_agent.py agents/__init__.py tests/test_sensory_agent.py
git commit -m "feat: add SensoryQuotaAgent (Sonnet)"
```

---

## Task 9: Recalibrate the six existing reviewers

**Files:**
- Modify: `agents/consistency_agent.py`, `ai_failure_checker.py`, `peer_writer_agent.py`, `editor_agent.py`, `marketing_agent.py`, `audience_agent.py`
- Test: `tests/test_ai_failure_checker.py` (+ a small new `tests/test_reviewer_canon.py`)

**Interfaces:**
- Modifies each reviewer's `run(...)` to accept `canon_sheet: str = ""` and build its system prompt via `with_canon(SYSTEM_PROMPT, canon_sheet, lower_authority=<False for PeerWriter, True for the rest>)`. `AIFailureCheckerAgent.run` and `run_prose` both take `canon_sheet`. EARTH (`canon_sheet=""`) → byte-identical prompts.

- [ ] **Step 1: Write the failing tests**

`tests/test_reviewer_canon.py`:
```python
from unittest.mock import patch
from agents.consistency_agent import ConsistencyAgent, SYSTEM_PROMPT as CONS_SP
from agents.editor_agent import EditorAgent, SYSTEM_PROMPT as ED_SP
from agents.peer_writer_agent import PeerWriterAgent, SYSTEM_PROMPT as PEER_SP


def test_consistency_earth_unchanged():
    a = ConsistencyAgent()
    with patch.object(a, "_call_claude", return_value="x") as m:
        a.run(story="s")
    assert m.call_args.args[0] == CONS_SP


def test_consistency_canon_lowers_authority():
    a = ConsistencyAgent()
    with patch.object(a, "_call_claude", return_value="x") as m:
        a.run(story="s", canon_sheet="halved gravity")
    sp = m.call_args.args[0]
    assert "halved gravity" in sp and "authority" in sp.lower()


def test_peer_writer_canon_keeps_authority():
    a = PeerWriterAgent()
    with patch.object(a, "_call_claude", return_value="x") as m:
        a.run(plan="p", story="s", canon_sheet="three suns")
    sp = m.call_args.args[0]
    assert "three suns" in sp
    assert "lower your authority" not in sp.lower()   # agent 5 exempt
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_reviewer_canon.py -q`
Expected: FAIL — `run() got an unexpected keyword argument 'canon_sheet'`.

- [ ] **Step 3: Implement — each reviewer, one change**

For each file, add `from .world_calibration import with_canon`, add `canon_sheet: str = ""` to `run`, and replace the `self._call_claude(SYSTEM_PROMPT, ...)` call so the system prompt is wrapped. Five reviewers use `lower_authority=True` (default); PeerWriter uses `False`.

`consistency_agent.py` `run`:
```python
    def run(self, story: str, canon_sheet: str = "") -> dict:
        user_prompt = f"STORY:\n{story}\n\nReview this story for all internal consistency problems."
        output = self._call_claude(with_canon(SYSTEM_PROMPT, canon_sheet), user_prompt)
        return {"agent": "ConsistencyAgent", "output": output}
```
`editor_agent.py`, `marketing_agent.py`, `audience_agent.py`: identical shape — add `canon_sheet=""` to `run`, wrap the first positional arg of `_call_claude` in `with_canon(SYSTEM_PROMPT, canon_sheet)`. (Marketing/Audience `run` also keep their existing `target_audience` param; add `canon_sheet=""` after it.)

`peer_writer_agent.py` `run` (note `lower_authority=False`):
```python
    def run(self, plan: str, story: str, canon_sheet: str = "") -> dict:
        user_prompt = (
            f"ORIGINAL PLAN:\n{plan}\n\n"
            f"STORY AS WRITTEN:\n{story}\n\n"
            "Identify the weakest areas and offer specific alternative approaches."
        )
        output = self._call_claude(
            with_canon(SYSTEM_PROMPT, canon_sheet, lower_authority=False), user_prompt)
        return {"agent": "PeerWriterAgent", "output": output}
```
`ai_failure_checker.py` — both methods. `run` and `run_prose` currently `.format()` the failure-modes template into a system prompt; wrap that result:
```python
    def run(self, story, failure_modes_path=None, canon_sheet: str = "") -> dict:
        ...
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(failure_modes=failure_modes)
        output = self._call_claude(with_canon(system_prompt, canon_sheet), user_prompt)
        ...
    def run_prose(self, story, top_n=5, failure_modes_path=None, canon_sheet: str = "") -> dict:
        ...
        system_prompt = PROSE_SYSTEM_PROMPT_TEMPLATE.format(failure_modes=failure_modes, top_n=top_n)
        output = self._call_claude(with_canon(system_prompt, canon_sheet), user_prompt)
        ...
```
Add `from .world_calibration import with_canon` to each of the six files.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_reviewer_canon.py tests/test_ai_failure_checker.py -q`
Expected: PASS — new canon tests pass; existing AI-failure-checker tests still pass (EARTH byte-identity).

- [ ] **Step 5: Commit**

```bash
git add agents/consistency_agent.py agents/ai_failure_checker.py agents/peer_writer_agent.py agents/editor_agent.py agents/marketing_agent.py agents/audience_agent.py tests/test_reviewer_canon.py
git commit -m "feat: canon-aware recalibration of the six reviewers (PeerWriter exempt)"
```

---

## Task 10: Orchestrator — alien branch in the initial inner loop

**Files:**
- Modify: `orchestrator.py` (`__init__`, `_run_inner` initial branch + return shape, fan-out)
- Test: `tests/test_orchestrator.py`

**Interfaces:**
- Modifies: `_run_inner(...)` — on the initial call, parses the class tag, and when `non_earth` runs WorldBuilder + `revise_with_world_bible`, then writes with Opus + canon + bible. Its return becomes `(plan, story, non_earth, canon_sheet, world_bible)`. The fan-out adds strangeness + sensory when `non_earth` (executor `max_workers=4`), and their outputs join the `plan_revision_2` feedback list. `plan_revision` is called with `non_earth=non_earth`.
- Consumes: `WorldBuilderAgent`, `StrangenessReviewerAgent`, `SensoryQuotaAgent` (Task 1/7/8); `planner.revise_with_world_bible` (Task 4); writer canon/bible/model params (Task 6); reviewer `canon_sheet` params (Task 9).

- [ ] **Step 1: Update existing orchestrator mocks for the new return shape**

In `tests/test_orchestrator.py`, the two tests that mock `_run_inner` expect a 2-tuple. Update them to the 5-tuple:
```python
    council._run_inner = MagicMock(
        return_value=("plan", "<<<SECTION 1>>>\nDraft.", False, "", ""))
```
(Apply to `test_run_applies_one_prose_pass_and_strips_markers` and `test_run_respects_prose_passes_and_top_n` — the latter's `_run_inner` returns `("plan", "s", False, "", "")`.)

- [ ] **Step 2: Write the failing test**

Add to `tests/test_orchestrator.py`:
```python
def test_initial_inner_non_earth_builds_world_and_uses_opus_writer():
    council = WritingCouncil()
    council.planner.run = MagicMock(return_value={
        "agent": "PlanningAgent",
        "output": "<<<WORLD_CLASS: NON-EARTH>>>\n<<<SECTION 1>>>\nBody."})
    council.world_builder.run = MagicMock(return_value={
        "agent": "WorldBuilderAgent", "output": "o",
        "canon_sheet": "CANON", "world_bible": "BIBLE"})
    council.planner.revise_with_world_bible = MagicMock(return_value={
        "agent": "PlanningAgent", "output": "<<<SECTION 1>>>\nBody."})
    council.writer.run = MagicMock(return_value={
        "agent": "WriterAgent", "output": "<<<SECTION 1>>>\nStory.",
        "revised_sections": None})
    council.consistency.run = MagicMock(return_value={"output": "c", "agent": "C"})
    council.ai_checker.run = MagicMock(return_value={"output": "a", "agent": "A"})
    council.strangeness.run = MagicMock(return_value={"output": "st", "agent": "S"})
    council.sensory.run = MagicMock(return_value={"output": "se", "agent": "Se"})
    council.planner.plan_revision = MagicMock(return_value={"output": "rp", "agent": "P"})
    council.writer.revise = MagicMock(return_value={
        "agent": "WriterAgent", "output": "<<<SECTION 1>>>\nFinal.",
        "revised_sections": None})

    plan, story, non_earth, canon, bible = council._run_inner(
        idea="i", target_length="1k", target_audience="a")

    assert non_earth is True
    assert canon == "CANON" and bible == "BIBLE"
    council.world_builder.run.assert_called_once()
    council.planner.revise_with_world_bible.assert_called_once()
    # Opus + canon/bible reached the initial write.
    assert council.writer.run.call_args.kwargs["model"] == INITIAL_DRAFT_MODEL
    assert council.writer.run.call_args.kwargs["canon_sheet"] == "CANON"
    # Two new reviewers ran; their feedback reached plan_revision.
    council.strangeness.run.assert_called_once()
    council.sensory.run.assert_called_once()
    feedbacks = council.planner.plan_revision.call_args.kwargs["feedbacks"]
    assert "st" in feedbacks and "se" in feedbacks
    assert council.planner.plan_revision.call_args.kwargs["non_earth"] is True


def test_initial_inner_earth_skips_world_builder():
    council = WritingCouncil()
    council.planner.run = MagicMock(return_value={
        "agent": "PlanningAgent", "output": "<<<WORLD_CLASS: EARTH>>>\n<<<SECTION 1>>>\nB."})
    council.world_builder.run = MagicMock()
    council.writer.run = MagicMock(return_value={
        "agent": "WriterAgent", "output": "<<<SECTION 1>>>\nS.", "revised_sections": None})
    council.consistency.run = MagicMock(return_value={"output": "c", "agent": "C"})
    council.ai_checker.run = MagicMock(return_value={"output": "a", "agent": "A"})
    council.planner.plan_revision = MagicMock(return_value={"output": "rp", "agent": "P"})
    council.writer.revise = MagicMock(return_value={
        "agent": "WriterAgent", "output": "final", "revised_sections": None})

    _, _, non_earth, canon, bible = council._run_inner(
        idea="i", target_length="1k", target_audience="a")

    assert non_earth is False
    assert canon == "" and bible == ""
    council.world_builder.run.assert_not_called()
    # Writer still gets Opus on the INITIAL write (existing behavior), canon empty.
    assert council.writer.run.call_args.kwargs["model"] == INITIAL_DRAFT_MODEL
    assert council.writer.run.call_args.kwargs["canon_sheet"] == ""
    council.planner.plan_revision.assert_called_with(
        story=council.planner.plan_revision.call_args.kwargs["story"],
        plan=council.planner.plan_revision.call_args.kwargs["plan"],
        feedbacks=council.planner.plan_revision.call_args.kwargs["feedbacks"],
        non_earth=False)
```

- [ ] **Step 3: Run to verify failure**

Run: `python -m pytest tests/test_orchestrator.py -k "non_earth or earth_skips" -q`
Expected: FAIL — `AttributeError: 'WritingCouncil' object has no attribute 'world_builder'`.

- [ ] **Step 4: Register the new agents in `__init__`**

In `orchestrator.py` imports add `WorldBuilderAgent, StrangenessReviewerAgent, SensoryQuotaAgent` to the `from agents import (...)` block, and in `WritingCouncil.__init__`:
```python
        self.world_builder = WorldBuilderAgent()
        self.strangeness = StrangenessReviewerAgent()
        self.sensory = SensoryQuotaAgent()
```

- [ ] **Step 5: Rewrite the initial branch of `_run_inner`**

Replace the initial-call branch (the `if idea is not None:` block, lines ~154-184) so that, after `plan = result["output"]`, it classifies and — when alien — builds the world and revises the plan, then writes with the elevated model + world context. Introduce locals `non_earth`, `canon_sheet`, `world_bible` initialized to `False`/`""` at the top of the method so the from-middle branch (Task 11 will pass them in) and the return can reference them:
```python
        non_earth, canon_sheet, world_bible = False, "", ""
        if idea is not None:
            # ... planner.run(...) as today (with model=INITIAL_DRAFT_MODEL) ...
            plan = result["output"]
            non_earth, plan = self._parse_world_class(plan)

            if non_earth:
                print(f"[{label}] NON-EARTH world — running WorldBuilder...")
                self._log_start(f"{label}.world_builder", "WorldBuilderAgent")
                wb = self.world_builder.run(idea=idea, plan=plan, world_rules=world_rules)
                self._log_end(wb, step=f"{label}.world_builder")
                canon_sheet, world_bible = wb["canon_sheet"], wb["world_bible"]

                print(f"[{label}] Revising plan against the world bible...")
                self._log_start(f"{label}.plan_bible_revision", "PlanningAgent")
                rev = self.planner.revise_with_world_bible(
                    plan=plan, world_bible=world_bible, canon_sheet=canon_sheet,
                    target_length=target_length)
                self._log_end(rev, step=f"{label}.plan_bible_revision")
                plan = rev["output"]

            print(f"[{label}] Running WriterAgent (initial write)...")
            self._log_start(f"{label}.write_1", "WriterAgent", f"plan:\n{plan}")
            write_result = self.writer.run(
                plan=plan, model=INITIAL_DRAFT_MODEL,
                canon_sheet=canon_sheet, world_bible=world_bible)
            self._log_end(write_result, step=f"{label}.write_1")
            story = write_result["output"]
        else:
            # from-middle branch — Task 11 wires non_earth/canon/bible in as params
            ...
```

- [ ] **Step 6: Extend the checker fan-out**

Replace the `(4 ∥ 3)` block so that, when `non_earth`, strangeness + sensory run alongside and their outputs are appended to the feedback list. Also thread `canon_sheet` into the existing two checkers and `model` into the final revise:
```python
        workers = 4 if non_earth else 2
        with ThreadPoolExecutor(max_workers=workers) as executor:
            f_cons = executor.submit(self.consistency.run, story=check_text,
                                     canon_sheet=canon_sheet)
            f_ai = executor.submit(self.ai_checker.run, story=check_text,
                                   canon_sheet=canon_sheet)
            f_str = executor.submit(self.strangeness.run, story=check_text,
                                    canon_sheet=canon_sheet) if non_earth else None
            f_sen = executor.submit(self.sensory.run, story=check_text,
                                    canon_sheet=canon_sheet) if non_earth else None
            cons_result = f_cons.result()
            ai_result = f_ai.result()
            str_result = f_str.result() if f_str else None
            sen_result = f_sen.result() if f_sen else None

        feedbacks = [cons_result["output"], ai_result["output"]]
        if str_result:
            feedbacks.append(str_result["output"])
        if sen_result:
            feedbacks.append(sen_result["output"])

        result = self.planner.plan_revision(
            story=story, plan=plan, feedbacks=feedbacks, non_earth=non_earth)
        revision_plan = result["output"]

        result = self.writer.revise(
            plan=plan, story=story, feedback=revision_plan,
            model=(INITIAL_DRAFT_MODEL if non_earth else None),
            canon_sheet=canon_sheet, world_bible=world_bible)
        story = result["output"]

        return plan, story, non_earth, canon_sheet, world_bible
```
(Keep the existing `_log_start`/`_log_end` calls for consistency/ai; add matching ones for strangeness/sensory guarded by `if non_earth`.)

- [ ] **Step 7: Run tests**

Run: `python -m pytest tests/test_orchestrator.py -q`
Expected: PASS — new alien/earth tests pass; the updated existing tests pass; `test_initial_inner_runs_plan_and_write_on_opus` still passes (its planner output has no tag → `non_earth=False`, writer.revise gets `model=None`).

- [ ] **Step 8: Commit**

```bash
git add orchestrator.py tests/test_orchestrator.py
git commit -m "feat: orchestrate WorldBuilder + bible-revision + 4-way fan-out in initial inner"
```

---

## Task 11: Orchestrator — propagate non_earth through middle, prose, and run()

**Files:**
- Modify: `orchestrator.py` (`run`, `_run_middle`, `_run_prose_pass`, from-middle `_run_inner` branch)
- Test: `tests/test_orchestrator.py`

**Interfaces:**
- Modifies: `_run_middle(plan, story, target_audience, non_earth=False, canon_sheet="", world_bible="")` and `_run_prose_pass(plan, story, top_n=5, label="prose", non_earth=False, canon_sheet="", world_bible="")`. `run()` captures the 5-tuple from the initial `_run_inner` and threads the three world values into both. The from-middle `_run_inner` accepts and uses them (reviewers get canon, writer gets Opus+canon+bible, `plan_revision` gets `non_earth`).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_orchestrator.py`:
```python
def test_run_threads_non_earth_into_middle_and_prose():
    council = WritingCouncil()
    council._run_inner = MagicMock(
        return_value=("plan", "<<<SECTION 1>>>\nD.", True, "CANON", "BIBLE"))
    council._run_middle = MagicMock(return_value="<<<SECTION 1>>>\nM.")
    council._run_prose_pass = MagicMock(return_value="<<<SECTION 1>>>\nP.")

    council.run(idea="i", target_length="1k", target_audience="a")

    assert council._run_middle.call_args.kwargs["non_earth"] is True
    assert council._run_middle.call_args.kwargs["canon_sheet"] == "CANON"
    assert council._run_prose_pass.call_args.kwargs["non_earth"] is True
    assert council._run_prose_pass.call_args.kwargs["world_bible"] == "BIBLE"
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_orchestrator.py::test_run_threads_non_earth_into_middle_and_prose -q`
Expected: FAIL — `_run_middle()` unexpected kwarg / `KeyError`.

- [ ] **Step 3: Thread through `run()`**

In `run()`, capture the 5-tuple and pass the world values on:
```python
        plan, story, non_earth, canon_sheet, world_bible = self._run_inner(
            idea=idea, target_length=target_length, target_audience=target_audience,
            world_rules=world_rules, framework=framework, style=style, image=image,
            label="outer.inner")

        story = self._run_middle(plan, story, target_audience,
                                 non_earth=non_earth, canon_sheet=canon_sheet,
                                 world_bible=world_bible)

        for i in range(prose_passes):
            story = self._run_prose_pass(
                plan, story, top_n=prose_top_n, label=f"prose.{i + 1}",
                non_earth=non_earth, canon_sheet=canon_sheet, world_bible=world_bible)
```
Also add `non_earth` to the returned dict: `return {"story": story, "non_earth": non_earth, "log": list(self._log)}`.

- [ ] **Step 4: Thread through `_run_middle`**

Add the three params; pass `canon_sheet` to each of the four reviewers' `.run(...)`, and forward all three into the from-middle `_run_inner` call:
```python
    def _run_middle(self, plan, story, target_audience,
                    non_earth: bool = False, canon_sheet: str = "", world_bible: str = "") -> str:
        ...
            f_peer = executor.submit(self.peer_writer.run, plan=plan, story=story,
                                     canon_sheet=canon_sheet)
            f_editor = executor.submit(self.editor.run, story=story, canon_sheet=canon_sheet)
            f_mkt = executor.submit(self.marketing.run, story=story,
                                    target_audience=target_audience, canon_sheet=canon_sheet)
            f_aud = executor.submit(self.audience.run, story=story,
                                    target_audience=target_audience, canon_sheet=canon_sheet)
        ...
        _, story, _, _, _ = self._run_inner(
            plan=plan, story=story, middle_feedbacks=middle_feedbacks, label="middle.inner",
            non_earth=non_earth, canon_sheet=canon_sheet, world_bible=world_bible)
        return story
```

- [ ] **Step 5: Accept the world values in `_run_inner` and use them in the from-middle branch**

Add `non_earth: bool = False, canon_sheet: str = "", world_bible: str = ""` to the `_run_inner` signature. At the top, only default them when this is the initial call; when called from middle, use the passed-in values:
```python
    def _run_inner(self, idea=None, ..., middle_feedbacks=None, label="inner",
                   non_earth: bool = False, canon_sheet: str = "", world_bible: str = ""):
        if idea is not None:
            non_earth, canon_sheet, world_bible = False, "", ""   # derived below
            ...
```
In the from-middle branch, forward `model`/`canon_sheet`/`world_bible` into `writer.revise`:
```python
            write_result = self.writer.revise(
                plan=plan, story=story, feedback=pre_write_plan,
                model=(INITIAL_DRAFT_MODEL if non_earth else None),
                canon_sheet=canon_sheet, world_bible=world_bible)
```
(The shared fan-out block from Task 10 already reads `non_earth`/`canon_sheet`/`world_bible`, so both branches converge correctly.)

- [ ] **Step 6: Thread through `_run_prose_pass`**

Add the three params; pass `canon_sheet` to the two prose reviewers, `non_earth` to `plan_revision_prose`, and Opus+canon+bible to the writer:
```python
    def _run_prose_pass(self, plan, story, top_n=5, label="prose",
                        non_earth: bool = False, canon_sheet: str = "", world_bible: str = "") -> str:
        with ThreadPoolExecutor(max_workers=2) as executor:
            f_cons = executor.submit(self.consistency.run, story=story, canon_sheet=canon_sheet)
            f_prose = executor.submit(self.ai_checker.run_prose, story=story, top_n=top_n,
                                      canon_sheet=canon_sheet)
            cons_result = f_cons.result()
            prose_result = f_prose.result()
        plan_result = self.planner.plan_revision_prose(
            story=story, plan=plan, prose_feedback=prose_result["output"],
            consistency_feedback=cons_result["output"], non_earth=non_earth)
        revision_plan = plan_result["output"]
        write_result = self.writer.revise(
            plan=plan, story=story, feedback=revision_plan,
            model=(INITIAL_DRAFT_MODEL if non_earth else None),
            canon_sheet=canon_sheet, world_bible=world_bible)
        return write_result["output"]
```
Note: this changes the call signatures the existing `test_run_prose_pass_calls_agents_in_order` asserts. Update that test's expected calls to include `canon_sheet=""` on the two reviewers, `non_earth=False` on `plan_revision_prose`, and `model=None, canon_sheet="", world_bible=""` on `writer.revise`.

- [ ] **Step 7: Run the full suite**

Run: `python -m pytest tests -q`
Expected: PASS (all tests, including server + document_writer, green).

- [ ] **Step 8: Commit**

```bash
git add orchestrator.py tests/test_orchestrator.py
git commit -m "feat: propagate non_earth/canon/bible through middle, prose, and run()"
```

---

## Task 12: Surface non_earth in the server response

**Files:**
- Modify: `server.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `run()` now returns `non_earth` in its dict (Task 11). The `/run` endpoint includes it in the JSON response so the browser/log can show which classification fired.

- [ ] **Step 1: Inspect the endpoint**

Read `server.py` around the `/run` handler to find where `WritingCouncil().run(...)`'s result is turned into the JSON response.

- [ ] **Step 2: Write the failing test**

Add to `tests/test_server.py` (follow the file's existing `WritingCouncil`-patching pattern):
```python
def test_run_response_includes_non_earth(client):
    with patch("server.WritingCouncil") as MockCouncil:
        MockCouncil.return_value.run.return_value = {
            "story": "S", "non_earth": True, "log": []}
        resp = client.post("/run", json={
            "idea": "i", "target_length": "1k", "target_audience": "a"})
    assert resp.status_code == 200
    assert resp.get_json()["non_earth"] is True
```
(Match the exact fixture/patch style already in `tests/test_server.py`; if the existing tests build the payload differently, mirror that.)

- [ ] **Step 3: Run to verify failure**

Run: `python -m pytest tests/test_server.py::test_run_response_includes_non_earth -q`
Expected: FAIL — `KeyError: 'non_earth'` or assertion error.

- [ ] **Step 4: Implement**

In the `/run` handler, add `non_earth` (defaulting to `False`) to the response payload built from the council result, e.g.:
```python
    result = council.run(**kwargs)
    return jsonify({
        "story": result["story"],
        "non_earth": result.get("non_earth", False),
        # ...existing fields (log, etc.)...
    })
```
(Preserve whatever fields the handler already returns; only add `non_earth`.)

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_server.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add server.py tests/test_server.py
git commit -m "feat: surface non_earth classification in /run response"
```

---

## Final verification

- [ ] **Full suite green**

Run: `python -m pytest tests -q`
Expected: PASS — all tests. This proves both the new alien-path behavior and the EARTH byte-identity guard (no existing characterization test regressed).

- [ ] **EARTH regression spot-check**

Confirm `test_initial_inner_runs_plan_and_write_on_opus`, the existing planner tests, writer tests, and AI-failure-checker tests all still pass unchanged — they are the guardrail proving EARTH runs are byte-for-byte today's pipeline.

---

## Self-Review (completed against the spec)

- **Trigger / classification / chunking** → Task 3. **Tag parse+strip** → Task 3.
- **WorldBuilder (Opus, canon-first split, raised max_tokens)** → Task 1.
- **Trope blacklist file shipped as stub** → Task 1.
- **Planner bible-revision (Opus, target_length, no tag / no ops-format)** → Task 4.
- **Writer Opus on all passes + canon/bible + gated blacklist** → Task 6 (agent) + Tasks 10/11 (call sites).
- **StrangenessReviewer (Sonnet, [WORLD], full authority)** → Task 7.
- **SensoryQuota (Sonnet, [WORLD], abstraction ban + density)** → Task 8.
- **Six reviewers recalibrated, PeerWriter exempt** → Task 9.
- **Bucketing in planner revision prompts; prose drops [WORLD]** → Task 5.
- **Inner 4-way fan-out (workers=4)** → Task 10.
- **non_earth/canon/bible propagation out of _run_inner through middle/prose/run** → Tasks 10/11.
- **EARTH byte-identical guard** → verified by unchanged existing tests in Tasks 5/6/9 + Final verification.
- **Cost tradeoff** → documentation only, no task (accepted).
- **Server surfacing** → Task 12.

No placeholders; types/signatures consistent across tasks (`_parse_world_class`, `revise_with_world_bible`, `with_canon`, the 5-tuple `_run_inner` return, `canon_sheet`/`world_bible`/`model` params).
