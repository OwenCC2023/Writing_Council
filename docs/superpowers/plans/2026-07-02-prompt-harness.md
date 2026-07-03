# Prompt Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a browser-based UI (`server.py` + `static/index.html`) that lets the user fill in Writing Council prompt details, run the council, read the output, and download the manuscript as a `.docx` — without editing Python files.

**Architecture:** Flask serves a self-contained `static/index.html`; `POST /run` blocks until `WritingCouncil.run()` completes (may take minutes) and returns the story as JSON; `POST /save` accepts `{story, title, author}`, generates a `.docx` in-memory via a BytesIO-capable `save_as_manuscript`, and returns it as a browser file download. `document_writer.py` is extended to accept either a file path or a BytesIO buffer.

**Tech Stack:** Python 3.11, Flask 3.x, python-docx 1.2.0, pytest, vanilla HTML/CSS/JS (no build step).

## Global Constraints

- Python venv at `.venv/` — all pip/pytest commands use `.venv\Scripts\<exe>`
- Flask must run with `threaded=True` — council run blocks the thread for minutes
- `document_writer.py` existing call sites use keyword `output_path=` — making it default to `None` is backwards-compatible
- `static/index.html` must be self-contained — no external JS/CSS dependencies
- Active image tab wins — only the active tab's payload fields are sent to `/run`
- Image `image_file` arrives as a data URI (`data:image/png;base64,...`) — server strips the prefix before decoding

---

### Task 1: Branch setup and Flask dependency

**Files:**
- Modify: `requirements.txt`

**Interfaces:**
- Produces: `flask` and `pytest` available in `.venv`

- [ ] **Step 1: Switch to the feature branch**

```bash
git checkout feature/prompt-harness
```

If the branch doesn't exist locally yet: `git checkout -b feature/prompt-harness`

- [ ] **Step 2: Add flask and pytest to `requirements.txt`**

Full file contents:

```
anthropic>=0.40.0
python-dotenv>=1.0.0
python-docx>=1.1.0
flask>=3.0.0
pytest>=8.0.0
```

- [ ] **Step 3: Install**

```
.venv\Scripts\pip.exe install flask pytest
```

Expected: output ends with `Successfully installed flask-3.x.x ...`

- [ ] **Step 4: Verify**

```
.venv\Scripts\python.exe -c "import flask; print(flask.__version__)"
```

Expected: prints a version string like `3.1.0`

- [ ] **Step 5: Commit**

```bash
git add requirements.txt
git commit -m "Add flask and pytest to requirements"
```

---

### Task 2: Extend `document_writer.py` with BytesIO output

**Files:**
- Modify: `document_writer.py`
- Create: `tests/__init__.py`
- Create: `tests/test_document_writer.py`

**Interfaces:**
- Produces: `save_as_manuscript(story: str, title: str, author: str, output_path: str = None, output: io.BytesIO = None) -> str | io.BytesIO`
  - `output_path` given → saves to file, returns path string (existing behaviour)
  - `output` (BytesIO) given → writes into buffer, seeks to 0, returns the buffer
  - Neither or both provided → raises `ValueError("Provide exactly one of output_path or output")`

- [ ] **Step 1: Create the tests package**

Create `tests/__init__.py` as an empty file.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_document_writer.py`:

```python
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
```

- [ ] **Step 3: Run tests to confirm they fail**

```
.venv\Scripts\pytest.exe tests/test_document_writer.py -v
```

Expected: 4 failures (signature mismatch)

- [ ] **Step 4: Update `document_writer.py`**

Add `import io` at the top (after the existing `import re`):

```python
import io
import re
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_LINE_SPACING, WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
```

Replace the function signature:

```python
def save_as_manuscript(
    story: str,
    title: str,
    author: str,
    output_path: str = None,
    output: io.BytesIO = None,
):
```

Replace the final two lines of the function body (`doc.save(output_path)` and `return output_path`) with:

```python
    if (output_path is None) == (output is None):
        raise ValueError("Provide exactly one of output_path or output")
    if output_path is not None:
        doc.save(output_path)
        return output_path
    doc.save(output)
    output.seek(0)
    return output
```

- [ ] **Step 5: Run tests to confirm they pass**

```
.venv\Scripts\pytest.exe tests/test_document_writer.py -v
```

Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add document_writer.py tests/__init__.py tests/test_document_writer.py
git commit -m "Extend save_as_manuscript to support BytesIO output"
```

---

### Task 3: Implement `server.py`

**Files:**
- Create: `server.py`
- Create: `static/index.html` (placeholder — replaced in Task 4)
- Create: `tests/test_server.py`

