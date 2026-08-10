from unittest.mock import MagicMock

from orchestrator import WritingCouncil
import world_class as wc
from agents.base_agent import INITIAL_DRAFT_MODEL
from agents.writer_agent import INITIAL_WRITE_MAX_TOKENS


def test_initial_inner_runs_plan_and_write_on_opus():
    """Initial plan + write use INITIAL_DRAFT_MODEL; revisions do not."""
    council = WritingCouncil()
    council.planner.run = MagicMock(return_value={"agent": "PlanningAgent", "output": "plan"})
    council.writer.run = MagicMock(
        return_value={"agent": "WriterAgent", "output": "story", "revised_sections": None})
    council.consistency.run = MagicMock(return_value={"agent": "ConsistencyAgent", "output": "c"})
    council.ai_checker.run = MagicMock(return_value={"agent": "AIFailureCheckerAgent", "output": "a"})
    council.engine.run = MagicMock(return_value={"agent": "EngineReviewerAgent", "output": "e"})
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
    council.variance.run = MagicMock(
        return_value={"agent": "VarianceReviewerAgent", "output": "var"})
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
        canon_aware=False, variance_feedback="var")
    council.writer.revise.assert_called_once_with(
        plan="plan", story="story", feedback="revplan",
        model=None, canon_sheet="", world_bible="", constraint="",
        # No target_length here, so the budget resolves to the unchanged floor.
        max_tokens=INITIAL_WRITE_MAX_TOKENS)


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
    council.engine.run = MagicMock(return_value={"output": "e", "agent": "E"})
    council.strangeness.run = MagicMock(return_value={"output": "st", "agent": "S"})
    council.sensory.run = MagicMock(return_value={"output": "se", "agent": "Se"})
    council.planner.plan_revision = MagicMock(return_value={"output": "rp", "agent": "P"})
    council.writer.revise = MagicMock(return_value={
        "agent": "WriterAgent", "output": "<<<SECTION 1>>>\nFinal.",
        "revised_sections": None})

    plan, story, world_class, canon, bible, _ = council._run_inner(
        idea="i", target_length="1k", target_audience="a")

    assert world_class == wc.NON_EARTH
    assert canon == "CANON" and bible == "BIBLE"
    council.world_builder.run.assert_called_once()
    council.planner.revise_with_world_bible.assert_called_once()
    # Opus + canon/bible reached the initial write.
    assert council.writer.run.call_args.kwargs["model"] == INITIAL_DRAFT_MODEL
    assert council.writer.run.call_args.kwargs["canon_sheet"] == "CANON"
    # New reviewers ran; their feedback reached plan_revision.
    council.strangeness.run.assert_called_once()
    council.sensory.run.assert_called_once()
    council.engine.run.assert_called_once()
    # Engine reviewer is canon-aware on a non-Earth run.
    assert council.engine.run.call_args.kwargs["canon_sheet"] == "CANON"
    feedbacks = council.planner.plan_revision.call_args.kwargs["feedbacks"]
    assert "st" in feedbacks and "se" in feedbacks and "e" in feedbacks
    assert council.planner.plan_revision.call_args.kwargs["canon_aware"] is True


