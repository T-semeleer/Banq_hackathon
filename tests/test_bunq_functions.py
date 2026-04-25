"""
Tests for src/bunq.py — inject_links() (pure) and create_payment_links() (mocked).
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "hackathon_toolkit-main"))

from matcher import PersonShare, ReceiptItem, SplitResult  # noqa: E402
from bunq import create_payment_links, inject_links  # noqa: E402


# ── inject_links (pure function) ──────────────────────────────────────────────

def _split_dict(names: list[str]) -> dict:
    return {
        "people": [
            {"name": n, "total_owed": 10.0, "bunqme_url": None, "payment_status": "pending"}
            for n in names
        ],
        "total": 10.0 * len(names),
        "status": "review",
    }


def test_inject_links_adds_urls():
    d = _split_dict(["Sarah", "Tom"])
    urls = {"Sarah": "https://bunq.me/sarah", "Tom": "https://bunq.me/tom"}
    result = inject_links(d, urls)
    assert result["people"][0]["bunqme_url"] == "https://bunq.me/sarah"
    assert result["people"][1]["bunqme_url"] == "https://bunq.me/tom"


def test_inject_links_sets_payment_status_to_link_created():
    d = _split_dict(["Alice"])
    result = inject_links(d, {"Alice": "https://bunq.me/alice"})
    assert result["people"][0]["payment_status"] == "link_created"


def test_inject_links_none_url_leaves_status_pending():
    d = _split_dict(["Bob"])
    result = inject_links(d, {"Bob": None})
    assert result["people"][0]["bunqme_url"] is None
    assert result["people"][0]["payment_status"] == "pending"


def test_inject_links_partial_urls():
    d = _split_dict(["Alice", "Bob"])
    result = inject_links(d, {"Alice": "https://bunq.me/alice", "Bob": None})
    assert result["people"][0]["payment_status"] == "link_created"
    assert result["people"][1]["payment_status"] == "pending"


def test_inject_links_unknown_person_ignored():
    d = _split_dict(["Alice"])
    result = inject_links(d, {"Alice": "https://bunq.me/alice", "Ghost": "https://bunq.me/x"})
    assert len(result["people"]) == 1


def test_inject_links_empty_people():
    d = {"people": [], "total": 0.0}
    result = inject_links(d, {"Alice": "https://bunq.me/alice"})
    assert result["people"] == []


def test_inject_links_returns_same_dict():
    d = _split_dict(["Alice"])
    result = inject_links(d, {"Alice": "https://bunq.me/x"})
    assert result is d   # mutates and returns the original


# ── create_payment_links (mocked BunqClient) ──────────────────────────────────

def _mock_client(share_url: str = "https://bunq.me/test") -> MagicMock:
    client = MagicMock()
    client.user_id = 1
    client.post.return_value = [{"Id": {"id": 42}}]
    client.get.return_value = [{"BunqMeTab": {"bunqme_tab_share_url": share_url}}]
    return client


def _make_split(*people: tuple[str, float]) -> SplitResult:
    return SplitResult(
        people=[
            PersonShare(name=n, items=[], subtotal=a, tax_share=0.0, tip_share=0.0, total_owed=a)
            for n, a in people
        ],
        unassigned=[],
        total=sum(a for _, a in people),
        tax=0.0, tip=0.0,
    )


def test_create_payment_links_returns_url_per_person():
    split = _make_split(("Sarah", 13.31), ("Tom", 22.39))
    mock_client = _mock_client("https://bunq.me/generated")
    with patch("bunq._get_client", return_value=(mock_client, 99)):
        urls = create_payment_links(split)
    assert "Sarah" in urls
    assert "Tom" in urls
    assert urls["Sarah"] == "https://bunq.me/generated"
    assert urls["Tom"] == "https://bunq.me/generated"


def test_create_payment_links_zero_amount_gets_none():
    split = _make_split(("Sarah", 0.0), ("Tom", 22.39))
    mock_client = _mock_client()
    with patch("bunq._get_client", return_value=(mock_client, 99)):
        urls = create_payment_links(split)
    assert urls["Sarah"] is None
    assert urls["Tom"] is not None


def test_create_payment_links_posts_correct_amount():
    split = _make_split(("Alice", 15.50))
    mock_client = _mock_client()
    with patch("bunq._get_client", return_value=(mock_client, 99)):
        create_payment_links(split)
    call_body = mock_client.post.call_args[0][1]
    amount = call_body["bunqme_tab_entry"]["amount_inquired"]
    assert amount["value"] == "15.50"
    assert amount["currency"] == "EUR"


def test_create_payment_links_includes_name_in_description():
    split = _make_split(("Charlie", 10.00))
    mock_client = _mock_client()
    with patch("bunq._get_client", return_value=(mock_client, 99)):
        create_payment_links(split)
    call_body = mock_client.post.call_args[0][1]
    description = call_body["bunqme_tab_entry"]["description"]
    assert "Charlie" in description


def test_create_payment_links_empty_split():
    split = _make_split()
    mock_client = _mock_client()
    with patch("bunq._get_client", return_value=(mock_client, 99)):
        urls = create_payment_links(split)
    assert urls == {}
    mock_client.post.assert_not_called()


def test_create_payment_links_fetches_tab_after_post():
    split = _make_split(("Dave", 8.00))
    mock_client = _mock_client()
    mock_client.post.return_value = [{"Id": {"id": 777}}]
    with patch("bunq._get_client", return_value=(mock_client, 99)):
        create_payment_links(split)
    get_call_url = mock_client.get.call_args[0][0]
    assert "777" in get_call_url
    assert "bunqme-tab" in get_call_url
