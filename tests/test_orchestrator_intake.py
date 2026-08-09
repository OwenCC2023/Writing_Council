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
    # The middle loop always runs regardless of prose_passes; mock its four
    # reviewers too so these tests never make a real API call.
    council.peer_writer.run = MagicMock(return_value={"agent": "PeerWriterAgent", "output": "p"})
    council.editor.run = MagicMock(return_value={"agent": "EditorAgent", "output": "ed"})
    council.marketing.run = MagicMock(return_value={"agent": "MarketingAgent", "output": "m"})
    council.audience.run = MagicMock(return_value={"agent": "AudienceAgent", "output": "au"})
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