def test_initial_inner_earth_skips_world_builder():
    council = WritingCouncil()
    council.planner.run = MagicMock(return_value={
        "agent": "PlanningAgent", "output": "<<<WORLD_CLASS: EARTH>>>\n<<<SECTION 1>>>\nB."})
    council.world_builder.run = MagicMock()
    council.writer.run = MagicMock(return_value={
        "agent": "WriterAgent", "output": "<<<SECTION 1>>>\nS.", "revised_sections": None})
    council.consistency.run = MagicMock(return_value={"output": "c", "agent": "C"})
    council.ai_checker.run = MagicMock(return_value={"output": "a", "agent": "A"})
    council.engine.run = MagicMock(return_value={"output": "e", "agent": "E"})
    council.planner.plan_revision = MagicMock(return_value={"output": "rp", "agent": "P"})
    council.writer.revise = MagicMock(return_value={
        "agent": "WriterAgent", "output": "final", "revised_sections": None})

    _, _, world_class, canon, bible, _ = council._run_inner(
        idea="i", target_length="1k", target_audience="a")

    assert world_class == wc.EARTH
    assert canon == "" and bible == ""
    council.world_builder.run.assert_not_called()
    # Engine reviewer runs on EARTH too, with the plan and no canon.
    council.engine.run.assert_called_once()
    assert council.engine.run.call_args.kwargs["canon_sheet"] == ""
    assert "e" in council.planner.plan_revision.call_args.kwargs["feedbacks"]
    # Writer still gets Opus on the INITIAL write (existing behavior), canon empty.
    assert council.writer.run.call_args.kwargs["model"] == INITIAL_DRAFT_MODEL
    assert council.writer.run.call_args.kwargs["canon_sheet"] == ""
    council.planner.plan_revision.assert_called_with(
        story=council.planner.plan_revision.call_args.kwargs["story"],
        plan=council.planner.plan_revision.call_args.kwargs["plan"],
        feedbacks=council.planner.plan_revision.call_args.kwargs["feedbacks"],
        canon_aware=False)


def test_run_threads_world_class_into_middle_and_prose():
    council = WritingCouncil()
    council._run_inner = MagicMock(
        return_value=("plan", "<<<SECTION 1>>>\nD.", wc.NON_EARTH, "CANON", "BIBLE", ""))
    council._run_middle = MagicMock(return_value="<<<SECTION 1>>>\nM.")
    council._run_prose_pass = MagicMock(return_value="<<<SECTION 1>>>\nP.")

    council.run(idea="i", target_length="1k", target_audience="a")

    assert council._run_middle.call_args.kwargs["world_class"] == wc.NON_EARTH
    assert council._run_middle.call_args.kwargs["canon_sheet"] == "CANON"
    assert council._run_prose_pass.call_args.kwargs["world_class"] == wc.NON_EARTH
    assert council._run_prose_pass.call_args.kwargs["world_bible"] == "BIBLE"


def test_constraint_threads_into_planner_and_writer():
    council = WritingCouncil()
    council.planner.run = MagicMock(return_value={
        "agent": "PlanningAgent", "output": "<<<SECTION 1>>>\nB."})
    council.writer.run = MagicMock(return_value={
        "agent": "WriterAgent", "output": "<<<SECTION 1>>>\nS.", "revised_sections": None})
    council.consistency.run = MagicMock(return_value={"output": "c", "agent": "C"})
    council.ai_checker.run = MagicMock(return_value={"output": "a", "agent": "A"})
    council.engine.run = MagicMock(return_value={"output": "e", "agent": "E"})
    council.planner.plan_revision = MagicMock(return_value={"output": "rp", "agent": "P"})
    council.writer.revise = MagicMock(return_value={
        "agent": "WriterAgent", "output": "final", "revised_sections": None})

    council._run_inner(idea="i", target_length="1k", target_audience="a",
                       constraint="exactly 5 words")

    assert council.planner.run.call_args.kwargs["constraint"] == "exactly 5 words"
    assert council.writer.run.call_args.kwargs["constraint"] == "exactly 5 words"
    # And the final revise pass carries it too.
    assert council.writer.revise.call_args.kwargs["constraint"] == "exactly 5 words"


