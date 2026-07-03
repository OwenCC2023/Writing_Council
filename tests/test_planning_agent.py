from unittest.mock import patch

from agents.planning_agent import PlanningAgent

_THREE_BLOCK = (
    "=== STRUCTURAL OPERATIONS ===\nNONE\n"
    "=== SECTION REVISIONS ===\nSECTION 1: cut the simile\n"
    "=== GENERAL NOTES ===\nNONE"
)


def test_plan_revision_prose_returns_expected_shape():
    agent = PlanningAgent()
    with patch.object(agent, "_call_claude", return_value=_THREE_BLOCK):
        result = agent.plan_revision_prose(
            story="<<<SECTION 1>>>\nHi.",
            plan="the plan",
            prose_feedback="1. AI dialect in section 1",
            consistency_feedback="no issues",
        )
    assert result == {"agent": "PlanningAgent", "output": _THREE_BLOCK}


def test_plan_revision_prose_prompt_carries_force_and_pins():
    agent = PlanningAgent()
    with patch.object(agent, "_call_claude", return_value="x") as m:
        agent.plan_revision_prose(
            story="<<<SECTION 1>>>\nHi.", plan="p",
            prose_feedback="findings", consistency_feedback="cons",
        )
    system_prompt = m.call_args.args[0]
    user_prompt = m.call_args.args[1]
    assert "FORCE ALL FIXES" in system_prompt
    assert "ONE LINE PER SECTION" in system_prompt
    assert "STRUCTURAL OPERATIONS is always NONE" in system_prompt
    assert "GENERAL NOTES is always NONE" in system_prompt
    assert "findings" in user_prompt        # prose feedback threaded in
    assert "cons" in user_prompt            # consistency feedback threaded in
