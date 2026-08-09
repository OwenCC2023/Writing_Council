from unittest.mock import patch

from agents.intake_agent import IntakeAgent, parse_brief, BRIEF_FIELDS

_BRIEF = """\
=== STORY BRIEF ===
TITLE: The Sforzato
WORLD_CLASS_GUESS: NON-EARTH — interstellar war, invented FTL physics
GENRE: military space opera
SETTING: a fallen empire's frontier systems
WORLD RULES: hyperlanes connect only certain systems; FTL comms need relay ships
CHARACTERS: Admiral Ligatto — wants vindication, fears irrelevance, drives the counteroffensive
PLOT: Ligatto launches the counteroffensive
  Republican forces fall back
  Frankfurt im Weltraum breaks the momentum
STORYLINE/STRUCTURE: third limited, past tense, chronological
INTENT: make the reader feel the cost of a turning point nobody chose
LENGTH: 8432 words
SYNOPSIS: A doomed empire's last offensive breaks on an accident of timing.
"""


def test_parse_brief_extracts_every_field():
    fields = parse_brief(_BRIEF)
    assert fields["TITLE"] == "The Sforzato"
    assert fields["GENRE"] == "military space opera"
    assert fields["LENGTH"] == "8432 words"
    assert fields["SYNOPSIS"].startswith("A doomed empire")


def test_parse_brief_keeps_multiline_field_bodies():
    fields = parse_brief(_BRIEF)
    assert "Republican forces fall back" in fields["PLOT"]
    assert "Frankfurt im Weltraum" in fields["PLOT"]
    # The next header ends the field.
    assert "STORYLINE" not in fields["PLOT"]


def test_parse_brief_missing_field_becomes_empty_string():
    fields = parse_brief("=== STORY BRIEF ===\nTITLE: Only This\n")
    assert fields["TITLE"] == "Only This"
    assert fields["PLOT"] == ""
    assert set(fields) == set(BRIEF_FIELDS)


def test_run_injects_computed_word_count_not_a_guess():
    agent = IntakeAgent()
    with patch.object(agent, "_call_claude", return_value=_BRIEF) as m:
        agent.run(story="the prose", source_words=8432)
    user_prompt = m.call_args.args[1]
    assert "8432" in user_prompt
    assert "the prose" in user_prompt


def test_run_threads_rewrite_notes_into_the_prompt():
    agent = IntakeAgent()
    with patch.object(agent, "_call_claude", return_value=_BRIEF) as m:
        agent.run(story="the prose", rewrite_notes="cut it to 3,000 words")
    assert "cut it to 3,000 words" in m.call_args.args[1]


def test_system_prompt_orders_front_matter_ignored():
    agent = IntakeAgent()
    with patch.object(agent, "_call_claude", return_value=_BRIEF) as m:
        agent.run(story="the prose")
    system_prompt = m.call_args.args[0]
    assert "front matter" in system_prompt
    assert "STORY BRIEF" in system_prompt


def test_run_returns_expected_shape():
    agent = IntakeAgent()
    with patch.object(agent, "_call_claude", return_value=_BRIEF):
        assert agent.run(story="x") == {"agent": "IntakeAgent", "output": _BRIEF}