def test_run_surfaces_deterministic_constraint_check():
    council = WritingCouncil()
    council._run_inner = MagicMock(
        return_value=("plan", "<<<SECTION 1>>>\none two three", False, "", "", ""))
    council._run_middle = MagicMock(return_value="<<<SECTION 1>>>\none two three")
    council._run_prose_pass = MagicMock(return_value="<<<SECTION 1>>>\none two three")

    result = council.run(idea="i", target_length="1k", target_audience="a",
                         constraint="exactly 3 words")

    cc = result["constraint_check"]
    assert cc is not None and cc["passed"] is True
    assert cc["checks"][0]["actual"] == 3

    # No constraint -> no check.
    council._run_inner = MagicMock(
        return_value=("plan", "<<<SECTION 1>>>\nx", False, "", "", ""))
    council._run_middle = MagicMock(return_value="<<<SECTION 1>>>\nx")
    council._run_prose_pass = MagicMock(return_value="<<<SECTION 1>>>\nx")
    assert council.run(idea="i", target_length="1k",
                       target_audience="a")["constraint_check"] is None


def test_parse_world_class_non_earth():
    council = WritingCouncil()
    plan = "<<<WORLD_CLASS: NON-EARTH>>>\n<<<SECTION 1>>>\nBody."
    world_class, stripped = council._parse_world_class(plan)
    assert world_class == wc.NON_EARTH
    assert "WORLD_CLASS" not in stripped
    assert stripped.startswith("<<<SECTION 1>>>")


def test_parse_world_class_earth_and_missing():
    council = WritingCouncil()
    assert council._parse_world_class("<<<WORLD_CLASS: EARTH>>>\nx")[0] == wc.EARTH
    world_class, stripped = council._parse_world_class("no tag here")
    assert world_class == wc.EARTH and stripped == "no tag here"


def test_parse_world_class_secondary():
    council = WritingCouncil()
    world_class, stripped = council._parse_world_class(
        "<<<WORLD_CLASS: SECONDARY>>>\n<<<SECTION 1>>>\nBody.")
    assert world_class == wc.SECONDARY
    assert stripped.startswith("<<<SECTION 1>>>")


def test_parse_world_class_override_beats_the_tag_and_still_strips_it():
    """The writer must never see the tag, whoever decided the class."""
    council = WritingCouncil()
    plan = "<<<WORLD_CLASS: NON-EARTH>>>\n<<<SECTION 1>>>\nBody."
    world_class, stripped = council._parse_world_class(plan, override=wc.SECONDARY)
    assert world_class == wc.SECONDARY
    assert "WORLD_CLASS" not in stripped


def test_parse_world_class_unreadable_tag_falls_back_to_earth():
    """An unknown tier buys nothing rather than accidentally buying the harness."""
    council = WritingCouncil()
    assert council._parse_world_class("<<<WORLD_CLASS: MOON>>>\nx")[0] == wc.EARTH


def test_prose_pass_variance_sees_full_story_and_gets_canon():
    """Variance counts repeated techniques, so it must get the whole draft — not the
    section subset the Inner fan-out sometimes works on — plus the canon sheet."""
    council = WritingCouncil()
    council.consistency.run = MagicMock(
        return_value={"agent": "ConsistencyAgent", "output": "cons"})
    council.ai_checker.run_prose = MagicMock(
        return_value={"agent": "AIFailureCheckerAgent", "output": "prose"})
    council.variance.run = MagicMock(
        return_value={"agent": "VarianceReviewerAgent", "output": "var"})
    council.planner.plan_revision_prose = MagicMock(
        return_value={"agent": "PlanningAgent", "output": "revplan"})
    council.writer.revise = MagicMock(
        return_value={"agent": "WriterAgent", "output": "final", "revised_sections": None})

    full = "<<<SECTION 1>>>\nA.\n\n<<<SECTION 2>>>\nB."
    council._run_prose_pass(plan="plan", story=full, top_n=7, label="prose.1",
                            world_class=wc.NON_EARTH, canon_sheet="CANON")

    council.variance.run.assert_called_once_with(
        story=full, top_n=7, canon_sheet="CANON")


