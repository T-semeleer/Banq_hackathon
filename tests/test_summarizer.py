"""Tests for the monthly expense netting summarizer."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add src/ and toolkit to path
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "hackathon_toolkit-main"))

from summarizer import summarize_month, _parse_split_ref  # noqa: E402


def _make_client(payments: list[dict]) -> MagicMock:
    client = MagicMock()
    client.user_id = 1
    client.get.return_value = [{"Payment": p} for p in payments]
    return client


def _payment(pid, value, description, created="2026-04-15 12:00:00.000000", ptype="BUNQ"):
    return {
        "id": pid,
        "amount": {"value": str(value), "currency": "EUR"},
        "description": description,
        "created": created,
        "type": ptype,
    }


# ── _parse_split_ref ──────────────────────────────────────────────────────────

def test_parse_split_ref_valid():
    result = _parse_split_ref("SPLIT|TXN123|Sarah|14.50")
    assert result == (123, "Sarah", 14.50)


def test_parse_split_ref_case_insensitive():
    result = _parse_split_ref("split|txn999|Mark|7.25")
    assert result == (999, "Mark", 7.25)


def test_parse_split_ref_embedded_in_longer_string():
    result = _parse_split_ref("Some prefix SPLIT|TXN42|Alice|20.00 suffix")
    assert result == (42, "Alice", 20.00)


def test_parse_split_ref_no_match():
    assert _parse_split_ref("Tikkie repayment — Sarah") is None
    assert _parse_split_ref("Salary April") is None
    assert _parse_split_ref("") is None


# ── summarize_month ───────────────────────────────────────────────────────────

def test_tikkie_netted_against_expense():
    """Tikkie with SPLIT reference offsets gross expense, not counted as income."""
    payments = [
        _payment(100, "-57.48", "Restaurant De Keuken"),
        _payment(101, "19.00", "SPLIT|TXN100|Sarah|19.00"),
        _payment(102, "14.50", "SPLIT|TXN100|Mark|14.50"),
    ]
    client = _make_client(payments)
    result = summarize_month(client, 1, 2026, 4)

    assert len(result["expenses"]) == 1
    exp = result["expenses"][0]
    assert exp["transaction_id"] == 100
    assert exp["gross_amount"] == 57.48
    assert len(exp["reimbursements"]) == 2
    assert exp["net_personal_amount"] == round(57.48 - 19.00 - 14.50, 2)

    # Tikkies must NOT appear in income
    assert result["income"] == []
    assert result["totals"]["tikkie_reimbursements_received"] == 33.50
    assert result["totals"]["net_personal_expenses"] == exp["net_personal_amount"]


def test_non_tikkie_income_goes_to_income():
    """Regular incoming payments without SPLIT tag appear in income, not expenses."""
    payments = [
        _payment(200, "3000.00", "Salary April"),
        _payment(201, "-50.00", "Supermarket"),
    ]
    client = _make_client(payments)
    result = summarize_month(client, 1, 2026, 4)

    assert len(result["income"]) == 1
    assert result["income"][0]["transaction_id"] == 200
    assert result["totals"]["other_income"] == 3000.00
    assert result["totals"]["tikkie_reimbursements_received"] == 0.0


def test_unmatched_tikkie_goes_to_unmatched():
    """Tikkie referencing an expense not in this period goes to unmatched_tikkies."""
    payments = [
        _payment(300, "14.50", "SPLIT|TXN999|Sarah|14.50"),  # TXN999 not in month
    ]
    client = _make_client(payments)
    result = summarize_month(client, 1, 2026, 4)

    assert len(result["unmatched_tikkies"]) == 1
    assert result["unmatched_tikkies"][0]["expense_id"] == 999
    # Unmatched Tikkie is NOT in income and NOT netted
    assert result["income"] == []
    assert result["totals"]["tikkie_reimbursements_received"] == 0.0


def test_net_personal_amount_never_negative():
    """Net cost is clamped at 0 even if reimbursements exceed the expense."""
    payments = [
        _payment(400, "-10.00", "Coffee"),
        _payment(401, "15.00", "SPLIT|TXN400|Friend|15.00"),  # over-reimbursed
    ]
    client = _make_client(payments)
    result = summarize_month(client, 1, 2026, 4)

    assert result["expenses"][0]["net_personal_amount"] == 0.0


def test_mixed_scenario_totals():
    """Gross expenses, Tikkie netting, and other income are all correct."""
    payments = [
        _payment(500, "-100.00", "Dinner"),
        _payment(501, "40.00", "SPLIT|TXN500|Alice|40.00"),
        _payment(502, "30.00", "SPLIT|TXN500|Bob|30.00"),
        _payment(503, "2000.00", "Wages"),
        _payment(504, "-25.00", "Groceries"),
    ]
    client = _make_client(payments)
    result = summarize_month(client, 1, 2026, 4)

    assert result["totals"]["gross_expenses"] == 125.00
    assert result["totals"]["tikkie_reimbursements_received"] == 70.00
    assert result["totals"]["net_personal_expenses"] == round(100 - 70 + 25, 2)
    assert result["totals"]["other_income"] == 2000.00


def test_empty_month():
    """No payments → all totals are zero."""
    client = _make_client([])
    result = summarize_month(client, 1, 2026, 4)

    assert result["expenses"] == []
    assert result["income"] == []
    assert result["totals"]["gross_expenses"] == 0.0
    assert result["totals"]["net_personal_expenses"] == 0.0


def test_period_label():
    client = _make_client([])
    result = summarize_month(client, 1, 2026, 4)
    assert result["period"] == "2026-04"


# ── month boundary filtering ──────────────────────────────────────────────────

def test_payments_from_later_month_excluded():
    """Payments dated after month-end (e.g. May) must not appear in April summary."""
    payments = [
        _payment(100, "-50.00", "May expense",   created="2026-05-01 10:00:00.000000"),
        _payment(101, "-30.00", "April expense",  created="2026-04-15 10:00:00.000000"),
    ]
    client = _make_client(payments)
    result = summarize_month(client, 1, 2026, 4)

    ids = [e["transaction_id"] for e in result["expenses"]]
    assert 101 in ids
    assert 100 not in ids


def test_payments_from_earlier_month_excluded():
    """Payments dated before month-start (e.g. March) must not appear in April summary."""
    payments = [
        _payment(200, "-30.00", "April expense", created="2026-04-10 10:00:00.000000"),
        _payment(201, "-20.00", "March expense", created="2026-03-20 10:00:00.000000"),
    ]
    client = _make_client(payments)
    result = summarize_month(client, 1, 2026, 4)

    ids = [e["transaction_id"] for e in result["expenses"]]
    assert 200 in ids
    assert 201 not in ids


def test_payments_on_month_boundaries_included():
    """Payments on the first and last day of the month are included."""
    payments = [
        _payment(300, "-10.00", "First day",  created="2026-04-01 00:00:00.000000"),
        _payment(301, "-10.00", "Last day",   created="2026-04-30 23:59:59.000000"),
    ]
    client = _make_client(payments)
    result = summarize_month(client, 1, 2026, 4)

    ids = [e["transaction_id"] for e in result["expenses"]]
    assert 300 in ids
    assert 301 in ids


# ── multiple expenses + multiple Tikkies ──────────────────────────────────────

def test_two_expenses_each_reimbursed_independently():
    """Two separate expenses, each with their own Tikkies, are netted independently."""
    payments = [
        _payment(400, "-60.00", "Dinner"),
        _payment(401, "-40.00", "Lunch"),
        _payment(402, "20.00", "SPLIT|TXN400|Alice|20.00"),
        _payment(403, "15.00", "SPLIT|TXN401|Bob|15.00"),
    ]
    client = _make_client(payments)
    result = summarize_month(client, 1, 2026, 4)

    dinner = next(e for e in result["expenses"] if e["transaction_id"] == 400)
    lunch  = next(e for e in result["expenses"] if e["transaction_id"] == 401)
    assert dinner["net_personal_amount"] == pytest.approx(40.00, abs=0.01)
    assert lunch["net_personal_amount"]  == pytest.approx(25.00, abs=0.01)


def test_three_people_reimburse_same_expense():
    payments = [
        _payment(500, "-90.00", "Group dinner"),
        _payment(501, "30.00", "SPLIT|TXN500|Alice|30.00"),
        _payment(502, "30.00", "SPLIT|TXN500|Bob|30.00"),
        _payment(503, "30.00", "SPLIT|TXN500|Carol|30.00"),
    ]
    client = _make_client(payments)
    result = summarize_month(client, 1, 2026, 4)

    exp = result["expenses"][0]
    assert exp["net_personal_amount"] == 0.0
    assert len(exp["reimbursements"]) == 3
    assert result["totals"]["tikkie_reimbursements_received"] == pytest.approx(90.00)


# ── integration: simulate format → summarizer netting ────────────────────────

def test_netting_uses_description_produced_by_simulate_payment():
    """
    The SPLIT|TXN description written by simulate_tikkie_payment.simulate_payment
    must be parsed and netted correctly by summarize_month.
    """
    import sys
    sys.path.insert(0, str(_ROOT / "scripts"))
    import simulate_tikkie_payment as sim

    # Build the description the same way simulate_payment does
    expense_id = 700
    person = "Sarah"
    amount = 19.50
    description = f"SPLIT|TXN{expense_id}|{person}|{amount:.2f}"

    payments = [
        _payment(expense_id, "-57.48", "Restaurant bill"),
        _payment(701, str(amount), description),
    ]
    client = _make_client(payments)
    result = summarize_month(client, 1, 2026, 4)

    exp = result["expenses"][0]
    assert exp["transaction_id"] == expense_id
    assert len(exp["reimbursements"]) == 1
    assert exp["reimbursements"][0]["from"] == person
    assert exp["reimbursements"][0]["amount"] == pytest.approx(amount)
    assert exp["net_personal_amount"] == pytest.approx(57.48 - amount, abs=0.01)
    assert result["income"] == []


# ── totals consistency invariants ─────────────────────────────────────────────

def test_net_personal_expenses_equals_sum_of_net_amounts():
    payments = [
        _payment(800, "-100.00", "Expense A"),
        _payment(801, "-50.00",  "Expense B"),
        _payment(802, "40.00",   "SPLIT|TXN800|Alice|40.00"),
    ]
    client = _make_client(payments)
    result = summarize_month(client, 1, 2026, 4)

    computed = sum(e["net_personal_amount"] for e in result["expenses"])
    assert result["totals"]["net_personal_expenses"] == pytest.approx(computed, abs=0.001)


def test_gross_expenses_equals_sum_of_gross_amounts():
    payments = [
        _payment(900, "-75.00", "Expense A"),
        _payment(901, "-25.00", "Expense B"),
    ]
    client = _make_client(payments)
    result = summarize_month(client, 1, 2026, 4)

    computed = sum(e["gross_amount"] for e in result["expenses"])
    assert result["totals"]["gross_expenses"] == pytest.approx(computed, abs=0.001)


def test_other_income_equals_sum_of_income_amounts():
    payments = [
        _payment(1000, "2000.00", "Salary"),
        _payment(1001, "500.00",  "Freelance"),
    ]
    client = _make_client(payments)
    result = summarize_month(client, 1, 2026, 4)

    computed = sum(i["amount"] for i in result["income"])
    assert result["totals"]["other_income"] == pytest.approx(computed, abs=0.001)
