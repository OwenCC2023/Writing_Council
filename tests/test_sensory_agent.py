from unittest.mock import patch

from agents.sensory_agent import (
    SensoryQuotaAgent, SYSTEM_PROMPT, DENSITY_FLOOR, DENSITY_CEILING,
)
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


def test_density_band_is_two_sided():
    """The agent used to be a one-way ratchet: it could only ever ask for more detail,
    and three write passes of that produced a measurement in every paragraph."""
    assert DENSITY_FLOOR < DENSITY_CEILING
    assert str(DENSITY_FLOOR) in SYSTEM_PROMPT and str(DENSITY_CEILING) in SYSTEM_PROMPT
    assert "SATURATED" in SYSTEM_PROMPT
    assert "CUT" in SYSTEM_PROMPT


def test_net_additive_instructions_are_forbidden_above_the_floor():
    assert "NET-ADDITIVE INSTRUCTIONS ARE FORBIDDEN" in SYSTEM_PROMPT
    assert "SWAP" in SYSTEM_PROMPT


def test_register_repetition_is_reported():
    """One register carrying the manuscript is a tic, not density."""
    assert "REGISTER REPETITION" in SYSTEM_PROMPT
    assert "temperature readings" in SYSTEM_PROMPT
    assert "[CRAFT]" in SYSTEM_PROMPT


def test_band_bounds_are_overridable_per_run():
    agent = SensoryQuotaAgent()
    with patch.object(agent, "_call_claude", return_value="r") as m:
        agent.run(story="s", floor=2, ceiling=99)
    system = m.call_args.args[0]
    assert "2–99 details per section" in system


def test_canon_does_not_lower_authority():
    agent = SensoryQuotaAgent()
    with patch.object(agent, "_call_claude", return_value="r") as m:
        agent.run(story="s", canon_sheet="CANON")
    assert "lower your authority" not in m.call_args.args[0].lower()