**Interfaces:**
- Consumes: `save_as_manuscript(story, title, author, output=buf) -> io.BytesIO` from Task 2
- Consumes: `WritingCouncil().run(idea, target_length, target_audience, world_rules, framework, style, image) -> {"story": str, "log": list}`
- Produces:
  - `GET /` → 200 HTML
  - `POST /run` (JSON) → 200 `{"story": str, "log": list}` or 500 `{"error": str}`
  - `POST /save` (JSON `{story, title, author}`) → 200 `.docx` attachment

- [ ] **Step 1: Create `static/` directory with a placeholder `index.html`**

Create `static/index.html`:

```html
<!DOCTYPE html><html><body><p>placeholder</p></body></html>
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_server.py`:

```python
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
```

- [ ] **Step 3: Run tests to confirm they fail**

```
.venv\Scripts\pytest.exe tests/test_server.py -v
```

Expected: failures (`server` module not found)

- [ ] **Step 4: Create `server.py`**

```python
import base64
import io
import os
import tempfile
from pathlib import Path

from flask import Flask, jsonify, request, send_file

from document_writer import save_as_manuscript
from orchestrator import WritingCouncil

app = Flask(__name__, static_folder="static")


@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/run", methods=["POST"])
def run():
    data = request.get_json()
    image_path = None
    try:
        image = ""
        if data.get("image_file"):
            raw = data["image_file"]
            if "," in raw:
                raw = raw.split(",", 1)[1]
            image_bytes = base64.b64decode(raw)
            suffix = Path(data.get("image_filename", "upload.png")).suffix or ".png"
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmp.write(image_bytes)
            tmp.close()
            image_path = tmp.name
            image = image_path
        elif data.get("image_url"):
            image = data["image_url"]

        council = WritingCouncil()
        result = council.run(
            idea=data.get("idea", ""),
            target_length=data.get("target_length", "8,000 words"),
            target_audience=data.get("target_audience", "Adult sci-fi readers"),
            world_rules=data.get("world_rules", ""),
            framework=data.get("framework", ""),
            style=data.get("style", ""),
            image=image,
        )
        return jsonify({"story": result["story"], "log": result["log"]})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        if image_path and os.path.exists(image_path):
            os.unlink(image_path)


@app.route("/save", methods=["POST"])
def save():
    data = request.get_json()
    buf = io.BytesIO()
    save_as_manuscript(
        story=data["story"],
        title=data["title"],
        author=data["author"],
        output=buf,
    )
    filename = f"{data['title']}.docx"
    return send_file(
        buf,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


if __name__ == "__main__":
    app.run(debug=True, threaded=True)
```

- [ ] **Step 5: Run server tests**

```
.venv\Scripts\pytest.exe tests/test_server.py -v
```

Expected: 5 passed

- [ ] **Step 6: Run full suite**

```
.venv\Scripts\pytest.exe tests/ -v
```

Expected: 9 passed

- [ ] **Step 7: Commit**

```bash
git add server.py static/index.html tests/test_server.py
git commit -m "Add Flask server with /run and /save routes"
```

---

### Task 4: Implement `static/index.html`

**Files:**
- Modify: `static/index.html` (replace Task 3 placeholder)

**Interfaces:**
- Consumes: `POST /run` → `{"story": str, "log": list}` or `{"error": str}`
- Consumes: `POST /save` → `.docx` binary download

