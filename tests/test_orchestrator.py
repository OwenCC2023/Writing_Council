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
    assert council.writer.revise.call_args.kwargs.get("model") is None
    assert INITIAL_DRAFT_MODEL == "claude-opus-5"


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
    council.ai_checker.run_prose.assert_called_once_with(
        story="story", top_n=5, canon_sheet="")
    council.consistency.run.assert_called_once_with(story="story", canon_sheet="")
    council.planner.plan_revision_prose.assert_called_once_with(
        story="story", plan="plan", prose_feedback="prose", consistency_feedback="cons",
        non_earth=False)
    council.writer.revise.assert_called_once_with(
        plan="plan", story="story", feedback="revplan",
        model=None, canon_sheet="", world_bible="")


def test_run_applies_one_prose_pass_and_strips_markers():
    council = WritingCouncil()
    council._run_inner = MagicMock(
        return_value=("plan", "<<<SECTION 1>>>\nDraft.", False, "", "", ""))
    council._run_middle = MagicMock(return_value="<<<SECTION 1>>>\nMiddle.")
    council._run_prose_pass = MagicMock(return_value="<<<SECTION 1>>>\nProse out.")

    result = council.run(idea="i", target_length="1k", target_audience="a")

    assert council._run_prose_pass.call_count == 1
    assert "<<<SECTION" not in result["story"]
    assert "Prose out." in result["story"]


def test_run_respects_prose_passes_and_top_n():
    council = WritingCouncil()
    council._run_inner = MagicMock(return_value=("plan", "s", False, "", "", ""))
    council._run_middle = MagicMock(return_value="s")
    council._run_prose_pass = MagicMock(
        side_effect=lambda plan, story, top_n, label, **kwargs: story + "+")

    result = council.run(idea="i", target_length="1k", target_audience="a",
                         prose_passes=3, prose_top_n=7)

    assert council._run_prose_pass.call_count == 3
    assert council._run_prose_pass.call_args.kwargs["top_n"] == 7
    assert "<<<SECTION" not in result["story"]


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

    plan, story, non_earth, canon, bible, _ = council._run_inner(
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

    _, _, non_earth, canon, bible, _ = council._run_inner(
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


def test_run_threads_non_earth_into_middle_and_prose():
    council = WritingCouncil()
    council._run_inner = MagicMock(
        return_value=("plan", "<<<SECTION 1>>>\nD.", True, "CANON", "BIBLE", ""))
    council._run_middle = MagicMock(return_value="<<<SECTION 1>>>\nM.")
    council._run_prose_pass = MagicMock(return_value="<<<SECTION 1>>>\nP.")

    council.run(idea="i", target_length="1k", target_audience="a")

    assert council._run_middle.call_args.kwargs["non_earth"] is True
    assert council._run_middle.call_args.kwargs["canon_sheet"] == "CANON"
    assert council._run_prose_pass.call_args.kwargs["non_earth"] is True
    assert council._run_prose_pass.call_args.kwargs["world_bible"] == "BIBLE"


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
