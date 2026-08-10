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


def _system_prompt_with_canon(method_name, tmp_path):
    modes = tmp_path / "modes.md"
    modes.write_text("TAXONOMY", encoding="utf-8")
    agent = AIFailureCheckerAgent()
    with patch.object(agent, "_call_claude", return_value="out") as m:
        getattr(agent, method_name)(story="s", failure_modes_path=modes,
                                    canon_sheet="CANON")
    return m.call_args.args[0]


def test_canon_does_not_lower_this_agents_authority(tmp_path):
    """Authority-lowering near world-elements taught the tic detector to excuse tics as
    intentional ("[WORLD] — structural to the story"). It keeps full authority, like
    PeerWriter."""
    for method in ("run", "run_prose"):
        system = _system_prompt_with_canon(method, tmp_path)
        assert "CANON" in system
        assert "lower your authority" not in system.lower()
