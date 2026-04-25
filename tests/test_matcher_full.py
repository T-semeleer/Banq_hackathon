"""
Comprehensive tests for src/matcher.py.
Covers _parse(), result_to_dict(), and match() with mocked Claude.
"""
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("ANTHROPIC_API_KEY", "test-dummy-key")

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "hackathon_toolkit-main"))

from matcher import (  # noqa: E402
    PersonShare,
    ReceiptItem,
    SplitResult,
    _parse,
    match,
    result_to_dict,
)


# ── _parse ────────────────────────────────────────────────────────────────────

def test_parse_full_result():
    raw = {
        "people": [
            {"name": "Alice", "items": [{"name": "Burger", "price": 12.50}],
             "subtotal": 12.50, "tax_share": 2.63, "tip_share": 1.25, "total_owed": 16.38},
        ],
        "unassigned": [],
        "total": 16.38, "tax": 2.63, "tip": 1.25,
    }
    result = _parse(raw)
    assert isinstance(result, SplitResult)
    assert len(result.people) == 1
    assert result.people[0].name == "Alice"
    assert result.people[0].items[0].name == "Burger"
    assert result.people[0].total_owed == pytest.approx(16.38)
    assert result.total == pytest.approx(16.38)
    assert result.tax == pytest.approx(2.63)
    assert result.tip == pytest.approx(1.25)


def test_parse_empty_people():
    raw = {"people": [], "unassigned": [], "total": 0.0, "tax": 0.0, "tip": 0.0}
    result = _parse(raw)
    assert result.people == []
    assert result.total == 0.0


def test_parse_unassigned_items():
    raw = {
        "people": [],
        "unassigned": [{"name": "Dessert", "price": 6.50}],
        "total": 6.50, "tax": 0.0, "tip": 0.0,
    }
    result = _parse(raw)
    assert len(result.unassigned) == 1
    assert result.unassigned[0].name == "Dessert"
    assert result.unassigned[0].price == pytest.approx(6.50)


def test_parse_missing_tip_defaults_zero():
    raw = {
        "people": [],
        "unassigned": [],
        "total": 20.0,
        "tax": 2.0,
        # tip is missing
    }
    result = _parse(raw)
    assert result.tip == 0.0


def test_parse_missing_all_optional_fields():
    result = _parse({})
    assert result.people == []
    assert result.unassigned == []
    assert result.total == 0.0
    assert result.tax == 0.0
    assert result.tip == 0.0


def test_parse_multiple_items_per_person():
    raw = {
        "people": [
            {
                "name": "Bob",
                "items": [
                    {"name": "Pasta", "price": 13.50},
                    {"name": "Beer",  "price": 5.00},
                    {"name": "Water", "price": 2.50},
                ],
                "subtotal": 21.0, "tax_share": 4.41, "tip_share": 0.0, "total_owed": 25.41,
            }
        ],
        "unassigned": [], "total": 25.41, "tax": 4.41, "tip": 0.0,
    }
    result = _parse(raw)
    assert len(result.people[0].items) == 3
    assert result.people[0].items[1].name == "Beer"


# ── result_to_dict ────────────────────────────────────────────────────────────

@pytest.fixture
def sample_split():
    return SplitResult(
        people=[
            PersonShare(
                name="You",
                items=[ReceiptItem("Chicken", 14.50)],
                subtotal=14.50, tax_share=3.05, tip_share=0.0, total_owed=17.55,
            ),
            PersonShare(
                name="Sarah",
                items=[ReceiptItem("Salad", 11.00)],
                subtotal=11.00, tax_share=2.31, tip_share=0.0, total_owed=13.31,
            ),
        ],
        unassigned=[ReceiptItem("Coffee", 2.50)],
        total=30.81, tax=5.36, tip=0.0,
    )


def test_result_to_dict_top_level_keys(sample_split):
    d = result_to_dict(sample_split)
    assert set(d.keys()) == {"people", "unassigned", "total", "tax", "tip", "status"}


def test_result_to_dict_status(sample_split):
    d = result_to_dict(sample_split)
    assert d["status"] == "review"


def test_result_to_dict_person_fields(sample_split):
    d = result_to_dict(sample_split)
    for person in d["people"]:
        assert "name" in person
        assert "items" in person
        assert "subtotal" in person
        assert "tax_share" in person
        assert "tip_share" in person
        assert "total_owed" in person
        assert "bunqme_url" in person
        assert "payment_status" in person
        assert person["bunqme_url"] is None
        assert person["payment_status"] == "pending"


