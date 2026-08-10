from unittest.mock import patch
from agents.world_builder_agent import WorldBuilderAgent
from agents.base_agent import INITIAL_DRAFT_MODEL


def test_run_splits_canon_and_bible_and_uses_opus():
    fake = (
        "=== CANON SHEET ===\n"
        "Gravity is half Earth-normal.\n"
        "=== WORLD BIBLE ===\n"
        "The air smells of hot iron and ozone.\n"
    )
    agent = WorldBuilderAgent()
    with patch.object(agent, "_call_claude", return_value=fake) as m:
        result = agent.run(idea="i", plan="PLAN TEXT", world_rules="low gravity")

    assert "Gravity is half Earth-normal." in result["canon_sheet"]
    assert "Gravity is half Earth-normal." not in result["world_bible"]
    assert "hot iron and ozone" in result["world_bible"]
    assert "===" not in result["canon_sheet"]
    assert result["canon_sheet"] == "Gravity is half Earth-normal."
    # Opus, with headroom above the 8192 default so neither block truncates.
    assert m.call_args.kwargs["model"] == INITIAL_DRAFT_MODEL
    assert m.call_args.kwargs["max_tokens"] > 8192


def test_run_handles_missing_bible_header_gracefully():
    agent = WorldBuilderAgent()
    with patch.object(agent, "_call_claude", return_value="=== CANON SHEET ===\nRule."):
        result = agent.run(idea="i", plan="p")
    assert "Rule." in result["canon_sheet"]
    assert result["world_bible"] == ""


def test_canon_only_omits_the_bible_and_says_so():
    """SECONDARY tier: rules without a sensory bank the writer does not need."""
    agent = WorldBuilderAgent()
    with patch.object(agent, "_call_claude",
                      return_value="=== CANON SHEET ===\nHealed wood fails by spring.") as m:
        out = agent.run(idea="i", plan="p", canon_only=True)
    system, user = m.call_args.args[0], m.call_args.args[1]
    assert "SECONDARY" in system
    assert "Do NOT produce a world bible" in system
    assert "WORLD BIBLE" not in user
    assert out["canon_sheet"] == "Healed wood fails by spring."
    assert out["world_bible"] == ""


def test_full_build_still_asks_for_both_blocks():
    agent = WorldBuilderAgent()
    with patch.object(agent, "_call_claude", return_value="=== CANON SHEET ===\nc") as m:
        agent.run(idea="i", plan="p")
    assert "=== WORLD BIBLE ===" in m.call_args.args[0]
