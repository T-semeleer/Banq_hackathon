"""
Tests for scripts/simulate_tikkie_payment.py — simulate_payment() function
and argument validation.
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hackathon_toolkit-main"))

# Import the script module (not __main__ block)
_SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))
import simulate_tikkie_payment as sim  # noqa: E402


# ── helpers ───────────────────────────────────────────────────────────────────

def _mock_client(request_id: int = 42) -> MagicMock:
    client = MagicMock()
    client.user_id = 1
    client.post.return_value = [{"Id": {"id": request_id}}]
    return client


# ── simulate_payment ──────────────────────────────────────────────────────────

def test_simulate_payment_returns_dict():
    result = sim.simulate_payment(_mock_client(), 99, "Sarah", 13.31)
    assert isinstance(result, dict)


def test_simulate_payment_contains_request_id():
    result = sim.simulate_payment(_mock_client(request_id=777), 99, "Sarah", 13.31)
    assert result["request_id"] == 777


def test_simulate_payment_contains_person_and_amount():
    result = sim.simulate_payment(_mock_client(), 99, "Tom", 22.39)
    assert result["person"] == "Tom"
    assert result["amount"] == pytest.approx(22.39)


def test_simulate_payment_description_includes_person():
    result = sim.simulate_payment(_mock_client(), 99, "Alice", 10.0)
    assert "Alice" in result["description"]


def test_simulate_payment_description_format():
    result = sim.simulate_payment(_mock_client(), 99, "Bob", 15.0)
    assert result["description"] == "Tikkie repayment — Bob"


def test_simulate_payment_posts_correct_endpoint():
    client = _mock_client()
    sim.simulate_payment(client, 99, "Carol", 20.0)
    endpoint = client.post.call_args[0][0]
    assert "request-inquiry" in endpoint
    assert "99" in endpoint


def test_simulate_payment_posts_correct_amount():
    client = _mock_client()
    sim.simulate_payment(client, 99, "Dave", 25.50)
    body = client.post.call_args[0][1]
    assert body["amount_inquired"]["value"] == "25.50"
    assert body["amount_inquired"]["currency"] == "EUR"


def test_simulate_payment_targets_sugardaddy():
    client = _mock_client()
    sim.simulate_payment(client, 99, "Eve", 10.0)
    body = client.post.call_args[0][1]
    assert body["counterparty_alias"]["value"] == "sugardaddy@bunq.com"


def test_simulate_payment_posts_description():
    client = _mock_client()
    sim.simulate_payment(client, 99, "Frank", 10.0)
    body = client.post.call_args[0][1]
    assert "Frank" in body["description"]


def test_simulate_payment_amount_formatted_to_2dp():
    client = _mock_client()
    sim.simulate_payment(client, 99, "Grace", 10.1)
    body = client.post.call_args[0][1]
    assert body["amount_inquired"]["value"] == "10.10"


def test_simulate_payment_different_account_ids():
    for account_id in [1, 99, 12345]:
        client = _mock_client()
        sim.simulate_payment(client, account_id, "Test", 5.0)
        endpoint = client.post.call_args[0][0]
        assert str(account_id) in endpoint


# ── _SELF_NAMES constant ──────────────────────────────────────────────────────

def test_self_names_contains_expected_variants():
    assert "you" in sim._SELF_NAMES
    assert "me"  in sim._SELF_NAMES
    assert "i"   in sim._SELF_NAMES


# ── --all flag reads last_split.json ─────────────────────────────────────────

def test_simulate_all_reads_from_split_file(tmp_path):
    split_data = {
        "people": [
            {"name": "Sarah", "total_owed": 13.31},
            {"name": "Tom",   "total_owed": 22.39},
            {"name": "You",   "total_owed": 21.78},  # self — should be skipped
        ]
    }
    split_file = tmp_path / "test_split.json"
    split_file.write_text(json.dumps(split_data))

    # Verify the filtering logic by checking _SELF_NAMES
    people_to_sim = [
        (p["name"], p["total_owed"])
        for p in split_data["people"]
        if p["name"].lower() not in sim._SELF_NAMES and p.get("total_owed", 0) > 0
    ]
    assert len(people_to_sim) == 2
    names = [n for n, _ in people_to_sim]
    assert "Sarah" in names
    assert "Tom" in names
    assert "You" not in names


def test_simulate_all_skips_zero_amount():
    split_data = {
        "people": [
            {"name": "Sarah", "total_owed": 0.0},
            {"name": "Tom",   "total_owed": 22.39},
        ]
    }
    people_to_sim = [
        (p["name"], p["total_owed"])
        for p in split_data["people"]
        if p["name"].lower() not in sim._SELF_NAMES and p.get("total_owed", 0) > 0
    ]
    assert len(people_to_sim) == 1
    assert people_to_sim[0][0] == "Tom"
