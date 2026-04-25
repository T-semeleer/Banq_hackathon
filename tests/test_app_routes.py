"""
Flask route tests for src/app.py.
All external APIs (bunq, Claude, OpenAI, AWS) are mocked.
"""
import io
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Env vars must be set before importing app
os.environ.setdefault("ANTHROPIC_API_KEY", "test-dummy-key")
os.environ.setdefault("OPENAI_API_KEY",    "test-dummy-key")
os.environ.setdefault("BUNQ_API_KEY",      "test-dummy-key")

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "hackathon_toolkit-main"))

import app as app_module  # noqa: E402 — imports src/app.py
from app import app  # noqa: E402

from matcher import PersonShare, ReceiptItem, SplitResult  # noqa: E402


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_state():
    """Reset module-level state before every test."""
    app_module._state.update({
        "split_result": None,
        "split_dict": None,
        "bunq_client": None,
        "account_id": None,
        "expense_transaction_id": None,
    })
    yield


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _make_split_result() -> SplitResult:
    return SplitResult(
        people=[
            PersonShare(name="You",   items=[ReceiptItem("Chicken", 14.50)],
                        subtotal=14.50, tax_share=3.05, tip_share=0.0, total_owed=17.55),
            PersonShare(name="Sarah", items=[ReceiptItem("Salad", 11.00)],
                        subtotal=11.00, tax_share=2.31, tip_share=0.0, total_owed=13.31),
        ],
        unassigned=[], total=30.86, tax=5.36, tip=0.0,
    )


def _set_split_state():
    """Pre-populate split state so routes that depend on it can run."""
    from matcher import result_to_dict
    result = _make_split_result()
    app_module._state["split_result"] = result
    app_module._state["split_dict"] = result_to_dict(result)


def _mock_bunq_client(account_id: int = 99) -> MagicMock:
    client = MagicMock()
    client.user_id = 1
    client.get_primary_account_id.return_value = account_id
    return client


# ── GET / ─────────────────────────────────────────────────────────────────────

def test_index_returns_200(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_index_returns_html(client):
    resp = client.get("/")
    assert b"SplitBill" in resp.data or b"<!DOCTYPE" in resp.data.lower()


# ── POST /api/transcribe ──────────────────────────────────────────────────────

def test_transcribe_missing_audio_returns_400(client):
    resp = client.post("/api/transcribe", data={})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_transcribe_no_openai_key_returns_501(client):
    with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
        audio_data = io.BytesIO(b"fake audio")
        resp = client.post(
            "/api/transcribe",
            data={"audio": (audio_data, "recording.webm", "audio/webm")},
            content_type="multipart/form-data",
        )
    assert resp.status_code == 501


def test_transcribe_empty_file_returns_400(client):
    empty = io.BytesIO(b"")
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        resp = client.post(
            "/api/transcribe",
            data={"audio": (empty, "recording.webm", "audio/webm")},
            content_type="multipart/form-data",
        )
    assert resp.status_code == 400
    data = resp.get_json()
    assert "empty" in data["error"].lower()


def test_transcribe_success(client):
    audio_data = io.BytesIO(b"fake audio content")
    mock_oai = MagicMock()
    mock_oai.audio.transcriptions.create.return_value = "I had the burger."

    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}), \
         patch("openai.OpenAI", return_value=mock_oai):
        resp = client.post(
            "/api/transcribe",
            data={"audio": (audio_data, "recording.webm", "audio/webm")},
            content_type="multipart/form-data",
        )

    assert resp.status_code == 200
    assert resp.get_json()["transcript"] == "I had the burger."


# ── POST /api/ocr ─────────────────────────────────────────────────────────────

def test_ocr_no_aws_key_returns_501(client):
    with patch.dict(os.environ, {"AWS_ACCESS_KEY_ID": ""}):
        resp = client.post("/api/ocr", data={})
    assert resp.status_code == 501


def test_ocr_missing_image_returns_400_if_aws_configured(client):
    with patch.dict(os.environ, {"AWS_ACCESS_KEY_ID": "fake-key"}):
        resp = client.post("/api/ocr", data={})
    assert resp.status_code in (400, 501)


