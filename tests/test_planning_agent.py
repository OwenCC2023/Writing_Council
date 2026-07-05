from unittest.mock import patch

from agents.base_agent import INITIAL_DRAFT_MODEL
from agents.planning_agent import PlanningAgent, REVISION_PLAN_SYSTEM_PROMPT

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


def test_run_threads_model_override_to_call():
    agent = PlanningAgent()
    with patch.object(agent, "_call_claude", return_value="plan") as m:
        agent.run(idea="i", target_length="1k", target_audience="a",
                  model="claude-opus-4-8")
    assert m.call_args.kwargs["model"] == "claude-opus-4-8"


def test_run_with_image_threads_model_override():
    agent = PlanningAgent()
    with patch.object(agent, "_call_claude_with_image", return_value="plan") as m:
        agent.run(idea="i", target_length="1k", target_audience="a",
                  image="photo.png", model="claude-opus-4-8")
    assert m.call_args.kwargs["model"] == "claude-opus-4-8"


def test_run_system_prompt_includes_world_class_instruction():
    agent = PlanningAgent()
    with patch.object(agent, "_call_claude", return_value="out") as m:
        agent.run(idea="i", target_length="1k", target_audience="a")
    system_prompt = m.call_args.args[0]
    assert "<<<WORLD_CLASS: NON-EARTH>>>" in system_prompt


def test_revise_with_world_bible_uses_opus_and_passes_inputs():
    agent = PlanningAgent()
    with patch.object(agent, "_call_claude", return_value="REVISED PLAN") as m:
        result = agent.revise_with_world_bible(
            plan="OLD PLAN", world_bible="smells of iron",
            canon_sheet="halved gravity", target_length="8,000 words")
    assert result["output"] == "REVISED PLAN"
    assert m.call_args.kwargs["model"] == INITIAL_DRAFT_MODEL
    user_prompt = m.call_args.args[1]
    assert "OLD PLAN" in user_prompt
    assert "smells of iron" in user_prompt
    assert "halved gravity" in user_prompt
    assert "8,000 words" in user_prompt


def test_plan_revision_earth_prompt_unchanged():
    agent = PlanningAgent()
    with patch.object(agent, "_call_claude", return_value="out") as m:
        agent.plan_revision(story="s", plan="p", feedbacks=["f"])
    assert m.call_args.args[0] == REVISION_PLAN_SYSTEM_PROMPT   # exact, unchanged


def test_plan_revision_non_earth_adds_bucket_clause():
    agent = PlanningAgent()
    with patch.object(agent, "_call_claude", return_value="out") as m:
        agent.plan_revision(story="s", plan="p", feedbacks=["f"], non_earth=True)
    sp = m.call_args.args[0]
    assert sp != REVISION_PLAN_SYSTEM_PROMPT
    assert "[WORLD]" in sp and "[CRAFT]" in sp


def test_plan_revision_prose_non_earth_drops_world_tag():
    agent = PlanningAgent()
    with patch.object(agent, "_call_claude", return_value="out") as m:
        agent.plan_revision_prose(story="s", plan="p", prose_feedback="pf",
                                  consistency_feedback="cf", non_earth=True)
    assert "[WORLD]" in m.call_args.args[0]
