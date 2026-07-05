import json
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