# ── POST /api/split ───────────────────────────────────────────────────────────

def test_split_missing_ocr_text_returns_400(client):
    resp = client.post("/api/split", json={"transcript": "I had the burger."})
    assert resp.status_code == 400


def test_split_missing_transcript_returns_400(client):
    resp = client.post("/api/split", json={"ocr_text": "Burger 12.50"})
    assert resp.status_code == 400


def test_split_empty_ocr_text_returns_400(client):
    resp = client.post("/api/split", json={"ocr_text": "   ", "transcript": "I had X."})
    assert resp.status_code == 400


def test_split_success_returns_200(client):
    mock_split = {
        "people": [
            {"name": "You", "items": [{"name": "Burger", "price": 12.50}],
             "subtotal": 12.50, "tax_share": 0.0, "tip_share": 0.0, "total_owed": 12.50},
        ],
        "unassigned": [], "total": 12.50, "tax": 0.0, "tip": 0.0,
    }
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps(mock_split))]
    mock_claude = MagicMock()
    mock_claude.messages.create.return_value = msg

    with patch("app.do_split.__wrapped__", create=True), \
         patch("matcher.anthropic.Anthropic", return_value=mock_claude):
        resp = client.post("/api/split", json={
            "ocr_text": "Burger 12.50\nTotal 12.50",
            "transcript": "I had the burger.",
        })

    assert resp.status_code == 200
    data = resp.get_json()
    assert "people" in data
    assert "total" in data


def test_split_stores_result_in_state(client):
    mock_split = {
        "people": [
            {"name": "You", "items": [], "subtotal": 10.0,
             "tax_share": 0.0, "tip_share": 0.0, "total_owed": 10.0},
        ],
        "unassigned": [], "total": 10.0, "tax": 0.0, "tip": 0.0,
    }
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps(mock_split))]
    mock_claude = MagicMock()
    mock_claude.messages.create.return_value = msg

    with patch("matcher.anthropic.Anthropic", return_value=mock_claude):
        client.post("/api/split", json={
            "ocr_text": "Food 10.00",
            "transcript": "I had everything.",
        })

    assert app_module._state["split_result"] is not None
    assert app_module._state["split_dict"] is not None


# ── POST /api/links ───────────────────────────────────────────────────────────

def test_links_without_split_returns_400(client):
    resp = client.post("/api/links")
    assert resp.status_code == 400
    assert "split" in resp.get_json()["error"].lower()


def test_links_success_adds_urls(client):
    _set_split_state()
    mock_urls = {"Sarah": "https://bunq.me/sarah"}
    with patch("app.create_payment_links", return_value=mock_urls), \
         patch("app.inject_links", side_effect=lambda d, u: {**d, "_urls_injected": True}):
        resp = client.post("/api/links")
    assert resp.status_code == 200


def test_links_bunq_error_returns_500(client):
    _set_split_state()
    with patch("app.create_payment_links", side_effect=RuntimeError("bunq error")):
        resp = client.post("/api/links")
    assert resp.status_code == 500
    assert "error" in resp.get_json()


# ── GET /api/reconcile ────────────────────────────────────────────────────────

def test_reconcile_without_split_returns_400(client):
    resp = client.get("/api/reconcile")
    assert resp.status_code == 400


def test_reconcile_success_returns_footnote(client):
    _set_split_state()
    mock_status = {
        "original_total": 30.86,
        "payments": [{"name": "Sarah", "amount_owed": 13.31, "paid": False,
                      "paid_at": None, "transaction_id": None}],
        "total_repaid": 0.0, "net_cost": 30.86, "remaining_owed": 13.31,
    }
    mock_bunq_c = _mock_bunq_client()
    app_module._state["bunq_client"] = mock_bunq_c
    app_module._state["account_id"] = 99

    with patch("app.reconcile", return_value=mock_status):
        resp = client.get("/api/reconcile")

    assert resp.status_code == 200
    data = resp.get_json()
    assert "original_total" in data
    assert "payments" in data
    assert "net_cost" in data


