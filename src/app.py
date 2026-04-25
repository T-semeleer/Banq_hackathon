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
from summarizer import summarize_month  # noqa: E402
from bunq_insights import (  # noqa: E402
    fetch_category_summary,
    fetch_category_transactions,
    fetch_event_feed,
    fetch_insight_preference,
    fetch_all_categories,
)
from category_store import get as _get_category  # noqa: E402

app = Flask(__name__, template_folder="templates")
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

# Single shared state for the current session (sufficient for hackathon demo)
_state: dict = {
    "split_result": None,
    "split_dict": None,
    "bunq_client": None,
    "account_id": None,
    "expense_transaction_id": None,  # original outgoing payment that was split
    "demo_expenses": None,           # populated by POST /api/demo/setup
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
    expense_txn_id = body.get("expense_transaction_id")

    if not ocr_text or not transcript:
        return jsonify({"error": "Both ocr_text and transcript are required"}), 400

    try:
        result = do_split(ocr_text, transcript)
        split_dict = result_to_dict(result)
        _state["split_result"] = result
        _state["split_dict"] = split_dict
        if expense_txn_id is not None:
            _state["expense_transaction_id"] = int(expense_txn_id)
            split_dict["expense_transaction_id"] = int(expense_txn_id)
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


# ── Recent outgoing transactions (expense picker) ──────────────────────────────

@app.route("/api/recent-expenses")
def recent_expenses():
    """Return the last 20 outgoing payments with spending category where known."""
    try:
        client, account_id = _get_bunq()
        raw = client.get(
            f"user/{client.user_id}/monetary-account/{account_id}/payment",
            params={"count": 100},
        )
        outgoing = []
        for item in raw:
            p = item.get("Payment", {})
            value = float(p.get("amount", {}).get("value", "0"))
            if value < 0:
                txn_id = p.get("id")
                outgoing.append({
                    "id": txn_id,
                    "amount": round(abs(value), 2),
                    "description": p.get("description", ""),
                    "date": (p.get("created") or "")[:10],
                    "counterparty": (p.get("counterparty_alias") or {}).get("display_name", ""),
                    "category": _get_category(txn_id) if txn_id else None,
                })
            if len(outgoing) >= 20:
                break
        return jsonify(outgoing)
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
        expense_id = _state.get("expense_transaction_id")
        if expense_id:
            description = f"Tikkie from {person} — SPLIT|TXN{expense_id}|{person}|{float(amount):.2f}"
        else:
            description = f"Tikkie from {person} — {float(amount):.2f}"
        resp = client.post(
            f"user/{client.user_id}/monetary-account/{account_id}/request-inquiry",
            {
                "amount_inquired": {"value": f"{float(amount):.2f}", "currency": "EUR"},
                "counterparty_alias": {
                    "type": "EMAIL",
                    "value": "sugardaddy@bunq.com",
                    "name": "Sugar Daddy",
                },
                "description": description,
                "allow_bunqme": False,
            },
        )
        request_id = resp[0]["Id"]["id"]
        time.sleep(1)  # let sandbox process the auto-accept
        return jsonify({
            "success": True,
            "request_id": request_id,
            "person": person,
            "amount": float(amount),
            "linked_expense_id": expense_id,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── Monthly summary ────────────────────────────────────────────────────────────

@app.route("/api/summary")
def summary():
    """
    Return a monthly expense summary with Tikkie reimbursements netted against
    their original expenses. Query param: month=YYYY-MM (defaults to current month).
    """
    from datetime import date as _date
    month_str = request.args.get("month", "")
    try:
        year_s, month_s = month_str.split("-")
        year, month = int(year_s), int(month_s)
        if not (1 <= month <= 12):
            raise ValueError
    except (ValueError, AttributeError):
        today = _date.today()
        year, month = today.year, today.month
    try:
        client, account_id = _get_bunq()
        result = summarize_month(client, account_id, year, month)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── Demo setup ────────────────────────────────────────────────────────────────

@app.route("/api/demo/setup", methods=["POST"])
def demo_setup():
    """
    Seed the sandbox account with six realistic demo expense transactions.

    - Funds the account with €500 via Sugar Daddy.
    - Creates one outgoing payment per demo expense.
    - Assigns spending categories locally so /api/insights returns real data.

    Call this once before starting a demo run. Takes ~5 seconds.
    """
    try:
        from demo_seeder import seed_demo
        client, account_id = _get_bunq()
        seeded = seed_demo(client, account_id)
        _state["demo_expenses"] = seeded
        return jsonify({
            "seeded": seeded,
            "count": len(seeded),
            "tip": (
                "Pick the first transaction from /api/recent-expenses as your expense to split. "
                "Then POST /api/split, POST /api/links, POST /api/demo/simulate-all, "
                "GET /api/reconcile, GET /api/insights."
            ),
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/demo/simulate-all", methods=["POST"])
def demo_simulate_all():
    """
    Simulate Tikkie repayments from every person in the current split.

    Creates one request-inquiry to Sugar Daddy per person (auto-accepted in sandbox),
    each with a description formatted like a real Tikkie repayment so the reconciler
    can match it and compute your net personal cost.

    Prerequisites: POST /api/split must have been called first.
    """
    if _state["split_result"] is None:
        return jsonify({"error": "No split result — call POST /api/split first"}), 400
    try:
        client, account_id = _get_bunq()
        expense_id = _state.get("expense_transaction_id")
        results = []

        for person in _state["split_result"].people:
            if person.name.lower() in ("you", "me", "i") or person.total_owed <= 0:
                continue
            amount_str = f"{person.total_owed:.2f}"
            if expense_id:
                description = (
                    f"Tikkie from {person.name} — "
                    f"SPLIT|TXN{expense_id}|{person.name}|{amount_str}"
                )
            else:
                description = f"Tikkie from {person.name} — {amount_str}"

            try:
                resp = client.post(
                    f"user/{client.user_id}/monetary-account/{account_id}/request-inquiry",
                    {
                        "amount_inquired": {"value": amount_str, "currency": "EUR"},
                        "counterparty_alias": {
                            "type": "EMAIL",
                            "value": "sugardaddy@bunq.com",
                            "name": "Sugar Daddy",
                        },
                        "description": description,
                        "allow_bunqme": False,
                    },
                )
                results.append({
                    "person": person.name,
                    "amount": float(amount_str),
                    "request_id": resp[0]["Id"]["id"],
                    "description": description,
                    "status": "simulated",
                })
                time.sleep(0.5)  # let sandbox auto-accept each request before the next
            except Exception as exc:
                results.append({
                    "person": person.name,
                    "amount": float(amount_str),
                    "status": "error",
                    "error": str(exc),
                })

        return jsonify({
            "simulated": results,
            "count": len(results),
            "next": "Call GET /api/reconcile to see who has paid and your net cost.",
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── Bunq native insights ───────────────────────────────────────────────────────

def _parse_month(month_str: str) -> tuple[int, int]:
    """Parse 'YYYY-MM' into (year, month), defaulting to current month."""
    from datetime import date as _date
    try:
        year_s, month_s = month_str.split("-")
        year, month = int(year_s), int(month_s)
        if not (1 <= month <= 12):
            raise ValueError
        return year, month
    except (ValueError, AttributeError):
        today = _date.today()
        return today.year, today.month


@app.route("/api/insights")
def bunq_insights():
    """
    Bunq-native category spend breakdown for a month.
    Query param: month=YYYY-MM (defaults to current month).
    """
    year, month = _parse_month(request.args.get("month", ""))
    try:
        client, account_id = _get_bunq()
        result = fetch_category_summary(client, year, month, account_id=account_id)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/insights/transactions")
def bunq_insight_transactions():
    """
    Transactions for a specific Bunq category.
    Query params: category=FOOD_AND_DRINK&month=YYYY-MM
    """
    category = request.args.get("category", "").strip().upper()
    if not category:
        return jsonify({"error": "category param is required (e.g. FOOD_AND_DRINK)"}), 400
    year, month = _parse_month(request.args.get("month", ""))
    try:
        client, account_id = _get_bunq()
        result = fetch_category_transactions(client, category, year, month, account_id=account_id)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/insights/categories")
def bunq_categories():
    """List all Bunq spending categories (system Tapix-assigned + user-defined)."""
    try:
        client, _ = _get_bunq()
        result = fetch_all_categories(client)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/events")
def event_feed():
    """
    Bunq activity event feed with Tapix category enrichment on each event.
    Query param: count=50 (max 200).
    """
    try:
        count = min(max(int(request.args.get("count", 50)), 1), 200)
        client, account_id = _get_bunq()
        result = fetch_event_feed(client, account_id=account_id, count=count)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/insights/preference")
def insight_preference():
    """User's configured monthly insight period start date."""
    try:
        client, _ = _get_bunq()
        result = fetch_insight_preference(client)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
