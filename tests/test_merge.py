"""
Integration tests for the full OCR → voice → split → reconcile pipeline.

External APIs (Anthropic, bunq) are mocked so no network calls are made.
These tests verify the wiring between src/matcher.py, src/reconciler.py,
src/audio.py, and src/bunq.py.
"""
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Provide a dummy key so os.environ[] lookups in matcher/audio don't raise
os.environ.setdefault("ANTHROPIC_API_KEY", "test-dummy-key")

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "hackathon_toolkit-main"))

from matcher import SplitResult, match, result_to_dict  # noqa: E402
from reconciler import reconcile  # noqa: E402

# ── sample data ───────────────────────────────────────────────────────────────

SAMPLE_OCR = """
THE BISTRO
Table 4 - 3 guests
Grilled Chicken       14.50
Caesar Salad          11.00
Pasta Carbonara       13.50
Draft Beer             5.00
Sparkling Water        3.50
Subtotal              47.50
BTW (21%)              9.98
Total                 57.48
"""

SAMPLE_TRANSCRIPT = (
    "I had the grilled chicken and a sparkling water. "
    "Sarah had the caesar salad. Tom got the pasta and a beer."
)

_MOCK_SPLIT_RAW = {
    "people": [
        {
            "name": "You",
            "items": [{"name": "Grilled Chicken", "price": 14.50}, {"name": "Sparkling Water", "price": 3.50}],
            "subtotal": 18.0, "tax_share": 3.78, "tip_share": 0.0, "total_owed": 21.78,
        },
        {
            "name": "Sarah",
            "items": [{"name": "Caesar Salad", "price": 11.00}],
            "subtotal": 11.0, "tax_share": 2.31, "tip_share": 0.0, "total_owed": 13.31,
        },
        {
            "name": "Tom",
            "items": [{"name": "Pasta Carbonara", "price": 13.50}, {"name": "Draft Beer", "price": 5.00}],
            "subtotal": 18.5, "tax_share": 3.89, "tip_share": 0.0, "total_owed": 22.39,
        },
    ],
    "unassigned": [],
    "total": 57.48,
    "tax": 9.98,
    "tip": 0.0,
}


def _mock_claude(raw: dict) -> MagicMock:
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps(raw))]
    client = MagicMock()
    client.messages.create.return_value = msg
    return client


def _mock_bunq(*payments: dict) -> tuple[MagicMock, int]:
    client = MagicMock()
    client.user_id = 1
    client.get.return_value = [{"Payment": p} for p in payments]
    return client, 99


def _txn(id_: int, value: float, description: str) -> dict:
    return {
        "id": id_, "amount": {"value": str(value)},
        "description": description, "created": "2026-04-25T12:00:00",
        "counterparty_alias": {"display_name": "Sugar Daddy"},
    }


# ── matcher tests ─────────────────────────────────────────────────────────────

def test_matcher_returns_split_result():
    with patch("matcher.anthropic.Anthropic", return_value=_mock_claude(_MOCK_SPLIT_RAW)):
        result = match(SAMPLE_OCR, SAMPLE_TRANSCRIPT)

    assert isinstance(result, SplitResult)
    names = {p.name for p in result.people}
    assert names == {"You", "Sarah", "Tom"}
    assert abs(result.total - 57.48) < 0.01


def test_matcher_preserves_tax():
    with patch("matcher.anthropic.Anthropic", return_value=_mock_claude(_MOCK_SPLIT_RAW)):
        result = match(SAMPLE_OCR, SAMPLE_TRANSCRIPT)
    assert abs(result.tax - 9.98) < 0.01


def test_result_to_dict_shape():
    with patch("matcher.anthropic.Anthropic", return_value=_mock_claude(_MOCK_SPLIT_RAW)):
        result = match(SAMPLE_OCR, SAMPLE_TRANSCRIPT)
    d = result_to_dict(result)

    assert d["status"] == "review"
    assert "people" in d and "total" in d and "tax" in d
    for person in d["people"]:
        assert "bunqme_url" in person
        assert "payment_status" in person
        assert person["payment_status"] == "pending"


# ── reconciler + matcher integration ──────────────────────────────────────────

def test_pipeline_no_payments():
    """Full pipeline: split then reconcile with no incoming payments."""
    with patch("matcher.anthropic.Anthropic", return_value=_mock_claude(_MOCK_SPLIT_RAW)):
        split = match(SAMPLE_OCR, SAMPLE_TRANSCRIPT)

    client, account_id = _mock_bunq()
    status = reconcile(client, account_id, split)

    assert status["total_repaid"] == 0.0
    assert status["net_cost"] == pytest.approx(57.48, abs=0.01)
    assert status["remaining_owed"] == pytest.approx(13.31 + 22.39, abs=0.01)


def test_pipeline_sarah_paid():
    """Full pipeline: Sarah pays back — net cost drops by her share."""
    with patch("matcher.anthropic.Anthropic", return_value=_mock_claude(_MOCK_SPLIT_RAW)):
        split = match(SAMPLE_OCR, SAMPLE_TRANSCRIPT)

    sarah_amount = next(p.total_owed for p in split.people if p.name == "Sarah")
    client, account_id = _mock_bunq(_txn(1, sarah_amount, f"Tikkie repayment — Sarah"))
    status = reconcile(client, account_id, split)

    sarah = next(p for p in status["payments"] if p["name"] == "Sarah")
    tom   = next(p for p in status["payments"] if p["name"] == "Tom")

    assert sarah["paid"] is True
    assert tom["paid"] is False
    assert status["net_cost"] == pytest.approx(57.48 - sarah_amount, abs=0.01)


def test_pipeline_all_paid():
    """Full pipeline: all Tikkies received — net cost equals 'You' own share."""
    with patch("matcher.anthropic.Anthropic", return_value=_mock_claude(_MOCK_SPLIT_RAW)):
        split = match(SAMPLE_OCR, SAMPLE_TRANSCRIPT)

    sarah_amount = next(p.total_owed for p in split.people if p.name == "Sarah")
    tom_amount   = next(p.total_owed for p in split.people if p.name == "Tom")
    you_amount   = next(p.total_owed for p in split.people if p.name == "You")

    client, account_id = _mock_bunq(
        _txn(1, sarah_amount, "Tikkie repayment — Sarah"),
        _txn(2, tom_amount,   "Tikkie repayment — Tom"),
    )
    status = reconcile(client, account_id, split)

    assert all(p["paid"] for p in status["payments"])
    assert status["remaining_owed"] == 0.0
    assert status["net_cost"] == pytest.approx(you_amount, abs=0.01)


# ── audio module ──────────────────────────────────────────────────────────────

def test_audio_validate_returns_validation_result():
    """audio.validate() parses Claude Haiku response into ValidationResult."""
    from audio import ValidationResult, validate

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps({
        "quality": "GOOD",
        "feedback": "Clear item assignments.",
        "suggestions": None,
    }))]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("audio.anthropic.Anthropic", return_value=mock_client):
        result = validate(SAMPLE_TRANSCRIPT)

    assert isinstance(result, ValidationResult)
    assert result.quality == "GOOD"


def test_audio_validate_poor_quality():
    from audio import validate

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps({
        "quality": "POOR",
        "feedback": "No order info.",
        "suggestions": "Re-record describing who ordered what.",
    }))]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("audio.anthropic.Anthropic", return_value=mock_client):
        result = validate("...")

    assert result.quality == "POOR"
    assert result.suggestions is not None