def test_reconcile_bunq_error_returns_500(client):
    _set_split_state()
    mock_bunq_c = _mock_bunq_client()
    app_module._state["bunq_client"] = mock_bunq_c
    app_module._state["account_id"] = 99

    with patch("app.reconcile", side_effect=RuntimeError("connection error")):
        resp = client.get("/api/reconcile")

    assert resp.status_code == 500


# ── POST /api/simulate ────────────────────────────────────────────────────────

def test_simulate_missing_person_returns_400(client):
    resp = client.post("/api/simulate", json={"amount": 10.0})
    assert resp.status_code == 400


def test_simulate_missing_amount_returns_400(client):
    resp = client.post("/api/simulate", json={"person": "Sarah"})
    assert resp.status_code == 400


def test_simulate_empty_person_returns_400(client):
    resp = client.post("/api/simulate", json={"person": "  ", "amount": 10.0})
    assert resp.status_code == 400


def test_simulate_success_returns_request_id(client):
    mock_bunq_c = _mock_bunq_client()
    mock_bunq_c.user_id = 1
    mock_bunq_c.post.return_value = [{"Id": {"id": 999}}]
    app_module._state["bunq_client"] = mock_bunq_c
    app_module._state["account_id"] = 99

    with patch("app.time.sleep"):
        resp = client.post("/api/simulate", json={"person": "Sarah", "amount": 13.31})

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["request_id"] == 999
    assert data["person"] == "Sarah"
    assert data["amount"] == pytest.approx(13.31)


def test_simulate_posts_correct_description(client):
    mock_bunq_c = _mock_bunq_client()
    mock_bunq_c.post.return_value = [{"Id": {"id": 1}}]
    app_module._state["bunq_client"] = mock_bunq_c
    app_module._state["account_id"] = 99

    with patch("app.time.sleep"):
        client.post("/api/simulate", json={"person": "Tom", "amount": 22.39})

    call_body = mock_bunq_c.post.call_args[0][1]
    assert "Tom" in call_body["description"]
    assert call_body["counterparty_alias"]["value"] == "sugardaddy@bunq.com"


def test_simulate_formats_amount_to_2dp(client):
    mock_bunq_c = _mock_bunq_client()
    mock_bunq_c.post.return_value = [{"Id": {"id": 1}}]
    app_module._state["bunq_client"] = mock_bunq_c
    app_module._state["account_id"] = 99

    with patch("app.time.sleep"):
        client.post("/api/simulate", json={"person": "Alice", "amount": 13.3})

    call_body = mock_bunq_c.post.call_args[0][1]
    assert call_body["amount_inquired"]["value"] == "13.30"


def test_simulate_bunq_error_returns_500(client):
    mock_bunq_c = _mock_bunq_client()
    mock_bunq_c.post.side_effect = RuntimeError("bunq API error")
    app_module._state["bunq_client"] = mock_bunq_c
    app_module._state["account_id"] = 99

    with patch("app.time.sleep"):
        resp = client.post("/api/simulate", json={"person": "Sarah", "amount": 10.0})

    assert resp.status_code == 500


# ── Full cycle: split → reconcile ─────────────────────────────────────────────

def test_full_cycle_split_then_reconcile(client):
    """POST /api/split stores state; GET /api/reconcile uses it."""
    mock_split_raw = {
        "people": [
            {"name": "You",   "items": [], "subtotal": 20.0, "tax_share": 0.0,
             "tip_share": 0.0, "total_owed": 20.0},
            {"name": "Sarah", "items": [], "subtotal": 10.0, "tax_share": 0.0,
             "tip_share": 0.0, "total_owed": 10.0},
        ],
        "unassigned": [], "total": 30.0, "tax": 0.0, "tip": 0.0,
    }
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps(mock_split_raw))]
    mock_claude = MagicMock()
    mock_claude.messages.create.return_value = msg

    with patch("matcher.anthropic.Anthropic", return_value=mock_claude):
        split_resp = client.post("/api/split", json={
            "ocr_text": "Food 30.00\nTotal 30.00",
            "transcript": "I had half, Sarah had half.",
        })

    assert split_resp.status_code == 200
    assert app_module._state["split_result"] is not None

    mock_bunq_c = _mock_bunq_client()
    mock_bunq_c.get.return_value = []
    app_module._state["bunq_client"] = mock_bunq_c
    app_module._state["account_id"] = 99

    from reconciler import reconcile as real_reconcile
    with patch("app.reconcile", wraps=real_reconcile):
        rec_resp = client.get("/api/reconcile")

    assert rec_resp.status_code == 200
    data = rec_resp.get_json()
    assert data["original_total"] == pytest.approx(30.0)
    assert data["total_repaid"] == 0.0


