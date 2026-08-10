from collections import Counter
from unittest.mock import patch

import pytest

import prompt_harness as harness


def _fake_input(mapping, default="x"):
    """Fake input(): match the prompt against mapping keys by substring.

    Two guards keep a wrong answer from stalling the suite, since the harness
    re-prompts required fields forever:

    * A bare input() (prompt "") is _ask_multiline reading a body line. Raise
      EOFError, exactly as a closed stdin would, so the read terminates.
    * Asking the same question a third time means the harness is looping on a
      value this test meant to supply — fail loudly instead of hanging.
    """
    asked = Counter()

    def _fake(prompt=""):
        if not prompt:
            raise EOFError
        asked[prompt] += 1
        assert asked[prompt] < 3, f"harness is looping on prompt: {prompt!r}"
        for key, value in mapping.items():
            if key.lower() in prompt.lower():
                return value
        return default
    return _fake


def _result():
    return {"story": "s", "log": [], "planning_details": "d",
            "intake_brief": "=== STORY BRIEF ==="}


def test_rewrite_answers_are_threaded_into_the_run(tmp_path):
    story = tmp_path / "sforzato.txt"
    story.write_text("The fleet dropped out of the lane.", encoding="utf-8")
    answers = {
        "story title": "The Sforzato",
        "author": "Owen",
        "existing story": str(story),
        "rewrite mode": "revise",
        "changed in the rewrite": "darker ending",
        "target audience": "Adults",
        "launch": "y",
    }
    with patch("builtins.input", _fake_input(answers)), \
            patch.object(harness, "WritingCouncil") as MockCouncil, \
            patch.object(harness, "save_as_manuscript", return_value="out.docx"):
        MockCouncil.return_value.run.return_value = _result()
        harness.main()
    kwargs = MockCouncil.return_value.run.call_args.kwargs
    assert kwargs["source_story"] == "The fleet dropped out of the lane."
    assert kwargs["source_filename"] == str(story)
    assert kwargs["rewrite_mode"] == "revise"
    assert kwargs["rewrite_notes"] == "darker ending"


def test_blank_length_and_audience_stay_blank_with_a_source_story(tmp_path):
    """Blank means blank: the merge takes those values from the brief."""
    story = tmp_path / "s.txt"
    story.write_text("prose", encoding="utf-8")
    answers = {
        "story title": "T",
        "author": "A",
        "existing story": str(story),
        "rewrite mode": "reimagine",
        "target length": "",
        "target audience": "",
        "launch": "y",
    }
    with patch("builtins.input", _fake_input(answers)), \
            patch.object(harness, "WritingCouncil") as MockCouncil, \
            patch.object(harness, "save_as_manuscript", return_value="out.docx"):
        MockCouncil.return_value.run.return_value = _result()
        harness.main()
    kwargs = MockCouncil.return_value.run.call_args.kwargs
    assert kwargs["target_length"] == ""
    assert kwargs["target_audience"] == ""


def test_idea_is_asked_but_optional_when_a_source_story_is_given(capsys, tmp_path):
    """A rewrite can be steered by an idea; skipping it is the normal answer."""
    story = tmp_path / "s.txt"
    story.write_text("prose", encoding="utf-8")
    answers = {
        "story title": "T",
        "author": "A",
        "existing story": str(story),
        "rewrite mode": "reimagine",
        "target audience": "Adults",
        "launch": "y",
    }
    with patch("builtins.input", _fake_input(answers)), \
            patch.object(harness, "WritingCouncil") as MockCouncil, \
            patch.object(harness, "save_as_manuscript", return_value="out.docx"):
        MockCouncil.return_value.run.return_value = _result()
        harness.main()
    # _ask_multiline prints its prompt rather than passing it to input(), so
    # stdout is where the idea question shows up. The fake ends the multiline
    # read immediately, standing in for a user who just presses Enter.
    assert "Story idea" in capsys.readouterr().out
    assert MockCouncil.return_value.run.call_args.kwargs["idea"] == ""


