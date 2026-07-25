from unittest.mock import patch

from agents.ai_failure_checker import AIFailureCheckerAgent


def test_run_prose_returns_expected_shape():
    agent = AIFailureCheckerAgent()
    with patch.object(agent, "_call_claude", return_value="1. AI dialect — ...") as m:
        result = agent.run_prose(story="<<<SECTION 1>>>\nHello there.", top_n=5)
    assert result == {"agent": "AIFailureCheckerAgent", "output": "1. AI dialect — ..."}
    m.assert_called_once()


def test_run_prose_prompt_carries_scope_framing_and_top_n():
    agent = AIFailureCheckerAgent()
    with patch.object(agent, "_call_claude", return_value="x") as m:
        agent.run_prose(story="<<<SECTION 1>>>\nHi.", top_n=3)
    system_prompt = m.call_args.args[0]
    user_prompt = m.call_args.args[1]
    assert "surviv" in system_prompt.lower()        # residue framing
    assert "OUT OF SCOPE" in system_prompt           # structural exclusion
    assert "3" in system_prompt                      # top_n injected into system
    assert "3" in user_prompt                        # and into user ask