# ── GET /api/recent-expenses ──────────────────────────────────────────────────

def test_recent_expenses_returns_200(client):
    mock_bunq_c = _mock_bunq_client()
    mock_bunq_c.get.return_value = []
    app_module._state["bunq_client"] = mock_bunq_c
    app_module._state["account_id"] = 99

    resp = client.get("/api/recent-expenses")
    assert resp.status_code == 200
    assert isinstance(resp.get_json(), list)


def test_recent_expenses_filters_outgoing_only(client):
    mock_bunq_c = _mock_bunq_client()
    mock_bunq_c.get.return_value = [
        {"Payment": {"id": 1, "amount": {"value": "-50.00"}, "description": "Restaurant",
                     "created": "2026-04-15 12:00:00", "counterparty_alias": {"display_name": "Bistro"}}},
        {"Payment": {"id": 2, "amount": {"value": "13.31"}, "description": "Tikkie Sarah",
                     "created": "2026-04-15 12:00:00", "counterparty_alias": {"display_name": "Sarah"}}},
        {"Payment": {"id": 3, "amount": {"value": "-25.00"}, "description": "Supermarket",
                     "created": "2026-04-14 10:00:00", "counterparty_alias": {"display_name": "AH"}}},
    ]
    app_module._state["bunq_client"] = mock_bunq_c
    app_module._state["account_id"] = 99

    resp = client.get("/api/recent-expenses")
    data = resp.get_json()

    assert len(data) == 2
    ids = [e["id"] for e in data]
    assert 1 in ids
    assert 3 in ids
    assert 2 not in ids   # incoming payment must be excluded


def test_recent_expenses_amount_is_positive(client):
    """Returned amounts are absolute values (positive), not negative."""
    mock_bunq_c = _mock_bunq_client()
    mock_bunq_c.get.return_value = [
        {"Payment": {"id": 1, "amount": {"value": "-57.48"}, "description": "Dinner",
                     "created": "2026-04-15 12:00:00", "counterparty_alias": {"display_name": "Restaurant"}}},
    ]
    app_module._state["bunq_client"] = mock_bunq_c
    app_module._state["account_id"] = 99

    resp = client.get("/api/recent-expenses")
    data = resp.get_json()
    assert data[0]["amount"] == pytest.approx(57.48)


def test_recent_expenses_max_twenty_results(client):
    """At most 20 outgoing payments are returned."""
    mock_bunq_c = _mock_bunq_client()
    mock_bunq_c.get.return_value = [
        {"Payment": {"id": i, "amount": {"value": "-10.00"}, "description": f"Expense {i}",
                     "created": "2026-04-15 12:00:00", "counterparty_alias": {"display_name": "Vendor"}}}
        for i in range(1, 30)
    ]
    app_module._state["bunq_client"] = mock_bunq_c
    app_module._state["account_id"] = 99

    resp = client.get("/api/recent-expenses")
    assert len(resp.get_json()) == 20


def test_recent_expenses_response_has_required_fields(client):
    mock_bunq_c = _mock_bunq_client()
    mock_bunq_c.get.return_value = [
        {"Payment": {"id": 1, "amount": {"value": "-30.00"}, "description": "Lunch",
                     "created": "2026-04-15 12:00:00", "counterparty_alias": {"display_name": "Café"}}},
    ]
    app_module._state["bunq_client"] = mock_bunq_c
    app_module._state["account_id"] = 99

    resp = client.get("/api/recent-expenses")
    entry = resp.get_json()[0]
    assert {"id", "amount", "description", "date", "counterparty"}.issubset(entry.keys())


