import base64
import json
import os
import pytest
from unittest.mock import patch

import server as srv


@pytest.fixture
def client():
    srv.app.config["TESTING"] = True
    with srv.app.test_client() as c:
        yield c


def test_index_serves_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"html" in resp.data.lower()


def test_run_returns_story(client):
    with patch("server.WritingCouncil") as MockCouncil:
        MockCouncil.return_value.run.return_value = {
            "story": "Once upon a time.",
            "log": [],
        }
        resp = client.post(
            "/run",
            data=json.dumps({
                "idea": "A test story",
                "target_length": "1,000 words",
                "target_audience": "Testers",
            }),
            content_type="application/json",
        )
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["story"] == "Once upon a time."
    assert "log" in data


def test_run_passes_optional_fields_to_council(client):
    with patch("server.WritingCouncil") as MockCouncil:
        MockCouncil.return_value.run.return_value = {"story": "x", "log": []}
        client.post(
            "/run",
            data=json.dumps({
                "idea": "My idea",
                "target_length": "5,000 words",
                "target_audience": "Readers",
                "world_rules": "Magic exists",
                "framework": "Novel",
                "style": "Dark",
            }),
            content_type="application/json",
        )
    kwargs = MockCouncil.return_value.run.call_args.kwargs
    assert kwargs["world_rules"] == "Magic exists"
    assert kwargs["framework"] == "Novel"
    assert kwargs["style"] == "Dark"


def test_run_returns_500_on_exception(client):
    with patch("server.WritingCouncil") as MockCouncil:
        MockCouncil.return_value.run.side_effect = RuntimeError("council exploded")
        resp = client.post(
            "/run",
            data=json.dumps({"idea": "x", "target_length": "1k", "target_audience": "y"}),
            content_type="application/json",
        )
    assert resp.status_code == 500
    data = json.loads(resp.data)
    assert "error" in data
    assert "council exploded" in data["error"]


_PNG_DATA_URI = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def test_run_with_image_file(client):
    with patch("server.WritingCouncil") as MockCouncil:
        MockCouncil.return_value.run.return_value = {"story": "x", "log": []}
        resp = client.post(
            "/run",
            data=json.dumps({
                "idea": "Test",
                "target_length": "1,000 words",
                "target_audience": "Testers",
                "image_file": _PNG_DATA_URI,
                "image_filename": "test.png",
            }),
            content_type="application/json",
        )
    assert resp.status_code == 200
    call_kwargs = MockCouncil.return_value.run.call_args.kwargs
    assert call_kwargs["image"] != ""   # temp file path was passed
    assert isinstance(call_kwargs["image"], str)  # legacy single-image stays a string


def test_run_with_multiple_image_files(client):
    import os

    captured = {}

    def fake_run(**kwargs):
        captured["image"] = kwargs["image"]
        # paths must still exist while the council is "running"
        assert all(os.path.exists(p) for p in kwargs["image"])
        return {"story": "x", "log": []}

    with patch("server.WritingCouncil") as MockCouncil:
        MockCouncil.return_value.run.side_effect = fake_run
        resp = client.post(
            "/run",
            data=json.dumps({
                "idea": "Test",
                "target_length": "1,000 words",
                "target_audience": "Testers",
                "image_files": [
                    {"data": _PNG_DATA_URI, "filename": "one.png"},
                    {"data": _PNG_DATA_URI, "filename": "two.png"},
                ],
            }),
            content_type="application/json",
        )
    assert resp.status_code == 200
    assert isinstance(captured["image"], list)
    assert len(captured["image"]) == 2
    # temp files are cleaned up after the request completes
    assert all(not os.path.exists(p) for p in captured["image"])


def test_run_response_includes_non_earth(client):
    with patch("server.WritingCouncil") as MockCouncil:
        MockCouncil.return_value.run.return_value = {
            "story": "Once upon a time.",
            "log": [],
            "non_earth": True,
        }
        resp = client.post(
            "/run",
            data=json.dumps({
                "idea": "A test story",
                "target_length": "1,000 words",
                "target_audience": "Testers",
            }),
            content_type="application/json",
        )
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "non_earth" in data
    assert data["non_earth"] is True


