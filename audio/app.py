import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from openai import OpenAI

load_dotenv(Path(__file__).parent / ".env")

api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    raise SystemExit(
        "\n\nMissing OPENAI_API_KEY.\n"
        "Create audio/.env with:\n\n"
        "  OPENAI_API_KEY=sk-...\n"
    )

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25 MB Whisper limit

client = OpenAI(api_key=api_key)

ALLOWED_MIME_TYPES = {
    "audio/webm",
    "audio/ogg",
    "audio/mp4",
    "audio/mpeg",
    "audio/wav",
    "audio/x-wav",
}


@app.route("/audio-test")
def audio_test():
    return render_template("audio_test.html")


@app.route("/api/transcribe", methods=["POST"])
def transcribe():
    audio_file = request.files.get("audio")
    if not audio_file:
        return jsonify({"error": "No audio file provided"}), 400

    mime = audio_file.content_type or ""
    # Strip codec suffix e.g. "audio/webm;codecs=opus" → "audio/webm"
    clean_mime = mime.split(";")[0].strip()
    ext = "webm" if "webm" in clean_mime else "ogg" if "ogg" in clean_mime else "mp4" if "mp4" in clean_mime else "wav"

    with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
        audio_file.save(tmp.name)
        tmp_path = tmp.name

    if os.path.getsize(tmp_path) == 0:
        os.unlink(tmp_path)
        return jsonify({"error": "Recording is empty — try again"}), 400

    try:
        with open(tmp_path, "rb") as f:
            # Pass explicit filename so Whisper knows the format
            result = client.audio.transcriptions.create(
                model="whisper-1",
                file=(f"recording.{ext}", f, clean_mime),
                response_format="text",
            )
        return jsonify({"transcript": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        os.unlink(tmp_path)


if __name__ == "__main__":
    app.run(debug=True, port=5050)
