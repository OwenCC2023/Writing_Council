from unittest.mock import patch

from agents.writer_agent import WriterAgent, SYSTEM_PROMPT, INITIAL_WRITE_MAX_TOKENS


def _revision(sections=(), notes="", ops=()):
    return {"structural_operations": list(ops),
            "section_revisions": [{"section": n, "instruction": t} for n, t in sections],
            "general_notes": notes}


NOTES = _revision(notes="notes")


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


def test_section_revisions_reach_only_their_sections():
    agent = WriterAgent()
    story = "<<<SECTION 1>>>\nalpha\n\n<<<SECTION 2>>>\nbeta\n\n<<<SECTION 3>>>\ngamma"
    with patch.object(agent, "_call_claude",
                      return_value="<<<SECTION 3>>>\nGAMMA") as m:
        result = agent.revise(plan="p", story=story, revision=_revision(
            [(3, "cut the simile in paragraph 2; delete the final sentence")]))
    prompt = m.call_args.args[1]
    assert "SECTION 3: cut the simile in paragraph 2; delete the final sentence" in prompt
    assert "alpha" not in prompt and "beta" not in prompt
    assert result["output"].endswith("<<<SECTION 3>>>\nGAMMA")
    assert result["revised_sections"] == [3]


def test_structural_operations_apply_without_a_model_call():
    agent = WriterAgent()
    story = "<<<SECTION 1>>>\nalpha\n\n<<<SECTION 2>>>\nbeta"
    with patch.object(agent, "_call_claude") as m:
        result = agent.revise(plan="p", story=story, revision=_revision(
            ops=[{"op": "MERGE", "section": 1, "target": 2}]))
    m.assert_not_called()
    assert result["output"] == "<<<SECTION 1>>>\nalpha\n\nbeta"


def test_general_notes_trigger_the_full_rewrite():
    agent = WriterAgent()
    story = "<<<SECTION 1>>>\nalpha"
    with patch.object(agent, "_call_claude", return_value="<<<SECTION 1>>>\nALPHA") as m:
        result = agent.revise(plan="p", story=story, revision=NOTES)
    assert "REVISION NOTES:\nnotes" in m.call_args.args[1]
    assert result["revised_sections"] is None


def test_unmarked_draft_renders_section_instructions_as_notes():
    agent = WriterAgent()
    with patch.object(agent, "_call_claude", return_value="revised") as m:
        agent.revise(plan="p", story="no markers", revision=_revision(
            [(2, "cut the dream")], notes="slow the ending"))
    assert "Section 2: cut the dream\nslow the ending" in m.call_args.args[1]


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
        agent.revise(plan="p", story="no markers", revision=NOTES,
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
        agent.revise(plan="p", story="no markers here", revision=NOTES, max_tokens=28000)
    assert m.call_args.kwargs["max_tokens"] == 28000


def test_section_revision_honors_an_explicit_budget():
    """Section-targeted path: a multi-section revision can exceed the 8192 default."""
    agent = WriterAgent()
    story = "<<<SECTION 1>>>\nalpha\n\n<<<SECTION 2>>>\nbeta"
    revision = _revision([(1, "tighten"), (2, "cut")])
    with patch.object(agent, "_call_claude",
                      return_value="<<<SECTION 1>>>\na\n\n<<<SECTION 2>>>\nb") as m:
        agent.revise(plan="p", story=story, revision=revision, max_tokens=28000)
    assert m.call_args.kwargs["max_tokens"] == 28000


def test_length_block_absent_without_a_target():
    """Existing prompt bytes are unchanged when no target is supplied."""
    agent = WriterAgent()
    with patch.object(agent, "_call_claude", return_value="story") as m:
        agent.run(plan="p")
    assert "TARGET LENGTH" not in m.call_args.args[0]


def test_length_block_reaches_run_and_revise():
    agent = WriterAgent()
    with patch.object(agent, "_call_claude", return_value="story") as m:
        agent.run(plan="p", target_length="14,589 words")
    system = m.call_args.args[0]
    assert "TARGET LENGTH: 14,589 words" in system
    # The instruction is per-section, not a running total the writer has to track.
    assert "Write each section to its own budget" in system
    assert "do not pad" in system

    with patch.object(agent, "_call_claude", return_value="revised") as m:
        agent.revise(plan="p", story="no markers here", revision=NOTES,
                     target_length="14,589 words")
    assert "TARGET LENGTH: 14,589 words" in m.call_args.args[0]
