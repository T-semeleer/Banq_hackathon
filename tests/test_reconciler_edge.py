"""
Edge-case tests for src/reconciler.py beyond the basics in test_reconciler.py.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "hackathon_toolkit-main"))

from matcher import PersonShare, ReceiptItem, SplitResult  # noqa: E402
from reconciler import _AMOUNT_TOL, reconcile, _find_match  # noqa: E402


# ── helpers ───────────────────────────────────────────────────────────────────

def _split(*people: tuple[str, float], total: float | None = None) -> SplitResult:
    ps = [
        PersonShare(name=n, items=[], subtotal=a, tax_share=0.0, tip_share=0.0, total_owed=a)
        for n, a in people
    ]
    return SplitResult(
        people=ps,
        unassigned=[],
        total=total if total is not None else sum(a for _, a in people),
        tax=0.0, tip=0.0,
    )


def _txn(id_: int, value: float, description: str = "") -> dict:
    return {
        "id": id_,
        "amount": {"value": str(value)},
        "description": description,
        "created": "2026-04-25T12:00:00",
        "counterparty_alias": {"display_name": "Sugar Daddy"},
    }


def _mock_client(*payments: dict) -> MagicMock:
    client = MagicMock()
    client.user_id = 1
    client.get.return_value = [{"Payment": p} for p in payments]
    return client


# ── outgoing payments (negative) are ignored ─────────────────────────────────

def test_outgoing_transactions_ignored():
    split = _split(("Sarah", 15.0))
    client = _mock_client(
        _txn(1, -15.0, "Tikkie repayment — Sarah"),   # negative = outgoing
        _txn(2,  15.0, "Tikkie repayment — Sarah"),   # positive = incoming
    )
    result = reconcile(client, 99, split)
    sarah = next(p for p in result["payments"] if p["name"] == "Sarah")
    assert sarah["paid"] is True
    assert sarah["transaction_id"] == 2   # matched the positive one


def test_only_outgoing_means_unpaid():
    split = _split(("Tom", 20.0))
    client = _mock_client(_txn(1, -20.0, "Outgoing payment"))
    result = reconcile(client, 99, split)
    assert result["payments"][0]["paid"] is False


# ── self-name variants ────────────────────────────────────────────────────────

@pytest.mark.parametrize("self_name", ["you", "You", "YOU", "me", "Me", "ME", "i", "I"])
def test_all_self_name_variants_excluded(self_name):
    split = _split((self_name, 20.0))
    client = _mock_client(_txn(1, 20.0, f"repayment — {self_name}"))
    result = reconcile(client, 99, split)
    assert result["payments"] == []
    assert result["total_repaid"] == 0.0


# ── large split (10 people) ───────────────────────────────────────────────────

def test_large_split_all_paid():
    people = [(f"Person{i}", 10.0 + i) for i in range(10)]
    split = _split(*people)
    payments = [
        _txn(i, 10.0 + i, f"Tikkie repayment — Person{i}")
        for i in range(10)
    ]
    client = _mock_client(*payments)
    result = reconcile(client, 99, split)
    assert all(p["paid"] for p in result["payments"])
    assert result["remaining_owed"] == 0.0


def test_large_split_none_paid():
    people = [(f"Person{i}", 10.0) for i in range(10)]
    split = _split(*people)
    client = _mock_client()
    result = reconcile(client, 99, split)
    assert result["total_repaid"] == 0.0
    assert len(result["payments"]) == 10


# ── duplicate amount — only one transaction consumed ─────────────────────────

def test_same_amount_two_people_each_get_one_transaction():
    split = _split(("Alice", 10.0), ("Bob", 10.0))
    client = _mock_client(
        _txn(1, 10.0, "Tikkie — Alice"),
        _txn(2, 10.0, "Tikkie — Bob"),
    )
    result = reconcile(client, 99, split)
    alice = next(p for p in result["payments"] if p["name"] == "Alice")
    bob   = next(p for p in result["payments"] if p["name"] == "Bob")
    assert alice["paid"] is True
    assert bob["paid"]   is True
    assert alice["transaction_id"] != bob["transaction_id"]


def test_one_transaction_not_shared_between_two_people():
    split = _split(("Alice", 10.0), ("Bob", 10.0))
    client = _mock_client(_txn(1, 10.0, "Generic payment"))
    result = reconcile(client, 99, split)
    paid_count = sum(1 for p in result["payments"] if p["paid"])
    assert paid_count == 1   # only one person can be matched to the one txn


# ── rounding precision ────────────────────────────────────────────────────────

def test_net_cost_rounding():
    split = _split(("Sarah", 13.31), ("Tom", 22.39), total=57.48)
    client = _mock_client(_txn(1, 13.31, "Tikkie repayment — Sarah"))
    result = reconcile(client, 99, split)
    expected_net = round(57.48 - 13.31, 2)
    assert result["net_cost"] == pytest.approx(expected_net, abs=0.001)


def test_total_repaid_rounding():
    split = _split(("A", 0.1), ("B", 0.2), total=0.3)
    client = _mock_client(
        _txn(1, 0.1, "Tikkie — A"),
        _txn(2, 0.2, "Tikkie — B"),
    )
    result = reconcile(client, 99, split)
    assert result["total_repaid"] == pytest.approx(0.3, abs=0.001)


# ── empty transaction list ────────────────────────────────────────────────────

def test_empty_transaction_list():
    split = _split(("Sarah", 15.0), ("Tom", 20.0))
    client = _mock_client()
    result = reconcile(client, 99, split)
    assert result["total_repaid"] == 0.0
    assert result["net_cost"] == split.total
    assert result["remaining_owed"] == 35.0


# ── response structure completeness ──────────────────────────────────────────

def test_response_has_all_required_keys():
    split = _split(("Alice", 10.0))
    client = _mock_client()
    result = reconcile(client, 99, split)
    required = {"original_total", "payments", "total_repaid", "net_cost", "remaining_owed"}
    assert required.issubset(result.keys())


def test_payment_entry_has_all_required_keys():
    split = _split(("Alice", 10.0))
    client = _mock_client()
    result = reconcile(client, 99, split)
    entry = result["payments"][0]
    assert set(entry.keys()) == {"name", "amount_owed", "paid", "paid_at", "transaction_id"}


def test_net_cost_equals_remaining_when_no_self_in_split():
    split = _split(("Sarah", 13.31), ("Tom", 22.39), total=35.70)
    client = _mock_client()
    result = reconcile(client, 99, split)
    # With no self person, net_cost == original_total == remaining_owed
    assert result["net_cost"] == result["original_total"]
    assert result["remaining_owed"] == result["original_total"]


# ── amount tolerance boundary ─────────────────────────────────────────────────

def test_amount_just_within_tolerance():
    split = _split(("X", 10.00))
    client = _mock_client(_txn(1, 10.00 + _AMOUNT_TOL, "Payment"))
    result = reconcile(client, 99, split)
    assert result["payments"][0]["paid"] is True


def test_amount_just_outside_tolerance():
    split = _split(("X", 10.00))
    client = _mock_client(_txn(1, 10.00 + _AMOUNT_TOL + 0.001, "Payment"))
    result = reconcile(client, 99, split)
    assert result["payments"][0]["paid"] is False