def test_result_to_dict_unassigned(sample_split):
    d = result_to_dict(sample_split)
    assert len(d["unassigned"]) == 1
    assert d["unassigned"][0]["name"] == "Coffee"
    assert d["unassigned"][0]["price"] == pytest.approx(2.50)


def test_result_to_dict_totals(sample_split):
    d = result_to_dict(sample_split)
    assert d["total"] == pytest.approx(30.81)
    assert d["tax"]   == pytest.approx(5.36)
    assert d["tip"]   == 0.0


def test_result_to_dict_empty_split():
    empty = SplitResult(people=[], unassigned=[], total=0.0, tax=0.0, tip=0.0)
    d = result_to_dict(empty)
    assert d["people"] == []
    assert d["unassigned"] == []


# ── match() with mocked Claude ────────────────────────────────────────────────

_MOCK_RESPONSE = {
    "people": [
        {"name": "You", "items": [{"name": "Chicken", "price": 14.50}],
         "subtotal": 14.50, "tax_share": 3.05, "tip_share": 0.0, "total_owed": 17.55},
        {"name": "Bob", "items": [{"name": "Pasta", "price": 13.50}],
         "subtotal": 13.50, "tax_share": 2.84, "tip_share": 0.0, "total_owed": 16.34},
    ],
    "unassigned": [], "total": 33.89, "tax": 5.89, "tip": 0.0,
}


def _mock_claude(raw: dict) -> MagicMock:
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps(raw))]
    c = MagicMock()
    c.messages.create.return_value = msg
    return c


def test_match_calls_create_once():
    mock = _mock_claude(_MOCK_RESPONSE)
    with patch("matcher.anthropic.Anthropic", return_value=mock):
        match("receipt text", "I had chicken, Bob had pasta.")
    mock.messages.create.assert_called_once()


def test_match_passes_ocr_text_in_prompt():
    mock = _mock_claude(_MOCK_RESPONSE)
    with patch("matcher.anthropic.Anthropic", return_value=mock):
        match("UNIQUE_RECEIPT_TEXT_MARKER", "transcript")
    call_kwargs = mock.messages.create.call_args
    user_content = call_kwargs[1]["messages"][0]["content"]
    assert "UNIQUE_RECEIPT_TEXT_MARKER" in user_content


def test_match_passes_transcript_in_prompt():
    mock = _mock_claude(_MOCK_RESPONSE)
    with patch("matcher.anthropic.Anthropic", return_value=mock):
        match("receipt", "UNIQUE_TRANSCRIPT_MARKER_HERE")
    call_kwargs = mock.messages.create.call_args
    user_content = call_kwargs[1]["messages"][0]["content"]
    assert "UNIQUE_TRANSCRIPT_MARKER_HERE" in user_content


def test_match_returns_split_result():
    mock = _mock_claude(_MOCK_RESPONSE)
    with patch("matcher.anthropic.Anthropic", return_value=mock):
        result = match("receipt", "transcript")
    assert isinstance(result, SplitResult)
    assert len(result.people) == 2
    assert result.total == pytest.approx(33.89)


def test_match_strips_whitespace_from_inputs():
    mock = _mock_claude(_MOCK_RESPONSE)
    with patch("matcher.anthropic.Anthropic", return_value=mock):
        # should not raise even with extra whitespace
        result = match("  receipt  \n", "\ntranscript  ")
    assert isinstance(result, SplitResult)


def test_match_raises_on_invalid_json():
    msg = MagicMock()
    msg.content = [MagicMock(text="not valid json at all")]
    mock = MagicMock()
    mock.messages.create.return_value = msg
    with patch("matcher.anthropic.Anthropic", return_value=mock):
        with pytest.raises(json.JSONDecodeError):
            match("receipt", "transcript")


def test_match_uses_correct_model():
    mock = _mock_claude(_MOCK_RESPONSE)
    with patch("matcher.anthropic.Anthropic", return_value=mock):
        match("receipt", "transcript")
    call_kwargs = mock.messages.create.call_args[1]
    assert call_kwargs["model"] == "claude-sonnet-4-6"