def test_recent_expenses_bunq_error_returns_500(client):
    mock_bunq_c = _mock_bunq_client()
    mock_bunq_c.get.side_effect = RuntimeError("bunq down")
    app_module._state["bunq_client"] = mock_bunq_c
    app_module._state["account_id"] = 99

    resp = client.get("/api/recent-expenses")
    assert resp.status_code == 500
    assert "error" in resp.get_json()


# ── GET /api/summary ──────────────────────────────────────────────────────────

def _make_summary_result(period: str = "2026-04") -> dict:
    return {
        "period": period,
        "expenses": [],
        "income": [],
        "unmatched_tikkies": [],
        "totals": {
            "gross_expenses": 0.0,
            "tikkie_reimbursements_received": 0.0,
            "net_personal_expenses": 0.0,
            "other_income": 0.0,
        },
    }


def test_summary_returns_200(client):
    mock_bunq_c = _mock_bunq_client()
    app_module._state["bunq_client"] = mock_bunq_c
    app_module._state["account_id"] = 99

    with patch("app.summarize_month", return_value=_make_summary_result("2026-04")):
        resp = client.get("/api/summary?month=2026-04")

    assert resp.status_code == 200


def test_summary_returns_correct_period(client):
    mock_bunq_c = _mock_bunq_client()
    app_module._state["bunq_client"] = mock_bunq_c
    app_module._state["account_id"] = 99

    with patch("app.summarize_month", return_value=_make_summary_result("2026-03")):
        resp = client.get("/api/summary?month=2026-03")

    assert resp.get_json()["period"] == "2026-03"


def test_summary_response_has_required_keys(client):
    mock_bunq_c = _mock_bunq_client()
    app_module._state["bunq_client"] = mock_bunq_c
    app_module._state["account_id"] = 99

    with patch("app.summarize_month", return_value=_make_summary_result()):
        resp = client.get("/api/summary?month=2026-04")

    data = resp.get_json()
    required = {"period", "expenses", "income", "unmatched_tikkies", "totals"}
    assert required.issubset(data.keys())
    assert {"gross_expenses", "tikkie_reimbursements_received",
            "net_personal_expenses", "other_income"}.issubset(data["totals"].keys())


def test_summary_with_invalid_month_defaults_to_current(client):
    """Invalid month string → falls back to current month without raising."""
    mock_bunq_c = _mock_bunq_client()
    app_module._state["bunq_client"] = mock_bunq_c
    app_module._state["account_id"] = 99

    with patch("app.summarize_month", return_value=_make_summary_result()) as mock_sum:
        resp = client.get("/api/summary?month=not-a-date")

    assert resp.status_code == 200
    mock_sum.assert_called_once()


def test_summary_without_month_param_uses_current(client):
    mock_bunq_c = _mock_bunq_client()
    app_module._state["bunq_client"] = mock_bunq_c
    app_module._state["account_id"] = 99

    with patch("app.summarize_month", return_value=_make_summary_result()) as mock_sum:
        resp = client.get("/api/summary")

    assert resp.status_code == 200
    mock_sum.assert_called_once()


def test_summary_bunq_error_returns_500(client):
    mock_bunq_c = _mock_bunq_client()
    mock_bunq_c.get.side_effect = RuntimeError("bunq error")
    app_module._state["bunq_client"] = mock_bunq_c
    app_module._state["account_id"] = 99

    with patch("app.summarize_month", side_effect=RuntimeError("bunq error")):
        resp = client.get("/api/summary?month=2026-04")

    assert resp.status_code == 500
    assert "error" in resp.get_json()


def test_summary_month_boundary_13_is_invalid(client):
    """Month=13 is invalid and must fall back to current month."""
    mock_bunq_c = _mock_bunq_client()
    app_module._state["bunq_client"] = mock_bunq_c
    app_module._state["account_id"] = 99

    with patch("app.summarize_month", return_value=_make_summary_result()) as mock_sum:
        resp = client.get("/api/summary?month=2026-13")

    assert resp.status_code == 200
    mock_sum.assert_called_once()


