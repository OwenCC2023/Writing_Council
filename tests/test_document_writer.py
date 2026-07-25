import io
import pytest
from document_writer import save_as_manuscript

STORY = "First paragraph.\n\nSecond paragraph."


def test_file_path_returns_path(tmp_path):
    out = str(tmp_path / "out.docx")
    result = save_as_manuscript(STORY, "Title", "Author", output_path=out)
    assert result == out
    assert (tmp_path / "out.docx").exists()


def test_bytesio_returns_seeked_buffer():
    buf = io.BytesIO()
    result = save_as_manuscript(STORY, "Title", "Author", output=buf)
    assert result is buf
    assert buf.tell() == 0          # seeked to start
    content = buf.read()
    assert content[:4] == b"PK\x03\x04"  # .docx is a ZIP


def test_neither_raises():
    with pytest.raises(ValueError, match="exactly one"):
        save_as_manuscript(STORY, "Title", "Author")


def test_both_raises(tmp_path):
    with pytest.raises(ValueError, match="exactly one"):
        save_as_manuscript(
            STORY, "Title", "Author",
            output_path=str(tmp_path / "x.docx"),
            output=io.BytesIO(),
        )


def test_save_as_manuscript_handles_marker_free_story():
    """run() now strips <<<SECTION>>> markers before document_writer sees the
    story. Confirm a marker-free story still produces a valid .docx."""
    import io
    from document_writer import save_as_manuscript

    buf = io.BytesIO()
    save_as_manuscript(
        story="First paragraph.\n\nSecond paragraph.",
        title="Test",
        author="Author",
        output=buf,
    )
    assert buf.getvalue()[:4] == b"PK\x03\x04"   # .docx is a ZIP
