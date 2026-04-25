"""
Unified split-bill app: OCR + Voice + Split + bunq Payments + Reconciliation.

Required env vars:
  ANTHROPIC_API_KEY    — bill splitting (Claude)
  OPENAI_API_KEY       — voice transcription (Whisper)
  BUNQ_API_KEY         — bunq sandbox key (created automatically if absent)
  AWS_ACCESS_KEY_ID    — OCR via Textract (optional; /api/ocr disabled if missing)
  AWS_SECRET_ACCESS_KEY
  S3_BUCKET

Run from project root:
    python src/app.py    →  http://localhost:5000
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_ROOT = Path(__file__).resolve().parent.parent
_TOOLKIT_DIR = _ROOT / "hackathon_toolkit-main"
for _p in (str(_ROOT / "src"), str(_TOOLKIT_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from flask import Flask, jsonify, render_template, request  # noqa: E402

from bunq_client import BunqClient  # noqa: E402
from matcher import match as do_split, result_to_dict  # noqa: E402
from reconciler import reconcile  # noqa: E402
from bunq import create_payment_links, inject_links  # noqa: E402

app = Flask(__name__, template_folder="templates")
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

# Single shared state for the current session (sufficient for hackathon demo)
_state: dict = {
    "split_result": None,
    "split_dict": None,
    "bunq_client": None,
    "account_id": None,
}


def _get_bunq() -> tuple[BunqClient, int]:
    """Return (client, account_id), authenticating once per process."""
    if _state["bunq_client"] is None:
        api_key = os.getenv("BUNQ_API_KEY", "").strip()
        if not api_key:
            api_key = BunqClient.create_sandbox_user()
        client = BunqClient(api_key=api_key, sandbox=True)
        client.authenticate()
        _state["bunq_client"] = client
        _state["account_id"] = client.get_primary_account_id()
    return _state["bunq_client"], _state["account_id"]


# ── UI ─────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ── Voice transcription ────────────────────────────────────────────────────────

@app.route("/api/transcribe", methods=["POST"])
def transcribe():
    audio_file = request.files.get("audio")
    if not audio_file:
        return jsonify({"error": "No audio file provided"}), 400

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return jsonify({"error": "OPENAI_API_KEY not configured"}), 501

    from openai import OpenAI
    oai = OpenAI(api_key=api_key)

    mime = (audio_file.content_type or "").split(";")[0].strip()
    ext = (
        "webm" if "webm" in mime else
        "ogg"  if "ogg"  in mime else
        "mp4"  if "mp4"  in mime else
        "wav"
    )

    with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
        audio_file.save(tmp.name)
        tmp_path = tmp.name

    if os.path.getsize(tmp_path) == 0:
        os.unlink(tmp_path)
        return jsonify({"error": "Recording is empty — try again"}), 400

    try:
        with open(tmp_path, "rb") as f:
            result = oai.audio.transcriptions.create(
                model="whisper-1",
                file=(f"recording.{ext}", f, mime or "audio/webm"),
                response_format="text",
            )
        return jsonify({"transcript": result})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        os.unlink(tmp_path)


# ── OCR ────────────────────────────────────────────────────────────────────────

@app.route("/api/ocr", methods=["POST"])
def ocr():
    if not os.getenv("AWS_ACCESS_KEY_ID"):
        return jsonify({"error": "AWS credentials not configured — paste receipt text manually"}), 501

    image_file = request.files.get("image")
    if not image_file:
        return jsonify({"error": "No image file provided"}), 400

    suffix = Path(image_file.filename or "receipt.jpg").suffix or ".jpg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        image_file.save(tmp.name)
        tmp_path = tmp.name

    try:
        from ocr import process_receipt
        result = process_receipt(tmp_path)
        lines = []
        if result.vendor:
            lines.append(result.vendor)
        for item in result.items:
            lines.append(f"{item.name:<40} {item.price:.2f}")
        if result.tax is not None:
            lines.append(f"{'Tax':<40} {result.tax:.2f}")
        if result.total is not None:
            lines.append(f"{'Total':<40} {result.total:.2f}")
        return jsonify({
            "ocr_text": "\n".join(lines),
            "vendor": result.vendor,
            "items": [{"name": i.name, "price": i.price} for i in result.items],
            "total": result.total,
            "tax": result.tax,
            "image_url": result.image_url,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        os.unlink(tmp_path)


# ── Bill splitting ─────────────────────────────────────────────────────────────

@app.route("/api/split", methods=["POST"])
def split():
    body = request.get_json(force=True) or {}
    ocr_text = (body.get("ocr_text") or "").strip()
    transcript = (body.get("transcript") or "").strip()

    if not ocr_text or not transcript:
        return jsonify({"error": "Both ocr_text and transcript are required"}), 400

    try:
        result = do_split(ocr_text, transcript)
        split_dict = result_to_dict(result)
        _state["split_result"] = result
        _state["split_dict"] = split_dict
        # Persist for simulate_tikkie_payment.py CLI tool
        with open(_ROOT / "last_split.json", "w") as f:
            json.dump(split_dict, f, indent=2)
        return jsonify(split_dict)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── Payment links ──────────────────────────────────────────────────────────────

@app.route("/api/links", methods=["POST"])
def links():
    if _state["split_result"] is None:
        return jsonify({"error": "No split result — run /api/split first"}), 400
    try:
        urls = create_payment_links(_state["split_result"])
        updated = inject_links(_state["split_dict"], urls)
        _state["split_dict"] = updated
        return jsonify(updated)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── Reconciliation ─────────────────────────────────────────────────────────────

@app.route("/api/reconcile", methods=["GET"])
def reconcile_status():
    if _state["split_result"] is None:
        return jsonify({"error": "No split result — run /api/split first"}), 400
    try:
        client, account_id = _get_bunq()
        status = reconcile(client, account_id, _state["split_result"])
        return jsonify(status)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── Tikkie simulation ──────────────────────────────────────────────────────────

@app.route("/api/simulate", methods=["POST"])
def simulate():
    body = request.get_json(force=True) or {}
    person = (body.get("person") or "").strip()
    amount = body.get("amount")

    if not person or amount is None:
        return jsonify({"error": "person and amount are required"}), 400

    try:
        client, account_id = _get_bunq()
        resp = client.post(
            f"user/{client.user_id}/monetary-account/{account_id}/request-inquiry",
            {
                "amount_inquired": {"value": f"{float(amount):.2f}", "currency": "EUR"},
                "counterparty_alias": {
                    "type": "EMAIL",
                    "value": "sugardaddy@bunq.com",
                    "name": "Sugar Daddy",
                },
                "description": f"Tikkie repayment — {person}",
                "allow_bunqme": False,
            },
        )
        request_id = resp[0]["Id"]["id"]
        time.sleep(1)  # let sandbox process the auto-accept
        return jsonify({"success": True, "request_id": request_id, "person": person, "amount": float(amount)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