# ── POST /api/simulate expense_transaction_id state ──────────────────────────

def test_simulate_with_expense_id_in_state_uses_split_format(client):
    """When expense_transaction_id is set in state, description uses SPLIT|TXN format."""
    mock_bunq_c = _mock_bunq_client()
    mock_bunq_c.post.return_value = [{"Id": {"id": 1}}]
    app_module._state["bunq_client"] = mock_bunq_c
    app_module._state["account_id"] = 99
    app_module._state["expense_transaction_id"] = 200

    with patch("app.time.sleep"):
        client.post("/api/simulate", json={"person": "Sarah", "amount": 13.31})

    call_body = mock_bunq_c.post.call_args[0][1]
    assert call_body["description"] == "Tikkie from Sarah — SPLIT|TXN200|Sarah|13.31"


def test_simulate_without_expense_id_uses_plain_format(client):
    """No expense_transaction_id → description is plain 'Tikkie from {name} — amount'."""
    mock_bunq_c = _mock_bunq_client()
    mock_bunq_c.post.return_value = [{"Id": {"id": 1}}]
    app_module._state["bunq_client"] = mock_bunq_c
    app_module._state["account_id"] = 99
    # expense_transaction_id is None (reset by fixture)

    with patch("app.time.sleep"):
        client.post("/api/simulate", json={"person": "Tom", "amount": 22.39})

    call_body = mock_bunq_c.post.call_args[0][1]
    assert call_body["description"] == "Tikkie from Tom — 22.39"


def test_simulate_linked_expense_id_returned_in_response(client):
    mock_bunq_c = _mock_bunq_client()
    mock_bunq_c.post.return_value = [{"Id": {"id": 1}}]
    app_module._state["bunq_client"] = mock_bunq_c
    app_module._state["account_id"] = 99
    app_module._state["expense_transaction_id"] = 99

    with patch("app.time.sleep"):
        resp = client.post("/api/simulate", json={"person": "Alice", "amount": 10.0})

    assert resp.get_json()["linked_expense_id"] == 99


def test_simulate_no_expense_id_linked_expense_id_is_none(client):
    mock_bunq_c = _mock_bunq_client()
    mock_bunq_c.post.return_value = [{"Id": {"id": 1}}]
    app_module._state["bunq_client"] = mock_bunq_c
    app_module._state["account_id"] = 99

    with patch("app.time.sleep"):
        resp = client.post("/api/simulate", json={"person": "Bob", "amount": 5.0})

    assert resp.get_json()["linked_expense_id"] is None


# ── POST /api/split expense_transaction_id wiring ────────────────────────────

def test_split_with_expense_transaction_id_stores_in_state(client):
    mock_split = {
        "people": [{"name": "You", "items": [], "subtotal": 10.0,
                    "tax_share": 0.0, "tip_share": 0.0, "total_owed": 10.0}],
        "unassigned": [], "total": 10.0, "tax": 0.0, "tip": 0.0,
    }
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps(mock_split))]
    mock_claude = MagicMock()
    mock_claude.messages.create.return_value = msg

    with patch("matcher.anthropic.Anthropic", return_value=mock_claude):
        client.post("/api/split", json={
            "ocr_text": "Food 10.00",
            "transcript": "I had everything.",
            "expense_transaction_id": 555,
        })

    assert app_module._state["expense_transaction_id"] == 555


def test_split_with_expense_transaction_id_included_in_response(client):
    mock_split = {
        "people": [{"name": "You", "items": [], "subtotal": 10.0,
                    "tax_share": 0.0, "tip_share": 0.0, "total_owed": 10.0}],
        "unassigned": [], "total": 10.0, "tax": 0.0, "tip": 0.0,
    }
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps(mock_split))]
    mock_claude = MagicMock()
    mock_claude.messages.create.return_value = msg

    with patch("matcher.anthropic.Anthropic", return_value=mock_claude):
        resp = client.post("/api/split", json={
            "ocr_text": "Food 10.00",
            "transcript": "I had everything.",
            "expense_transaction_id": 777,
        })

    assert resp.get_json().get("expense_transaction_id") == 777