def test_an_idea_typed_on_a_rewrite_reaches_the_run(tmp_path):
    story = tmp_path / "s.txt"
    story.write_text("prose", encoding="utf-8")
    answers = {"story title": "T", "author": "A", "existing story": str(story),
               "rewrite mode": "reimagine", "target audience": "Adults",
               "launch": "y"}
    with patch("builtins.input", _fake_input(answers)), \
            patch.object(harness, "WritingCouncil") as MockCouncil, \
            patch.object(harness, "save_as_manuscript", return_value="out.docx"), \
            patch.object(harness, "_ask_multiline", return_value="steer it darker"):
        MockCouncil.return_value.run.return_value = _result()
        harness.main()
    assert MockCouncil.return_value.run.call_args.kwargs["idea"] == "steer it darker"


def test_an_unreadable_source_story_exits_cleanly(capsys, tmp_path):
    bad = tmp_path / "story.pdf"
    bad.write_text("prose", encoding="utf-8")
    answers = {"story title": "T", "author": "A", "existing story": str(bad)}
    with patch("builtins.input", _fake_input(answers)), \
            patch.object(harness, "WritingCouncil") as MockCouncil:
        with pytest.raises(SystemExit) as excinfo:
            harness.main()
    assert excinfo.value.code == 1
    assert "Could not read that story" in capsys.readouterr().out
    MockCouncil.assert_not_called()


def test_a_bad_rewrite_mode_exits_before_the_remaining_questions(capsys, tmp_path):
    story = tmp_path / "s.txt"
    story.write_text("prose", encoding="utf-8")
    answers = {"story title": "T", "author": "A", "existing story": str(story),
               "rewrite mode": "polish"}
    asked = []
    inner = _fake_input(answers)

    def _recording(prompt=""):
        asked.append(prompt)
        return inner(prompt)

    with patch("builtins.input", _recording), \
            patch.object(harness, "WritingCouncil") as MockCouncil:
        with pytest.raises(SystemExit) as excinfo:
            harness.main()
    assert excinfo.value.code == 1
    assert "polish" in capsys.readouterr().out
    # It bailed at the mode question, not after the whole interview.
    assert not any("audience" in p.lower() for p in asked)
    assert not any("changed in the rewrite" in p.lower() for p in asked)
    MockCouncil.assert_not_called()


def test_a_fresh_run_still_asks_for_the_idea():
    answers = {"story title": "T", "author": "A", "existing story": "",
               "target audience": "Adults", "launch": "y"}
    # _ask_multiline reads bare input() lines, which the fake terminates
    # immediately, so patch it directly to seed a non-empty idea.
    with patch("builtins.input", _fake_input(answers)), \
            patch.object(harness, "WritingCouncil") as MockCouncil, \
            patch.object(harness, "save_as_manuscript", return_value="out.docx"), \
            patch.object(harness, "_ask_multiline", return_value="a fresh idea"):
        MockCouncil.return_value.run.return_value = _result()
        harness.main()
    kwargs = MockCouncil.return_value.run.call_args.kwargs
    assert kwargs["idea"] == "a fresh idea"
    assert kwargs["source_story"] == ""
    assert kwargs["rewrite_mode"] == ""


def test_brief_is_printed_when_present(capsys, tmp_path):
    story = tmp_path / "s.txt"
    story.write_text("prose", encoding="utf-8")
    answers = {
        "story title": "T",
        "author": "A",
        "existing story": str(story),
        "rewrite mode": "reimagine",
        "launch": "y",
    }
    with patch("builtins.input", _fake_input(answers)), \
            patch.object(harness, "WritingCouncil") as MockCouncil, \
            patch.object(harness, "save_as_manuscript", return_value="out.docx"):
        MockCouncil.return_value.run.return_value = _result()
        harness.main()
    assert "STORY BRIEF" in capsys.readouterr().out
