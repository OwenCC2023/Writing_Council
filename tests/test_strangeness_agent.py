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
