from unittest.mock import patch

import pytest

import consult_the_council as cli


def _result():
    return {"story": "s", "log": [], "planning_details": "d",
            "constraint_check": None, "intake_brief": "=== STORY BRIEF ==="}


def test_fresh_run_passes_no_source_story(monkeypatch):
    monkeypatch.setattr(cli, "SOURCE_STORY_PATH", "")
    with patch.object(cli, "WritingCouncil") as MockCouncil, \
            patch.object(cli, "save_as_manuscript", return_value="out.docx"):
        MockCouncil.return_value.run.return_value = _result()
        cli.main()
    kwargs = MockCouncil.return_value.run.call_args.kwargs
    assert kwargs["source_story"] == ""
    assert kwargs["rewrite_mode"] == ""


def test_source_story_path_is_loaded_and_threaded(monkeypatch, tmp_path):
    story = tmp_path / "sforzato.txt"
    story.write_text("The fleet dropped out of the lane.", encoding="utf-8")
    monkeypatch.setattr(cli, "SOURCE_STORY_PATH", str(story))
    monkeypatch.setattr(cli, "REWRITE_MODE", "revise")
    monkeypatch.setattr(cli, "REWRITE_NOTES", "darker ending")
    with patch.object(cli, "WritingCouncil") as MockCouncil, \
            patch.object(cli, "save_as_manuscript", return_value="out.docx"):
        MockCouncil.return_value.run.return_value = _result()
        cli.main()
    kwargs = MockCouncil.return_value.run.call_args.kwargs
    assert kwargs["source_story"] == "The fleet dropped out of the lane."
    assert kwargs["source_filename"] == str(story)
    assert kwargs["rewrite_mode"] == "revise"
    assert kwargs["rewrite_notes"] == "darker ending"


def test_an_unreadable_source_story_exits_cleanly(monkeypatch, capsys, tmp_path):
    """A config typo should read as a message, not a traceback."""
    bad = tmp_path / "story.pdf"
    bad.write_text("prose", encoding="utf-8")
    monkeypatch.setattr(cli, "SOURCE_STORY_PATH", str(bad))
    with patch.object(cli, "WritingCouncil") as MockCouncil:
        with pytest.raises(SystemExit) as excinfo:
            cli.main()
    assert excinfo.value.code == 1
    out = capsys.readouterr().out
    assert "SOURCE_STORY_PATH" in out
    assert "Unsupported story file type" in out
    MockCouncil.assert_not_called()


def test_a_missing_source_story_exits_cleanly(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "SOURCE_STORY_PATH", str(tmp_path / "nope.txt"))
    with patch.object(cli, "WritingCouncil") as MockCouncil:
        with pytest.raises(SystemExit) as excinfo:
            cli.main()
    assert excinfo.value.code == 1
    assert "SOURCE_STORY_PATH" in capsys.readouterr().out
    MockCouncil.assert_not_called()


def test_brief_is_printed_when_present(monkeypatch, capsys, tmp_path):
    story = tmp_path / "s.txt"
    story.write_text("prose", encoding="utf-8")
    monkeypatch.setattr(cli, "SOURCE_STORY_PATH", str(story))
    with patch.object(cli, "WritingCouncil") as MockCouncil, \
            patch.object(cli, "save_as_manuscript", return_value="out.docx"):
        MockCouncil.return_value.run.return_value = _result()
        cli.main()
    assert "STORY BRIEF" in capsys.readouterr().out
