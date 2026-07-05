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