def _secondary_council():
    council = WritingCouncil()
    council.planner.run = MagicMock(return_value={
        "agent": "PlanningAgent",
        "output": "<<<WORLD_CLASS: SECONDARY>>>\n<<<SECTION 1>>>\nBody."})
    council.world_builder.run = MagicMock(return_value={
        "agent": "WorldBuilderAgent", "output": "o",
        "canon_sheet": "CANON", "world_bible": ""})
    council.planner.revise_with_world_bible = MagicMock()
    council.writer.run = MagicMock(return_value={
        "agent": "WriterAgent", "output": "<<<SECTION 1>>>\nStory.",
        "revised_sections": None})
    council.consistency.run = MagicMock(return_value={"output": "c", "agent": "C"})
    council.ai_checker.run = MagicMock(return_value={"output": "a", "agent": "A"})
    council.engine.run = MagicMock(return_value={"output": "e", "agent": "E"})
    council.strangeness.run = MagicMock(return_value={"output": "st", "agent": "S"})
    council.sensory.run = MagicMock(return_value={"output": "se", "agent": "Se"})
    council.planner.plan_revision = MagicMock(return_value={"output": "rp", "agent": "P"})
    council.writer.revise = MagicMock(return_value={
        "agent": "WriterAgent", "output": "<<<SECTION 1>>>\nFinal.",
        "revised_sections": None})
    return council


def test_secondary_builds_canon_only_and_skips_the_alien_harness():
    """The tier that fixes the wands-in-Britain run: rules, but no bible, no bible-driven
    plan rewrite, no Opus-on-every-pass, and neither strangeness reviewer."""
    council = _secondary_council()

    _, _, world_class, canon, bible, _ = council._run_inner(
        idea="i", target_length="1k", target_audience="a")

    assert world_class == wc.SECONDARY
    assert canon == "CANON" and bible == ""
    assert council.world_builder.run.call_args.kwargs["canon_only"] is True
    council.planner.revise_with_world_bible.assert_not_called()
    council.strangeness.run.assert_not_called()
    council.sensory.run.assert_not_called()
    # Revisions drop back to the default model; only NON-EARTH keeps Opus throughout.
    assert council.writer.revise.call_args.kwargs["model"] is None


def test_secondary_still_makes_the_reviewers_canon_aware():
    """A canon sheet exists, so findings get bucketed [CRAFT]/[WORLD] as on NON-EARTH."""
    council = _secondary_council()

    council._run_inner(idea="i", target_length="1k", target_audience="a")

    assert council.engine.run.call_args.kwargs["canon_sheet"] == "CANON"
    assert council.consistency.run.call_args.kwargs["canon_sheet"] == "CANON"
    assert council.planner.plan_revision.call_args.kwargs["canon_aware"] is True


def test_world_class_override_beats_the_planners_tag():
    council = _secondary_council()

    _, _, world_class, _, _, _ = council._run_inner(
        idea="i", target_length="1k", target_audience="a",
        world_class_override=wc.EARTH)

    assert world_class == wc.EARTH
    council.world_builder.run.assert_not_called()


def test_run_rejects_an_unknown_world_class_before_spending_anything():
    council = WritingCouncil()
    council._run_inner = MagicMock()
    try:
        council.run(idea="i", target_length="1k", target_audience="a",
                    world_class="Mars")
    except ValueError as exc:
        assert "Mars" in str(exc)
    else:
        raise AssertionError("expected a ValueError")
    council._run_inner.assert_not_called()


def test_run_returns_world_class_alongside_the_legacy_flag():
    council = WritingCouncil()
    council._run_inner = MagicMock(
        return_value=("plan", "<<<SECTION 1>>>\nD.", wc.SECONDARY, "CANON", "", ""))
    council._run_middle = MagicMock(return_value="<<<SECTION 1>>>\nM.")
    council._run_prose_pass = MagicMock(return_value="<<<SECTION 1>>>\nP.")

    result = council.run(idea="i", target_length="1k", target_audience="a")

    assert result["world_class"] == wc.SECONDARY
    # non_earth stays a NON-EARTH-only flag: the server, CLI, and UI all read it.
    assert result["non_earth"] is False
