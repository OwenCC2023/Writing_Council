from unittest.mock import patch

from agents.variance_agent import VarianceReviewerAgent, SYSTEM_PROMPT
from agents.base_agent import DEFAULT_MODEL


def test_default_model_is_sonnet():
    """Counting one construction across a whole draft is the job; the cheap tier undercounts."""
    assert VarianceReviewerAgent().model == DEFAULT_MODEL


def test_run_passes_story_top_n_and_canon():
    agent = VarianceReviewerAgent()
    with patch.object(agent, "_call_claude", return_value="report") as m:
        out = agent.run(story="STORY BODY", top_n=3, canon_sheet="ammonia seas")
    assert out["agent"] == "VarianceReviewerAgent"
    assert out["output"] == "report"
    system, user = m.call_args.args[0], m.call_args.args[1]
    assert "STORY BODY" in user
    assert "ammonia seas" in system
    assert "3 most-repeated" in system


def test_prompt_demands_counts_quotes_and_cuts():
    for demand in ("COUNT", "verbatim", "AT LEAST HALF", "<<<SECTION N>>>"):
        assert demand in SYSTEM_PROMPT


def test_findings_are_always_craft_and_never_world_excused():
    """The whole point: a repeated move is not redeemed by fitting the world."""
    assert "[CRAFT]" in SYSTEM_PROMPT
    assert "Repetition is never excused" in SYSTEM_PROMPT


def test_canon_does_not_lower_authority():
    """Like PeerWriter — this agent must keep full authority near world-elements."""
    agent = VarianceReviewerAgent()
    with patch.object(agent, "_call_claude", return_value="r") as m:
        agent.run(story="s", canon_sheet="CANON")
    assert "lower your authority" not in m.call_args.args[0].lower()
