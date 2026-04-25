"""Unit tests for src/reconciler.py — all bunq API calls are mocked."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "hackathon_toolkit-main"))

from matcher import PersonShare, ReceiptItem, SplitResult  # noqa: E402
from reconciler import _find_match, reconcile  # noqa: E402


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def split():
    return SplitResult(
        people=[
            PersonShare(name="You",   items=[], subtotal=18.0, tax_share=3.78, tip_share=0.0, total_owed=21.78),
            PersonShare(name="Sarah", items=[], subtotal=11.0, tax_share=2.31, tip_share=0.0, total_owed=13.31),
            PersonShare(name="Tom",   items=[], subtotal=18.5, tax_share=3.89, tip_share=0.0, total_owed=22.39),
        ],
        unassigned=[],
        total=57.48,
        tax=9.98,
        tip=0.0,
    )


def _mock_client(*payments: dict) -> MagicMock:
    client = MagicMock()
    client.user_id = 1
    client.get.return_value = [{"Payment": p} for p in payments]
    return client


def _txn(id_: int, value: float, description: str) -> dict:
    return {"id": id_, "amount": {"value": str(value)}, "description": description,
            "created": "2026-04-25T12:00:00", "counterparty_alias": {"display_name": "Sugar Daddy"}}


# ── reconcile ─────────────────────────────────────────────────────────────────

def test_all_paid(split):
    client = _mock_client(
        _txn(1, 13.31, "Tikkie repayment — Sarah"),
        _txn(2, 22.39, "Tikkie repayment — Tom"),
    )
    result = reconcile(client, 99, split)

    assert result["total_repaid"] == 35.70
    assert result["net_cost"] == pytest.approx(21.78, abs=0.01)
    assert result["remaining_owed"] == 0.0
    assert all(p["paid"] for p in result["payments"])


def test_none_paid(split):
    client = _mock_client()
    result = reconcile(client, 99, split)

    assert result["total_repaid"] == 0.0
    assert result["net_cost"] == 57.48
    assert not any(p["paid"] for p in result["payments"])


def test_partial_payment(split):
    client = _mock_client(_txn(1, 13.31, "Tikkie repayment — Sarah"))
    result = reconcile(client, 99, split)

    sarah = next(p for p in result["payments"] if p["name"] == "Sarah")
    tom   = next(p for p in result["payments"] if p["name"] == "Tom")

    assert sarah["paid"] is True
    assert tom["paid"] is False
    assert result["total_repaid"] == pytest.approx(13.31, abs=0.01)
    assert result["net_cost"] == pytest.approx(57.48 - 13.31, abs=0.01)


def test_you_excluded_from_payments(split):
    """'You' should never appear in the payments list."""
    client = _mock_client()
    result = reconcile(client, 99, split)
    names = [p["name"] for p in result["payments"]]
    assert "You" not in names


def test_paid_at_and_transaction_id_populated(split):
    client = _mock_client(_txn(42, 13.31, "Tikkie repayment — Sarah"))
    result = reconcile(client, 99, split)
    sarah = next(p for p in result["payments"] if p["name"] == "Sarah")
    assert sarah["transaction_id"] == 42
    assert sarah["paid_at"] == "2026-04-25T12:00:00"


def test_no_duplicate_match(split):
    """Same transaction must not be matched to two different people."""
    client = _mock_client(_txn(1, 13.31, "random payment"))
    result = reconcile(client, 99, split)
    paid_count = sum(1 for p in result["payments"] if p["paid"])
    assert paid_count <= 1


# ── _find_match ───────────────────────────────────────────────────────────────

def test_name_match_takes_priority():
    txns = [
        {"id": 1, "value": 99.0,  "description": "Tikkie repayment — Sarah", "created": ""},
        {"id": 2, "value": 13.31, "description": "Other payment",            "created": ""},
    ]
    match = _find_match("Sarah", 13.31, txns, set())
    assert match["id"] == 1


def test_amount_fallback():
    txns = [{"id": 5, "value": 13.31, "description": "Random", "created": ""}]
    match = _find_match("Unknown", 13.31, txns, set())
    assert match is not None
    assert match["id"] == 5


def test_used_id_skipped():
    txns = [{"id": 7, "value": 13.31, "description": "Tikkie — Sarah", "created": ""}]
    match = _find_match("Sarah", 13.31, txns, {7})
    assert match is None


def test_amount_tolerance():
    txns = [{"id": 9, "value": 13.32, "description": "Payment", "created": ""}]
    match = _find_match("Nobody", 13.31, txns, set())
    assert match is not None  # within 0.02 tolerance


def test_split_txn_description_matched_by_name():
    """SPLIT|TXN{id}|{name}|{amount} format is matched by the name-based search."""
    txns = [{"id": 11, "value": 13.31, "description": "SPLIT|TXN100|Sarah|13.31", "created": ""}]
    match = _find_match("Sarah", 13.31, txns, set())
    assert match is not None
    assert match["id"] == 11


def test_split_txn_description_all_paid(split):
    """Reconciler correctly matches SPLIT|TXN formatted Tikkie descriptions."""
    client = _mock_client(
        _txn(1, 13.31, "SPLIT|TXN999|Sarah|13.31"),
        _txn(2, 22.39, "SPLIT|TXN999|Tom|22.39"),
    )
    result = reconcile(client, 99, split)
    sarah = next(p for p in result["payments"] if p["name"] == "Sarah")
    tom   = next(p for p in result["payments"] if p["name"] == "Tom")
    assert sarah["paid"] is True
    assert tom["paid"] is True
    assert result["total_repaid"] == pytest.approx(35.70, abs=0.01)
