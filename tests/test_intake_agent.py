from unittest.mock import patch

from agents.intake_agent import (
    BRIEF_FIELDS, BRIEF_SCHEMA, SYSTEM_PROMPT, IntakeAgent, brief_fields, render_brief)

_RAW = {
    "title": "The Sforzato",
    "world_class_guess": "NON-EARTH",
    "world_class_reason": "interstellar war, invented FTL physics",
    "genre": "military space opera",
    "setting": "a fallen empire's frontier systems",
    "world_rules": "hyperlanes connect only certain systems; FTL comms need relay ships",
    "characters": ["Admiral Ligatto — wants vindication, fears irrelevance, drives the "
                   "counteroffensive"],
    "plot": ["Ligatto launches the counteroffensive", "Republican forces fall back",
             "  ", "Frankfurt im Weltraum breaks the momentum"],
    "structure": "third limited, past tense, chronological",
    "intent": "make the reader feel the cost of a turning point nobody chose",
    "length": "8432 words",
    "synopsis": "A doomed empire's last offensive breaks on an accident of timing.",
}


def test_brief_fields_maps_every_schema_key_to_its_brief_field():
    fields = brief_fields(_RAW)
    assert list(fields) == BRIEF_FIELDS
    assert fields["TITLE"] == "The Sforzato"
    assert fields["WORLD RULES"].startswith("hyperlanes")
    assert fields["STORYLINE/STRUCTURE"] == "third limited, past tense, chronological"
    assert fields["LENGTH"] == "8432 words"
    assert fields["WORLD_CLASS_GUESS"] == "NON-EARTH — interstellar war, invented FTL physics"


def test_list_fields_become_one_line_per_entry_with_blanks_dropped():
    fields = brief_fields(_RAW)
    assert fields["PLOT"] == ("Ligatto launches the counteroffensive\n"
                              "Republican forces fall back\n"
                              "Frankfurt im Weltraum breaks the momentum")


def test_an_untitled_story_keeps_an_empty_title():
    fields = brief_fields(dict(_RAW, title=""))
    assert fields["TITLE"] == ""


def test_render_brief_keeps_the_block_the_planner_and_ui_read():
    text = render_brief(brief_fields(_RAW))
    lines = text.splitlines()
    assert lines[0] == "=== STORY BRIEF ==="
    assert lines[1] == "TITLE: The Sforzato"
    assert "SYNOPSIS: A doomed empire" in text
    # Field order is the brief's historical order.
    assert [l.split(":")[0] for l in lines if l.split(":")[0] in BRIEF_FIELDS] == BRIEF_FIELDS


def test_run_returns_fields_and_the_rendered_brief():
    agent = IntakeAgent()
    with patch.object(agent, "_call_claude_json", return_value=_RAW) as m:
        result = agent.run(story="x")
    assert m.call_args.args[2] is BRIEF_SCHEMA
    assert result["agent"] == "IntakeAgent"
    assert result["fields"] == brief_fields(_RAW)
    assert result["output"] == render_brief(result["fields"])


def test_run_injects_computed_word_count_not_a_guess():
    agent = IntakeAgent()
    with patch.object(agent, "_call_claude_json", return_value=_RAW) as m:
        agent.run(story="the prose", source_words=8432)
    user_prompt = m.call_args.args[1]
    assert "8432" in user_prompt
    assert "the prose" in user_prompt


def test_run_threads_rewrite_notes_into_the_prompt():
    agent = IntakeAgent()
    with patch.object(agent, "_call_claude_json", return_value=_RAW) as m:
        agent.run(story="the prose", rewrite_notes="cut it to 3,000 words")
    assert "cut it to 3,000 words" in m.call_args.args[1]


def test_system_prompt_orders_front_matter_ignored():
    assert "front matter" in SYSTEM_PROMPT


def test_world_class_guess_offers_all_three_tiers():
    assert BRIEF_SCHEMA["properties"]["world_class_guess"]["enum"] == [
        "EARTH", "SECONDARY", "NON-EARTH"]
    guess = next(l for l in SYSTEM_PROMPT.splitlines()
                 if l.startswith("- world_class_guess:"))
    assert "EARTH, SECONDARY, or NON-EARTH" in guess


def test_prompt_no_longer_polices_a_line_format():
    assert "Emit EXACTLY" not in SYSTEM_PROMPT
    assert "beginning of a line" not in SYSTEM_PROMPT
