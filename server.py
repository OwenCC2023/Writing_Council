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


def _write_temp_image(data_uri: str, filename: str) -> str:
    raw = data_uri
    if "," in raw:
        raw = raw.split(",", 1)[1]
    image_bytes = base64.b64decode(raw)
    suffix = Path(filename or "upload.png").suffix or ".png"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(image_bytes)
    tmp.close()
    return tmp.name


@app.route("/run", methods=["POST"])
def run():
    data = request.get_json()
    image_paths = []
    try:
        image = ""
        image_files = data.get("image_files")
        if image_files:
            image_paths = [
                _write_temp_image(f["data"], f.get("filename", ""))
                for f in image_files
            ]
            image = image_paths
        elif data.get("image_file"):
            image_paths = [_write_temp_image(data["image_file"], data.get("image_filename", ""))]
            image = image_paths[0]
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
            title=data.get("title", ""),
        )
        return jsonify({
            "story": result["story"],
            "log": result["log"],
            "non_earth": result.get("non_earth", False),
            "planning_details": result.get("planning_details", ""),
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        for path in image_paths:
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