- [ ] **Step 1: Replace `static/index.html` with the full UI**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Writing Council</title>
<style>
  *, *::before, *::after { box-sizing: border-box; }
  body { font-family: Georgia, serif; background: #f5f0eb; color: #222; margin: 0; padding: 2rem; }
  .container { max-width: 780px; margin: 0 auto; }
  h1 { font-size: 1.6rem; margin-bottom: 1.5rem; }
  label { display: block; font-weight: bold; margin-top: 1rem; margin-bottom: 0.25rem; font-size: 0.9rem; }
  input[type="text"], textarea {
    width: 100%; padding: 0.5rem; font-family: inherit; font-size: 0.95rem;
    border: 1px solid #bbb; border-radius: 3px; background: #fff;
  }
  textarea { resize: vertical; min-height: 100px; }
  .optional { font-weight: normal; color: #666; font-size: 0.8rem; margin-left: 0.4rem; }
  .tabs { display: flex; margin-top: 1rem; }
  .tab-btn {
    padding: 0.4rem 1rem; border: 1px solid #bbb; background: #e8e0d8;
    cursor: pointer; font-size: 0.9rem; border-radius: 3px 3px 0 0;
    font-family: inherit;
  }
  .tab-btn.active { background: #fff; border-bottom-color: #fff; }
  .tab-panel { border: 1px solid #bbb; padding: 0.75rem; background: #fff; border-radius: 0 3px 3px 3px; }
  .hidden { display: none !important; }
  button[type="submit"] {
    margin-top: 1.5rem; padding: 0.6rem 1.4rem; font-size: 1rem;
    background: #3a3a3a; color: #fff; border: none; border-radius: 3px;
    cursor: pointer; font-family: inherit;
  }
  button[type="submit"]:disabled { background: #999; cursor: not-allowed; }
  #download-btn {
    display: block; margin-top: 0.75rem; padding: 0.6rem 1.4rem; font-size: 1rem;
    background: #2a6049; color: #fff; border: none; border-radius: 3px;
    cursor: pointer; font-family: inherit;
  }
  #spinner { margin-top: 1.5rem; font-style: italic; color: #555; }
  #output-section { margin-top: 2rem; }
  #output-section h2 { font-size: 1.1rem; margin-bottom: 0.5rem; }
  #story-output {
    width: 100%; min-height: 400px; font-family: "Times New Roman", serif;
    font-size: 0.95rem; padding: 0.75rem; border: 1px solid #bbb; border-radius: 3px;
  }
  .warning {
    background: #fff8e1; border: 1px solid #f0c040; padding: 0.5rem 0.75rem;
    border-radius: 3px; font-size: 0.85rem; margin-top: 0.75rem;
  }
  #error-msg {
    margin-top: 1rem; color: #c0392b; background: #fdecea;
    border: 1px solid #e57373; padding: 0.5rem 0.75rem; border-radius: 3px; font-size: 0.9rem;
  }
</style>
</head>
<body>
<div class="container">
  <h1>Writing Council</h1>

  <form id="council-form" novalidate>
    <label for="title">Title *</label>
    <input type="text" id="title" name="title">

    <label for="author">Author *</label>
    <input type="text" id="author" name="author">

    <label for="idea">Idea *</label>
    <textarea id="idea" name="idea" rows="5"></textarea>

    <label for="target_length">Target Length *</label>
    <input type="text" id="target_length" name="target_length" value="8,000 words">

    <label for="target_audience">Target Audience *</label>
    <input type="text" id="target_audience" name="target_audience" value="Adult sci-fi readers">

    <label for="world_rules">World Rules <span class="optional">(optional)</span></label>
    <textarea id="world_rules" name="world_rules" rows="4"></textarea>

    <label for="framework">Framework <span class="optional">(optional)</span></label>
    <input type="text" id="framework" name="framework" value="Short Story">

    <label for="style_field">Style <span class="optional">(optional)</span></label>
    <input type="text" id="style_field" name="style_field">

    <label>Image <span class="optional">(optional)</span></label>
    <div class="tabs">
      <button type="button" class="tab-btn active" id="tab-upload">Upload</button>
      <button type="button" class="tab-btn" id="tab-url">URL</button>
    </div>
    <div class="tab-panel">
      <div id="panel-upload">
        <input type="file" id="image_file" accept="image/jpeg,image/png,image/gif,image/webp">
      </div>
      <div id="panel-url" class="hidden">
        <input type="text" id="image_url" placeholder="https://example.com/image.png">
      </div>
    </div>

    <button type="submit" id="run-btn">Run Council</button>
  </form>

  <div id="spinner" class="hidden">&#8635; Council is working&hellip; (this may take several minutes)</div>
  <div id="error-msg" class="hidden"></div>

  <div id="output-section" class="hidden">
    <h2>Output</h2>
    <textarea id="story-output" readonly></textarea>
    <div class="warning">&#9888; Output is not saved &mdash; download before closing this tab.</div>
    <button id="download-btn">Download .docx</button>
  </div>
</div>

<script>
  const form         = document.getElementById('council-form');
  const runBtn       = document.getElementById('run-btn');
  const spinner      = document.getElementById('spinner');
  const errorMsg     = document.getElementById('error-msg');
  const outputSection = document.getElementById('output-section');
  const storyOutput  = document.getElementById('story-output');
  const downloadBtn  = document.getElementById('download-btn');
  const tabUpload    = document.getElementById('tab-upload');
  const tabUrl       = document.getElementById('tab-url');
  const panelUpload  = document.getElementById('panel-upload');
  const panelUrl     = document.getElementById('panel-url');

  // --- Image tab switching ---
  tabUpload.addEventListener('click', () => {
    tabUpload.classList.add('active');
    tabUrl.classList.remove('active');
    panelUpload.classList.remove('hidden');
    panelUrl.classList.add('hidden');
  });
  tabUrl.addEventListener('click', () => {
    tabUrl.classList.add('active');
    tabUpload.classList.remove('active');
    panelUrl.classList.remove('hidden');
    panelUpload.classList.add('hidden');
  });

  // --- Helpers ---
  function showError(msg) {
    errorMsg.textContent = msg;
    errorMsg.classList.remove('hidden');
    spinner.classList.add('hidden');
    runBtn.disabled = false;
  }

  function buildPayload(imageDataUrl) {
    const payload = {
      idea:             document.getElementById('idea').value.trim(),
      target_length:    document.getElementById('target_length').value.trim(),
      target_audience:  document.getElementById('target_audience').value.trim(),
      world_rules:      document.getElementById('world_rules').value.trim(),
      framework:        document.getElementById('framework').value.trim(),
      style:            document.getElementById('style_field').value.trim(),
    };
    const uploadActive = !panelUpload.classList.contains('hidden');
    if (uploadActive) {
      const file = document.getElementById('image_file').files[0];
      if (file && imageDataUrl) {
        payload.image_file     = imageDataUrl;   // full data URI — server strips prefix
        payload.image_filename = file.name;      // preserves extension for MIME detection
      }
    } else {
      const url = document.getElementById('image_url').value.trim();
      if (url) payload.image_url = url;
    }
    return payload;
  }

  function submitPayload(payload) {
    errorMsg.classList.add('hidden');
    runBtn.disabled = true;
    spinner.classList.remove('hidden');
    outputSection.classList.add('hidden');

    fetch('/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
      .then(r => r.json())
      .then(data => {
        spinner.classList.add('hidden');
        if (data.error) { showError(data.error); return; }
        storyOutput.value = data.story;
        outputSection.classList.remove('hidden');
        runBtn.disabled = false;
      })
      .catch(err => showError('Network error: ' + err.message));
  }

  // --- Form submit ---
  form.addEventListener('submit', e => {
    e.preventDefault();
    const REQUIRED = [
      ['title',           'Title'],
      ['author',          'Author'],
      ['idea',            'Idea'],
      ['target_length',   'Target Length'],
      ['target_audience', 'Target Audience'],
    ];
    for (const [id, label] of REQUIRED) {
      if (!document.getElementById(id).value.trim()) {
        showError('"' + label + '" is required.');
        return;
      }
    }
    const uploadActive = !panelUpload.classList.contains('hidden');
    const file = document.getElementById('image_file').files[0];
    if (uploadActive && file) {
      const reader = new FileReader();
      reader.onload = evt => submitPayload(buildPayload(evt.target.result));
      reader.readAsDataURL(file);
    } else {
      submitPayload(buildPayload(null));
    }
  });

  // --- Download ---
  downloadBtn.addEventListener('click', () => {
    const title  = document.getElementById('title').value.trim();
    const author = document.getElementById('author').value.trim();
    fetch('/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ story: storyOutput.value, title, author }),
    })
      .then(r => {
        if (!r.ok) throw new Error('Save failed (' + r.status + ')');
        return r.blob();
      })
      .then(blob => {
        const url = URL.createObjectURL(blob);
        const a   = document.createElement('a');
        a.href     = url;
        a.download = title + '.docx';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      })
      .catch(err => showError('Download failed: ' + err.message));
  });
</script>
</body>
</html>
```

- [ ] **Step 2: Manual smoke test**

Start the server:
```
.venv\Scripts\python.exe server.py
```

Open `http://localhost:5000` and verify:
1. All form fields visible and labeled; defaults pre-filled (`8,000 words`, `Adult sci-fi readers`, `Short Story`)
2. Upload/URL tabs switch correctly — only one panel visible at a time
3. Submitting with an empty required field shows the error message and re-enables Run
4. Run button disables and spinner appears on submit (stop the server to cancel the actual run)
5. Download button is hidden before a run completes

- [ ] **Step 3: Run full test suite**

```
.venv\Scripts\pytest.exe tests/ -v
```

Expected: 9 passed

- [ ] **Step 4: Commit**

```bash
git add static/index.html
git commit -m "Add prompt harness UI"
```

---

### Task 5: PR

- [ ] **Step 1: Push branch**

```bash
git push -u origin feature/prompt-harness
```

- [ ] **Step 2: Open PR**

Base branch: `feature/orchestrator`

```bash
gh pr create \
  --base feature/orchestrator \
  --title "Add browser-based prompt harness" \
  --body "Flask server + self-contained HTML UI for running the Writing Council and downloading the manuscript without editing Python files."
```