def test_save_returns_docx_bytes(client):
    resp = client.post(
        "/save",
        data=json.dumps({
            "story": "Once upon a time.\n\nThe end.",
            "title": "My Story",
            "author": "Jane",
        }),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.data[:4] == b"PK\x03\x04"   # .docx is a ZIP
    cd = resp.headers.get("Content-Disposition", "")
    assert "attachment" in cd
    assert "My" in cd  # filename contains title


def _b64(text: str) -> str:
    return "data:text/plain;base64," + base64.b64encode(text.encode()).decode()


def test_run_accepts_story_text_and_returns_the_brief(client):
    with patch("server.WritingCouncil") as MockCouncil:
        MockCouncil.return_value.run.return_value = {
            "story": "s", "log": [], "intake_brief": "=== STORY BRIEF ===",
            "rewrite_mode": "reimagine", "title": "The Sforzato",
            "target_length": "8432 words",
        }
        resp = client.post("/run", data=json.dumps({
            "story_text": "The fleet dropped out of the lane.",
            "rewrite_mode": "reimagine",
            "rewrite_notes": "darker ending",
        }), content_type="application/json")
    data = json.loads(resp.data)
    assert data["intake_brief"] == "=== STORY BRIEF ==="
    assert data["rewrite_mode"] == "reimagine"
    assert data["title"] == "The Sforzato"
    assert data["target_length"] == "8432 words"
    kwargs = MockCouncil.return_value.run.call_args.kwargs
    assert kwargs["source_story"] == "The fleet dropped out of the lane."
    assert kwargs["rewrite_notes"] == "darker ending"


def test_run_accepts_an_uploaded_story_file_and_deletes_the_temp(client):
    seen = {}

    def _fake_loader(path):
        seen["path"] = path
        return "loaded prose"

    with patch("server.WritingCouncil") as MockCouncil:
        MockCouncil.return_value.run.return_value = {"story": "s", "log": []}
        with patch("server.load_story_text", side_effect=_fake_loader):
            resp = client.post("/run", data=json.dumps({
                "story_file": {"data": _b64("prose here"), "filename": "sforzato.txt"},
            }), content_type="application/json")
    assert resp.status_code == 200
    kwargs = MockCouncil.return_value.run.call_args.kwargs
    assert kwargs["source_story"] == "loaded prose"
    assert kwargs["source_filename"] == "sforzato.txt"
    assert not os.path.exists(seen["path"])  # cleaned up in finally


def test_an_uploaded_file_wins_over_pasted_text(client):
    """Both supplied: the file is the deliberate act, so it takes the field."""
    with patch("server.WritingCouncil") as MockCouncil:
        MockCouncil.return_value.run.return_value = {"story": "s", "log": []}
        with patch("server.load_story_text", return_value="from the file"):
            resp = client.post("/run", data=json.dumps({
                "story_text": "pasted prose",
                "story_file": {"data": _b64("prose here"), "filename": "s.txt"},
            }), content_type="application/json")
    assert resp.status_code == 200
    assert MockCouncil.return_value.run.call_args.kwargs["source_story"] == "from the file"


def test_an_unnamed_story_upload_lands_on_a_readable_suffix(client):
    """Without a story-specific default the temp file got .png and was rejected."""
    seen = {}

    def _fake_loader(path):
        seen["path"] = path
        return "loaded prose"

    with patch("server.WritingCouncil") as MockCouncil:
        MockCouncil.return_value.run.return_value = {"story": "s", "log": []}
        with patch("server.load_story_text", side_effect=_fake_loader):
            resp = client.post("/run", data=json.dumps({
                "story_file": {"data": _b64("prose here"), "filename": ""},
            }), content_type="application/json")
    assert resp.status_code == 200
    assert seen["path"].endswith(".txt")


def test_a_story_file_without_data_is_a_400(client):
    with patch("server.WritingCouncil") as MockCouncil:
        resp = client.post("/run", data=json.dumps({
            "story_file": {"filename": "sforzato.txt"},
        }), content_type="application/json")
    assert resp.status_code == 400
    assert "data" in json.loads(resp.data)["error"]
    MockCouncil.return_value.run.assert_not_called()


def test_an_unreadable_story_upload_is_a_400_carrying_the_real_message(client):
    with patch("server.WritingCouncil") as MockCouncil:
        resp = client.post("/run", data=json.dumps({
            "story_file": {"data": _b64("%PDF-1.4"), "filename": "story.pdf"},
        }), content_type="application/json")
    assert resp.status_code == 400
    assert "Unsupported story file type" in json.loads(resp.data)["error"]
    MockCouncil.return_value.run.assert_not_called()


def test_an_empty_story_upload_is_a_400(client):
    with patch("server.WritingCouncil"):
        resp = client.post("/run", data=json.dumps({
            "story_file": {"data": _b64("   "), "filename": "story.txt"},
        }), content_type="application/json")
    assert resp.status_code == 400
    assert "empty" in json.loads(resp.data)["error"]


def test_run_skips_its_defaults_when_a_story_is_supplied(client):
    with patch("server.WritingCouncil") as MockCouncil:
        MockCouncil.return_value.run.return_value = {"story": "s", "log": []}
        client.post("/run", data=json.dumps({
            "story_text": "prose",
        }), content_type="application/json")
    kwargs = MockCouncil.return_value.run.call_args.kwargs
    assert kwargs["target_length"] == ""
    assert kwargs["target_audience"] == ""


def test_run_keeps_its_defaults_for_a_fresh_run(client):
    with patch("server.WritingCouncil") as MockCouncil:
        MockCouncil.return_value.run.return_value = {"story": "s", "log": []}
        client.post("/run", data=json.dumps({"idea": "fresh"}),
                    content_type="application/json")
    kwargs = MockCouncil.return_value.run.call_args.kwargs
    assert kwargs["target_length"] == "8,000 words"
    assert kwargs["target_audience"] == "Adult sci-fi readers"


def test_run_defaults_world_class_to_auto(client):
    with patch("server.WritingCouncil") as MockCouncil:
        MockCouncil.return_value.run.return_value = {"story": "x", "log": []}
        client.post("/run", data=json.dumps({"idea": "i"}),
                    content_type="application/json")
    assert MockCouncil.return_value.run.call_args.kwargs["world_class"] == "auto"


def test_run_threads_a_world_class_override(client):
    with patch("server.WritingCouncil") as MockCouncil:
        MockCouncil.return_value.run.return_value = {
            "story": "x", "log": [], "world_class": "SECONDARY", "non_earth": False}
        resp = client.post("/run",
                           data=json.dumps({"idea": "i", "world_class": "secondary"}),
                           content_type="application/json")
    assert MockCouncil.return_value.run.call_args.kwargs["world_class"] == "SECONDARY"
    assert json.loads(resp.data)["world_class"] == "SECONDARY"


def test_run_rejects_an_unknown_world_class_with_400(client):
    """A bad tier is a user mistake, like a bad file extension - not a 500."""
    with patch("server.WritingCouncil") as MockCouncil:
        resp = client.post("/run",
                           data=json.dumps({"idea": "i", "world_class": "Mars"}),
                           content_type="application/json")
    assert resp.status_code == 400
    assert "Mars" in json.loads(resp.data)["error"]
    MockCouncil.return_value.run.assert_not_called()
