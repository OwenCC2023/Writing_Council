from unittest.mock import MagicMock

from orchestrator import WritingCouncil
from agents.base_agent import INITIAL_DRAFT_MODEL


def test_initial_inner_runs_plan_and_write_on_opus():
    """Initial plan + write use INITIAL_DRAFT_MODEL; revisions do not."""
    council = WritingCouncil()
    council.planner.run = MagicMock(return_value={"agent": "PlanningAgent", "output": "plan"})
    council.writer.run = MagicMock(
        return_value={"agent": "WriterAgent", "output": "story", "revised_sections": None})
    council.consistency.run = MagicMock(return_value={"agent": "ConsistencyAgent", "output": "c"})
    council.ai_checker.run = MagicMock(return_value={"agent": "AIFailureCheckerAgent", "output": "a"})
    council.planner.plan_revision = MagicMock(return_value={"agent": "PlanningAgent", "output": "rp"})
    council.writer.revise = MagicMock(
        return_value={"agent": "WriterAgent", "output": "final", "revised_sections": None})

    council._run_inner(idea="i", target_length="1k", target_audience="a")

    assert council.planner.run.call_args.kwargs["model"] == INITIAL_DRAFT_MODEL
    assert council.writer.run.call_args.kwargs["model"] == INITIAL_DRAFT_MODEL
    # Revisions carry no model override -> stay on the agent's default.
    assert "model" not in council.writer.revise.call_args.kwargs
    assert INITIAL_DRAFT_MODEL == "claude-opus-4-8"


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
