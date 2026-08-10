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


def test_plan_revision_canon_aware_adds_bucket_clause():
    agent = PlanningAgent()
    with patch.object(agent, "_call_claude", return_value="out") as m:
        agent.plan_revision(story="s", plan="p", feedbacks=["f"], canon_aware=True)
    sp = m.call_args.args[0]
    assert sp != REVISION_PLAN_SYSTEM_PROMPT
    assert "[WORLD]" in sp and "[CRAFT]" in sp


def test_plan_revision_prose_canon_aware_drops_world_tag():
    agent = PlanningAgent()
    with patch.object(agent, "_call_claude", return_value="out") as m:
        agent.plan_revision_prose(story="s", plan="p", prose_feedback="pf",
                                  consistency_feedback="cf", canon_aware=True)
    assert "[WORLD]" in m.call_args.args[0]


from agents.planning_agent import PLAN_EXISTING_ADDENDUM


def test_run_without_new_params_leaves_prompts_unchanged():
    agent = PlanningAgent()
    with patch.object(agent, "_call_claude", return_value="plan") as m:
        agent.run(idea="i", target_length="1k", target_audience="a")
    user_prompt = m.call_args.args[1]
    assert "STORY BRIEF" not in user_prompt
    assert "REWRITE DIRECTIVE" not in user_prompt
    assert "ORIGINAL STORY TEXT" not in user_prompt
    assert PLAN_EXISTING_ADDENDUM not in m.call_args.args[0]


def test_run_threads_the_whole_brief_into_the_prompt():
    agent = PlanningAgent()
    brief = "=== STORY BRIEF ===\nCHARACTERS: Ligatto — wants vindication\nPLOT: he attacks"
    with patch.object(agent, "_call_claude", return_value="plan") as m:
        agent.run(idea="i", target_length="1k", target_audience="a", brief=brief)
    user_prompt = m.call_args.args[1]
    assert "Ligatto — wants vindication" in user_prompt
    assert "he attacks" in user_prompt


def test_run_renders_rewrite_notes_as_a_directive_block():
    agent = PlanningAgent()
    with patch.object(agent, "_call_claude", return_value="plan") as m:
        agent.run(idea="i", target_length="1k", target_audience="a",
                  rewrite_notes="cut it to 3,000 words")
    user_prompt = m.call_args.args[1]
    assert "REWRITE DIRECTIVE" in user_prompt
    assert "cut it to 3,000 words" in user_prompt
    assert "outranks" in user_prompt.lower()


def test_plan_existing_adds_addendum_and_source_story():
    agent = PlanningAgent()
    with patch.object(agent, "_call_claude", return_value="plan") as m:
        agent.run(idea="i", target_length="1k", target_audience="a",
                  source_story="The fleet dropped out of the lane.", plan_existing=True)
    assert PLAN_EXISTING_ADDENDUM in m.call_args.args[0]
    assert "The fleet dropped out of the lane." in m.call_args.args[1]


def test_plan_existing_addendum_overrides_non_earth_chunking():
    assert "MORE, SMALLER" in PLAN_EXISTING_ADDENDUM or "more, smaller" in PLAN_EXISTING_ADDENDUM
    assert "scene structure" in PLAN_EXISTING_ADDENDUM


def test_plan_revision_prose_threads_variance_feedback_as_force_fixed():
    agent = PlanningAgent()
    with patch.object(agent, "_call_claude", return_value="x") as m:
        agent.plan_revision_prose(
            story="<<<SECTION 1>>>\nHi.", plan="p",
            prose_feedback="findings", consistency_feedback="cons",
            variance_feedback="temperature readings x38",
        )
    user_prompt = m.call_args.args[1]
    assert "temperature readings x38" in user_prompt
    assert "REPEATED-TECHNIQUE FINDINGS (every one MUST be fixed" in user_prompt
    # The fix for a repeated move is removal, not a hedge bolted onto it.
    assert "never by adding a qualifier to it" in user_prompt


def test_plan_revision_prose_omits_variance_block_when_empty():
    agent = PlanningAgent()
    with patch.object(agent, "_call_claude", return_value="x") as m:
        agent.plan_revision_prose(story="s", plan="p", prose_feedback="f",
                                  consistency_feedback="c")
    assert "REPEATED-TECHNIQUE" not in m.call_args.args[1]


def test_classifier_offers_three_tiers_and_a_sensory_test():
    from agents.planning_agent import CLASSIFY_ADDENDUM
    for tag in ("<<<WORLD_CLASS: EARTH>>>", "<<<WORLD_CLASS: SECONDARY>>>",
                "<<<WORLD_CLASS: NON-EARTH>>>"):
        assert tag in CLASSIFY_ADDENDUM
    # The test is sensory ground, not rule count: wands in Britain is SECONDARY.
    assert "WOULD A READER'S BODY KNOW THIS ROOM" in CLASSIFY_ADDENDUM
    assert "SENSORY GROUND, not by how many rules differ" in CLASSIFY_ADDENDUM
    # Only the top tier chunks smaller, and the prompt says the tier is expensive.
    assert "If and only if NON-EARTH" in CLASSIFY_ADDENDUM
    assert "expensive" in CLASSIFY_ADDENDUM


def test_fix_plan_length_shows_the_planner_exact_arithmetic():
    from agents.planning_agent import LENGTH_FIX_SYSTEM_PROMPT, PLAN_FIX_MAX_TOKENS
    agent = PlanningAgent()
    check = {"declared": 6050, "target": 14589, "ratio": 0.4147, "sections": 8,
             "passed": False}
    with patch.object(agent, "_call_claude", return_value="FIXED PLAN") as m:
        result = agent.fix_plan_length(plan="OLD PLAN", target_length="14,589 words",
                                       check=check)
    assert result == {"agent": "PlanningAgent", "output": "FIXED PLAN"}
    user_prompt = m.call_args.args[1]
    assert "6,050 words" in user_prompt
    assert "41% of the 14,589-word target" in user_prompt
    assert "shortfall is 8,539 words" in user_prompt
    assert "OLD PLAN" in user_prompt
    assert m.call_args.args[0] == LENGTH_FIX_SYSTEM_PROMPT
    # A corrected plan is longer than the one it replaces; the 8192 default would cut it.
    assert m.call_args.kwargs["max_tokens"] == PLAN_FIX_MAX_TOKENS


def test_fix_plan_length_prompt_forbids_padding_the_numbers():
    from agents.planning_agent import LENGTH_FIX_SYSTEM_PROMPT
    assert "counted, not \\nestimated" in LENGTH_FIX_SYSTEM_PROMPT or \
           "counted, not estimated" in LENGTH_FIX_SYSTEM_PROMPT
    assert "do NOT pad" in LENGTH_FIX_SYSTEM_PROMPT
    assert "budget correction, not a re-conception" in LENGTH_FIX_SYSTEM_PROMPT
