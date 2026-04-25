"""
Tests for src/ocr.py — parse_response(), _parse_price(), _content_type().
No AWS calls are made; all data is synthetic Textract response shapes.
boto3/PIL are mocked at import time so tests run without AWS packages.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Mock heavy AWS/imaging deps before src/ocr.py is imported
for _mod in ("boto3", "PIL", "PIL.Image"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from ocr import ReceiptItem, ReceiptResult, _content_type, _parse_price, parse_response


# ── helpers ───────────────────────────────────────────────────────────────────

def _summary_field(field_type: str, value_text: str, use_amount_key: bool = False) -> dict:
    value_block = {"Text": value_text}
    key = "Amount" if use_amount_key else "ValueDetection"
    return {"Type": {"Text": field_type}, key: value_block}


def _line_item(name: str, price: str) -> dict:
    return {
        "LineItemExpenseFields": [
            {"Type": {"Text": "ITEM"},  "ValueDetection": {"Text": name}},
            {"Type": {"Text": "PRICE"}, "ValueDetection": {"Text": price}},
        ]
    }


def _build_response(
    summary_fields: list[dict],
    line_items: list[dict] | None = None,
) -> dict:
    doc = {
        "SummaryFields": summary_fields,
        "LineItemGroups": [{"LineItems": line_items or []}],
    }
    return {"ExpenseDocuments": [doc]}


IMAGE_URL = "https://bucket.s3.amazonaws.com/receipts/test.jpg"


# ── _parse_price ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("14.50",   14.50),
    ("$14.50",  14.50),
    ("€14.50",  14.50),
    ("£14.50",  14.50),
    ("1,234.56", 1234.56),
    ("  9.98 ", 9.98),
    ("0.00",    0.00),
    ("100",     100.0),
])
def test_parse_price_valid(text, expected):
    assert _parse_price(text) == pytest.approx(expected)


@pytest.mark.parametrize("text", ["", "N/A", "abc", "—", "   "])
def test_parse_price_invalid_returns_none(text):
    assert _parse_price(text) is None


# ── _content_type ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("suffix,expected", [
    (".jpg",  "image/jpeg"),
    (".jpeg", "image/jpeg"),
    (".JPG",  "image/jpeg"),
    (".png",  "image/png"),
    (".webp", "image/webp"),
    (".heic", "image/heic"),
    (".bmp",  "image/jpeg"),   # unknown → fallback
])
def test_content_type(suffix, expected):
    assert _content_type(suffix) == expected


# ── parse_response: line items ─────────────────────────────────────────────────

def test_parse_response_basic_items():
    resp = _build_response(
        summary_fields=[
            _summary_field("TOTAL", "57.48"),
            _summary_field("VENDOR_NAME", "THE BISTRO"),
        ],
        line_items=[
            _line_item("Grilled Chicken", "14.50"),
            _line_item("Caesar Salad",    "11.00"),
        ],
    )
    result = parse_response(resp, IMAGE_URL)

    assert result.vendor == "THE BISTRO"
    assert len(result.items) == 2
    assert result.items[0].name == "Grilled Chicken"
    assert result.items[0].price == pytest.approx(14.50)
    assert result.items[1].price == pytest.approx(11.00)
    assert result.total == pytest.approx(57.48)
    assert result.image_url == IMAGE_URL


def test_parse_response_amount_paid_overrides_total():
    resp = _build_response(summary_fields=[
        _summary_field("TOTAL",       "50.00", use_amount_key=True),
        _summary_field("AMOUNT_PAID", "57.48", use_amount_key=True),
    ])
    result = parse_response(resp, IMAGE_URL)
    assert result.total == pytest.approx(57.48)   # AMOUNT_PAID wins


def test_parse_response_amount_due_fallback():
    resp = _build_response(summary_fields=[
        _summary_field("AMOUNT_DUE", "32.50", use_amount_key=True),
    ])
    result = parse_response(resp, IMAGE_URL)
    assert result.total == pytest.approx(32.50)


def test_parse_response_multiple_totals_takes_max():
    resp = _build_response(summary_fields=[
        _summary_field("TOTAL", "40.00", use_amount_key=True),
        _summary_field("TOTAL", "57.48", use_amount_key=True),
    ])
    result = parse_response(resp, IMAGE_URL)
    assert result.total == pytest.approx(57.48)


def test_parse_response_tax_extracted():
    resp = _build_response(summary_fields=[
        _summary_field("TAX", "9.98", use_amount_key=True),
        _summary_field("TOTAL", "57.48", use_amount_key=True),
    ])
    result = parse_response(resp, IMAGE_URL)
    assert result.tax == pytest.approx(9.98)


def test_parse_response_zero_tax_ignored():
    resp = _build_response(summary_fields=[
        _summary_field("TAX", "0.00", use_amount_key=True),
    ])
    result = parse_response(resp, IMAGE_URL)
    assert result.tax is None   # zero tax is not stored


def test_parse_response_no_vendor():
    resp = _build_response(summary_fields=[
        _summary_field("TOTAL", "20.00", use_amount_key=True),
    ])
    result = parse_response(resp, IMAGE_URL)
    assert result.vendor is None


def test_parse_response_empty_document():
    result = parse_response({"ExpenseDocuments": []}, IMAGE_URL)
    assert result.items == []
    assert result.total is None
    assert result.tax is None
    assert result.vendor is None


def test_parse_response_item_without_price_skipped():
    resp = _build_response(
        summary_fields=[],
        line_items=[
            {"LineItemExpenseFields": [
                {"Type": {"Text": "ITEM"}, "ValueDetection": {"Text": "Mystery Item"}},
            ]}
        ],
    )
    result = parse_response(resp, IMAGE_URL)
    assert result.items == []    # no price → not included


def test_parse_response_item_without_name_skipped():
    resp = _build_response(
        summary_fields=[],
        line_items=[
            {"LineItemExpenseFields": [
                {"Type": {"Text": "PRICE"}, "ValueDetection": {"Text": "9.99"}},
            ]}
        ],
    )
    result = parse_response(resp, IMAGE_URL)
    assert result.items == []    # no name → not included


def test_parse_response_image_url_passed_through():
    resp = _build_response(summary_fields=[])
    url = "https://custom.bucket/receipts/xyz.jpg"
    result = parse_response(resp, url)
    assert result.image_url == url


def test_parse_response_vendor_prefers_shortest_single_line():
    resp = _build_response(summary_fields=[
        _summary_field("VENDOR_NAME", "THE BISTRO AMSTERDAM"),
        _summary_field("VENDOR_NAME", "BISTRO"),
    ])
    result = parse_response(resp, IMAGE_URL)
    assert result.vendor == "BISTRO"


def test_parse_response_multiline_vendor_uses_first_line():
    resp = _build_response(summary_fields=[
        _summary_field("VENDOR_NAME", "THE BISTRO\n123 Main St"),
    ])
    result = parse_response(resp, IMAGE_URL)
    assert result.vendor == "THE BISTRO"
