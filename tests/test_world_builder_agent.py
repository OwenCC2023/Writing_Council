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
    # Opus, with headroom above the 8192 default so neither block truncates.
    assert m.call_args.kwargs["model"] == INITIAL_DRAFT_MODEL
    assert m.call_args.kwargs["max_tokens"] > 8192


def test_run_handles_missing_bible_header_gracefully():
    agent = WorldBuilderAgent()
    with patch.object(agent, "_call_claude", return_value="=== CANON SHEET ===\nRule."):
        result = agent.run(idea="i", plan="p")
    assert "Rule." in result["canon_sheet"]
    assert result["world_bible"] == ""
