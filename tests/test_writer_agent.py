from unittest.mock import patch

from agents.writer_agent import WriterAgent, SYSTEM_PROMPT, INITIAL_WRITE_MAX_TOKENS


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


def test_run_earth_prompt_unchanged_and_no_model():
    agent = WriterAgent()
    with patch.object(agent, "_call_claude", return_value="story") as m:
        agent.run(plan="PLAN")
    assert m.call_args.args[0] == SYSTEM_PROMPT           # byte-identical
    assert m.call_args.kwargs.get("model") is None


def test_run_non_earth_injects_world_and_model():
    agent = WriterAgent()
    with patch.object(agent, "_call_claude", return_value="story") as m:
        agent.run(plan="PLAN", model="claude-opus-4-8",
                  canon_sheet="halved gravity", world_bible="smells of iron")
    sp = m.call_args.args[0]
    assert sp != SYSTEM_PROMPT
    assert "halved gravity" in sp and "smells of iron" in sp
    assert m.call_args.kwargs["model"] == "claude-opus-4-8"


def test_revise_forwards_model_on_fallback():
    agent = WriterAgent()
    # No section markers -> fallback rewrite path, single _call_claude.
    with patch.object(agent, "_call_claude", return_value="revised") as m:
        agent.revise(plan="p", story="no markers", feedback="notes",
                     model="claude-opus-4-8")
    assert m.call_args.kwargs["model"] == "claude-opus-4-8"


def test_run_defaults_to_the_existing_write_budget():
    agent = WriterAgent()
    with patch.object(agent, "_call_claude", return_value="story") as m:
        agent.run(plan="p")
    assert m.call_args.kwargs["max_tokens"] == INITIAL_WRITE_MAX_TOKENS


def test_run_honors_an_explicit_budget():
    agent = WriterAgent()
    with patch.object(agent, "_call_claude", return_value="story") as m:
        agent.run(plan="p", max_tokens=28000)
    assert m.call_args.kwargs["max_tokens"] == 28000


def test_revise_fallback_honors_an_explicit_budget():
    """No section markers in the draft -> full-rewrite fallback path."""
    agent = WriterAgent()
    with patch.object(agent, "_call_claude", return_value="story") as m:
        agent.revise(plan="p", story="no markers here", feedback="f", max_tokens=28000)
    assert m.call_args.kwargs["max_tokens"] == 28000
