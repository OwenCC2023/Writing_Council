from unittest.mock import patch

from agents.writer_agent import WriterAgent


def test_run_threads_model_override_to_call():
    agent = WriterAgent()
    with patch.object(agent, "_call_claude", return_value="story") as m:
        agent.run(plan="p", model="claude-opus-4-8")
    assert m.call_args.kwargs["model"] == "claude-opus-4-8"


def test_run_defaults_model_to_none():
    agent = WriterAgent()
    with patch.object(agent, "_call_claude", return_value="story") as m:
        agent.run(plan="p")
    assert m.call_args.kwargs["model"] is None


def test_single_line_semicolon_fixes_both_survive():
    """The prose planner packs multiple same-section fixes into one line —
    confirm both survive parsing."""
    agent = WriterAgent()
    _ops, revisions, _notes = agent._parse_revision_plan(
        "=== STRUCTURAL OPERATIONS ===\nNONE\n"
        "=== SECTION REVISIONS ===\n"
        "SECTION 3: cut the simile in paragraph 2; delete the final sentence\n"
        "=== GENERAL NOTES ===\nNONE"
    )
    assert 3 in revisions
    assert "cut the simile" in revisions[3]
    assert "delete the final sentence" in revisions[3]


def test_two_lines_same_section_second_overwrites_first():
    """Documents the hazard the prose prompt must avoid: a second SECTION 3
    line silently replaces the first."""
    agent = WriterAgent()
    _ops, revisions, _notes = agent._parse_revision_plan(
        "=== STRUCTURAL OPERATIONS ===\nNONE\n"
        "=== SECTION REVISIONS ===\n"
        "SECTION 3: fix A\n"
        "SECTION 3: fix B\n"
        "=== GENERAL NOTES ===\nNONE"
    )
    assert revisions[3] == "fix B"
