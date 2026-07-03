# Prompt Harness — Design Spec
**Date:** 2026-07-02
**Branch:** feature/prompt-harness

## Summary

A local browser-based UI that lets the user fill in Writing Council prompt details, run the council, read the story output, and download the finished manuscript as a `.docx` — without editing Python files.

---

## Architecture

Two new files added to the project root. One existing file modified: `document_writer.py` gains a `BytesIO` output path.

### `server.py`

Flask application with three routes:

| Route | Method | Purpose |
|---|---|---|
| `/` | GET | Serves `static/index.html` |
| `/run` | POST | Accepts JSON payload, runs `WritingCouncil.run()`, returns `{story, log}` |
| `/save` | POST | Accepts `{story, title, author}`, generates `.docx` in-memory, returns as file download |

**`/run` request shape:**
```json
{
  "idea": "...",
  "target_length": "8,000 words",
  "target_audience": "Adult sci-fi readers",
  "world_rules": "",
  "framework": "Short Story",
  "style": "",
  "image_url": "",
  "image_file": "<base64-encoded bytes or omitted>",
  "image_filename": "world.png"
}
```

`title` and `author` are not included — `WritingCouncil.run()` does not use them. The client sends them directly to `/save` from the form values it already holds.

**`/run` response shape:**
```json
{
  "story": "...",
  "log": [{"step": "...", "output": "..."}]
}
```

Image handling in `/run`:
- If `image_file` is present (base64): decode, write to a temp file using the extension from `image_filename` (e.g. `.png`) so `_IMAGE_MEDIA_TYPES` can determine the MIME type, pass path to `WritingCouncil.run(image=...)`, delete temp file in a `finally` block.
- If `image_url` is present: pass URL string directly to `WritingCouncil.run(image=...)`.
- Both take the same `image` parameter on `WritingCouncil.run()` — no changes to the orchestrator needed.

**`/save` request shape:**
```json
{"story": "...", "title": "My Story", "author": "Jane Smith"}
```

Response: `Content-Disposition: attachment; filename="My Story.docx"` with `.docx` bytes. Uses `io.BytesIO` — nothing written to disk on the server.

Flask runs on `localhost:5000` by default. Start with `python server.py`. Must use `app.run(threaded=True)` so the long-running `/run` request does not block Flask from serving any other request (static assets, health checks).

### `document_writer.py` — change

`save_as_manuscript` gains an optional `output` parameter:

```python
def save_as_manuscript(story, title, author, output_path=None, output=None) -> "str | io.BytesIO":
```

- If `output_path` is given: existing behaviour — saves to file, returns the path string.
- If `output` is a `BytesIO`: writes into the buffer, returns the buffer (caller seeks to 0 before reading).
- Exactly one of the two must be provided; raises `ValueError` otherwise.

`/save` passes a fresh `BytesIO` and reads the result directly — no temp files, no disk writes.

### `static/index.html`

Single self-contained file: HTML + embedded `<style>` + embedded `<script>`. No build step, no external JS dependencies, no bundler.

---

## UI Layout

```
┌─────────────────────────────────────────────┐
│  Writing Council                            │
├─────────────────────────────────────────────┤
│  Title *          [                       ] │
│  Author *         [                       ] │
│  Idea *           [                       ] │
│                   [                       ] │
│  Target Length *  [8,000 words            ] │
│  Target Audience* [Adult sci-fi readers   ] │
│  World Rules      [                       ] │
│                   [                       ] │
│  Framework        [Short Story            ] │
│  Style            [                       ] │
│  Image   [ Upload ] [ URL ]                 │
│           [Choose file...] or [https://...] │
│                                             │
│  [ Run Council ]                            │
├─────────────────────────────────────────────┤
│  ⟳ Council is working...    (spinner)       │
│  (hidden until Run clicked)                 │
├─────────────────────────────────────────────┤
│  Output                                     │
│  ┌───────────────────────────────────────┐  │
│  │ story text appears here...            │  │
│  └───────────────────────────────────────┘  │
│  ⚠ Output is not saved — download before   │
│    closing this tab.                        │
│  [ Download .docx ]                         │
│  (hidden until story ready)                 │
└─────────────────────────────────────────────┘
```

### Fields

| Field | Type | Required | Default |
|---|---|---|---|
| Title | `<input type="text">` | yes | — |
| Author | `<input type="text">` | yes | — |
| Idea | `<textarea>` | yes | — |
| Target Length | `<input type="text">` | yes | `8,000 words` |
| Target Audience | `<input type="text">` | yes | `Adult sci-fi readers` |
| World Rules | `<textarea>` | no | — |
| Framework | `<input type="text">` | no | `Short Story` |
| Style | `<input type="text">` | no | — |
| Image | tab switcher: Upload \| URL | no | — |

**Image tab behaviour:** active tab wins. If the user enters a URL then switches to Upload and selects a file, `image_file` is sent and `image_url` is ignored (and vice-versa). Only the active tab's input is included in the payload.

### Interaction flow

1. User fills form, clicks **Run Council**.
2. JS validates required fields client-side (non-empty check). Shows inline error if missing.
3. If image file selected: read as base64 via `FileReader`, include in JSON payload as `image_file` and `image_filename` (original filename, used to preserve extension for MIME detection).
4. `POST /run` sent. Button disabled, spinner shown.
5. Response arrives (may take several minutes). Spinner hidden.
6. Story text populated in output `<textarea>`. **Download .docx** button appears. Warning banner shown: "Output is not saved — download before closing this tab."
7. User clicks **Download .docx** → `POST /save` with `{story, title, author}` → browser receives file download.

### Error handling

- Client-side: required field validation before submit.
- Server-side: if `WritingCouncil.run()` throws, `/run` returns `{"error": "..."}` with HTTP 500. JS displays the error message below the spinner in red.
- Temp image file always deleted in a `finally` block.

---

## Dependencies

- `flask` — add to `requirements.txt` (create the file if it doesn't exist; install into `.venv` with `pip install flask`)
- `python-docx` — already used by `document_writer.py`; already in `.venv`
- No new frontend dependencies

---

## Out of scope

- Authentication
- Persisting past runs
- Streaming output
- Running multiple simultaneous jobs
