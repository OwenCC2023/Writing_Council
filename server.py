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
