from unittest.mock import patch

from agents.engine_agent import EngineReviewerAgent, WEIRD_SPINE_CLAUSE
from agents.base_agent import FEEDBACK_MODEL


def test_default_model_is_feedback_tier():
    assert EngineReviewerAgent().model == FEEDBACK_MODEL


def test_run_returns_agent_key_and_sees_plan_and_story():
    agent = EngineReviewerAgent()
    with patch.object(agent, "_call_claude", return_value="findings") as m:
        out = agent.run(plan="PLAN-TEXT", story="STORY-TEXT")
    assert out == {"agent": "EngineReviewerAgent", "output": "findings"}
    system_prompt, user_prompt = m.call_args.args[0], m.call_args.args[1]
    # The reviewer needs the plan (declared engine) and the story.
    assert "PLAN-TEXT" in user_prompt and "STORY-TEXT" in user_prompt
    # EARTH run: no canon, so no weird-with-spine clause.
    assert WEIRD_SPINE_CLAUSE.strip() not in system_prompt


def test_non_earth_adds_weird_spine_clause_and_canon():
    agent = EngineReviewerAgent()
    with patch.object(agent, "_call_claude", return_value="f") as m:
        agent.run(plan="P", story="S", canon_sheet="CANON RULES HERE")
    system_prompt = m.call_args.args[0]
    assert WEIRD_SPINE_CLAUSE.strip() in system_prompt
    assert "CANON RULES HERE" in system_prompt
