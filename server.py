import base64
import io
import os
import tempfile
from pathlib import Path

from flask import Flask, jsonify, request, send_file

from document_writer import save_as_manuscript
from orchestrator import WritingCouncil
from story_intake import load_story_text

app = Flask(__name__, static_folder="static")


@app.route("/")
def index():
    return app.send_static_file("index.html")


def _write_temp_upload(data_uri: str, filename: str) -> str:
    """Decode a base64 data URI to a temp file and return its path."""
    raw = data_uri
    if "," in raw:
        raw = raw.split(",", 1)[1]
    file_bytes = base64.b64decode(raw)
    suffix = Path(filename or "upload.png").suffix or ".png"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(file_bytes)
    tmp.close()
    return tmp.name


@app.route("/run", methods=["POST"])
def run():
    data = request.get_json()
    temp_paths = []
    try:
        image = ""
        image_files = data.get("image_files")
        if image_files:
            image_paths = [
                _write_temp_upload(f["data"], f.get("filename", ""))
                for f in image_files
            ]
            temp_paths.extend(image_paths)
            image = image_paths
        elif data.get("image_file"):
            image_path = _write_temp_upload(data["image_file"], data.get("image_filename", ""))
            temp_paths.append(image_path)
            image = image_path
        elif data.get("image_url"):
            image = data["image_url"]

        source_story = data.get("story_text", "") or ""
        source_filename = ""
        story_file = data.get("story_file")
        if story_file:
            source_filename = story_file.get("filename", "")
            story_path = _write_temp_upload(story_file["data"], source_filename)
            temp_paths.append(story_path)
            source_story = load_story_text(story_path)

        has_source = bool(source_story)
        council = WritingCouncil()
        result = council.run(
            idea=data.get("idea", ""),
            target_length=data.get("target_length", "" if has_source else "8,000 words"),
            target_audience=data.get("target_audience",
                                     "" if has_source else "Adult sci-fi readers"),
            world_rules=data.get("world_rules", ""),
            framework=data.get("framework", ""),
            style=data.get("style", ""),
            image=image,
            title=data.get("title", ""),
            constraint=data.get("constraint", ""),
            source_story=source_story,
            source_filename=source_filename,
            rewrite_mode=data.get("rewrite_mode", ""),
            rewrite_notes=data.get("rewrite_notes", ""),
        )
        return jsonify({
            "story": result["story"],
            "log": result["log"],
            "non_earth": result.get("non_earth", False),
            "planning_details": result.get("planning_details", ""),
            "constraint_check": result.get("constraint_check"),
            "intake_brief": result.get("intake_brief", ""),
            "rewrite_mode": result.get("rewrite_mode", ""),
            "title": result.get("title", ""),
            "target_length": result.get("target_length", ""),
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        for path in temp_paths:
            if os.path.exists(path):
                os.unlink(path)


@app.route("/save", methods=["POST"])
def save():
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"error": "Invalid JSON body"}), 400
        buf = io.BytesIO()
        save_as_manuscript(
            story=data["story"],
            title=data["title"],
            author=data["author"],
            output=buf,
            details=data.get("details"),
        )
        filename = f"{data['title']}.docx"
        return send_file(
            buf,
            as_attachment=True,
            download_name=filename,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    app.run(debug=False, threaded=True)
