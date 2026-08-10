"""The writer's output budget must scale with target_length at EVERY writer call.

A long revise run makes only revise() calls; a long fresh run makes one run()
call and then revise() calls in the inner, middle, and prose passes. If any of
them falls back to the 16000 floor, that pass truncates work the previous pass
produced.
"""

from unittest.mock import MagicMock

from orchestrator import WritingCouncil

_LONG = "20,000 words"      # → max_tokens_for(...) == 28000
_EXPECTED = 28000

_STORY = ("The fleet dropped out of the lane.\n\n"
          "By morning the line had bent.\n\n"
          "At Frankfurt the timing failed him.")

_BRIEF = "=== STORY BRIEF ===\nTITLE: T\nLENGTH: 900 words\nSYNOPSIS: S\n"


def _council():
    council = WritingCouncil()
    council.intake.run = MagicMock(return_value={"agent": "IntakeAgent", "output": _BRIEF})
    council.planner.run = MagicMock(
        return_value={"agent": "PlanningAgent", "output": "<<<WORLD_CLASS: EARTH>>>\nplan"})
    council.sectionizer.run = MagicMock(
        return_value=["The fleet dropped out", "By morning the line",
                      "At Frankfurt the timing"])
    council.writer.run = MagicMock(
        return_value={"agent": "WriterAgent", "output": "story", "revised_sections": None})
    council.writer.revise = MagicMock(
        return_value={"agent": "WriterAgent", "output": "final", "revised_sections": None})
    council.consistency.run = MagicMock(return_value={"agent": "ConsistencyAgent", "output": "c"})
    council.ai_checker.run = MagicMock(return_value={"agent": "AIFailureCheckerAgent", "output": "a"})
    council.ai_checker.run_prose = MagicMock(
        return_value={"agent": "AIFailureCheckerAgent", "output": "pr"})
    council.engine.run = MagicMock(return_value={"agent": "EngineReviewerAgent", "output": "e"})
    council.planner.plan_revision = MagicMock(return_value={"agent": "PlanningAgent", "output": "rp"})
    council.planner.plan_revision_prose = MagicMock(
        return_value={"agent": "PlanningAgent", "output": "pp"})
    council.peer_writer.run = MagicMock(return_value={"agent": "PeerWriterAgent", "output": "p"})
    council.editor.run = MagicMock(return_value={"agent": "EditorAgent", "output": "ed"})
    council.marketing.run = MagicMock(return_value={"agent": "MarketingAgent", "output": "m"})
    council.audience.run = MagicMock(return_value={"agent": "AudienceAgent", "output": "au"})
    return council


def _budgets(mock):
    return [c.kwargs.get("max_tokens") for c in mock.call_args_list]


def test_seeded_revise_write_gets_the_long_budget():
    """The seeded inner loop's only writer call is write_2."""
    council = _council()
    council.run(idea="i", target_length=_LONG, target_audience="Adults",
                source_story=_STORY, rewrite_mode="revise", prose_passes=0)
    assert _budgets(council.writer.revise)[0] == _EXPECTED


def test_middle_loop_revise_gets_the_long_budget():
    council = _council()
    council.run(idea="a fresh idea", target_length=_LONG,
                target_audience="Adults", prose_passes=0)
    # calls: inner write_2, middle inner write_1, middle inner write_2
    assert _budgets(council.writer.revise) == [_EXPECTED] * 3


def test_prose_pass_revise_gets_the_long_budget():
    council = _council()
    council.run(idea="a fresh idea", target_length=_LONG,
                target_audience="Adults", prose_passes=1)
    assert _budgets(council.writer.revise)[-1] == _EXPECTED


def test_every_writer_call_on_a_long_run_gets_the_long_budget():
    council = _council()
    council.run(idea="a fresh idea", target_length=_LONG,
                target_audience="Adults", prose_passes=2)
    assert council.writer.run.call_args.kwargs["max_tokens"] == _EXPECTED
    assert set(_budgets(council.writer.revise)) == {_EXPECTED}


def test_a_short_run_still_gets_the_floor():
    """Regression guard: the threading is a ceiling raise, never a reduction."""
    from agents.writer_agent import INITIAL_WRITE_MAX_TOKENS
    council = _council()
    council.run(idea="a fresh idea", target_length="1,000 words",
                target_audience="Adults", prose_passes=1)
    assert set(_budgets(council.writer.revise)) == {INITIAL_WRITE_MAX_TOKENS}
