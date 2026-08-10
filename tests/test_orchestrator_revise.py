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
    council.peer_writer.run = MagicMock(return_value={"agent": "PeerWriterAgent", "output": "p"})
    council.editor.run = MagicMock(return_value={"agent": "EditorAgent", "output": "ed"})
    council.marketing.run = MagicMock(return_value={"agent": "MarketingAgent", "output": "m"})
    council.audience.run = MagicMock(return_value={"agent": "AudienceAgent", "output": "au"})
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
    # First call: the seeded branch runs the checker fan-out on the marked
    # original before any writer touches it. Later calls (the middle loop's
    # own inner pass) see the mocked writer.revise output instead — call_args
    # (the *last* call) would not have the markers.
    checked = council.consistency.run.call_args_list[0].kwargs["story"]
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


def test_revise_forwards_the_image_to_the_planner():
    council = _revise_council()
    council.run(idea="", target_length="", target_audience="Adults",
                source_story=_STORY, rewrite_mode="revise", prose_passes=0,
                image="photo.jpg")
    assert council.planner.run.call_args.kwargs["image"] == "photo.jpg"


def test_revise_planning_details_echo_the_image():
    council = _revise_council()
    result = council.run(idea="", target_length="", target_audience="Adults",
                         source_story=_STORY, rewrite_mode="revise", prose_passes=0,
                         image=["a.jpg", "b.png"])
    assert "a.jpg" in result["planning_details"]
    assert "b.png" in result["planning_details"]


def test_count_plan_sections_reads_decorated_section_headers():
    council = WritingCouncil()
    assert council._count_plan_sections(
        "**SECTION 1: Opening**\nbeat\n**SECTION 2: Turn**\nbeat") == 2
    assert council._count_plan_sections(
        "## SECTION 1\nbeat\n\n## SECTION 2\nbeat\n\n## SECTION 3\nbeat") == 3
    assert council._count_plan_sections(
        "SECTION 1: Opening\nSECTION 2: Turn") == 2


def test_count_plan_sections_still_reads_bare_numbering():
    council = WritingCouncil()
    assert council._count_plan_sections("1. Opening\n2. Turn\n3. Close") == 3


def test_count_plan_sections_ignores_numbered_sub_lists():
    council = WritingCouncil()
    plan = (
        "**SECTION 1: Opening**\n"
        "How it escalates: stake\n"
        "1. she arrives\n2. she waits\n3. she leaves\n"
        "**SECTION 2: Turn**\n"
        "1. he answers\n2. he lies\n"
    )
    assert council._count_plan_sections(plan) == 2


def test_revise_returns_populated_planning_details():
    council = _revise_council()
    result = council.run(idea="", target_length="", target_audience="Adults",
                         source_story=_STORY, rewrite_mode="revise",
                         rewrite_notes="darker ending", prose_passes=0)
    details = result["planning_details"]
    assert details
    assert "revise" in details
    assert "darker ending" in details
