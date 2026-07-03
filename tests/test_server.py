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
