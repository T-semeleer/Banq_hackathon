import os
import sys
from pathlib import Path

# Resolve the toolkit path relative to this file's location
_TOOLKIT_DIR = Path(__file__).resolve().parents[1] / "hackathon_toolkit-main"
if str(_TOOLKIT_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLKIT_DIR))

from bunq_client import BunqClient  # noqa: E402

from matcher import SplitResult  # noqa: E402


def _get_client() -> tuple[BunqClient, int]:
    """Authenticate and return (client, account_id). Creates a sandbox user if no key is set."""
    api_key = os.getenv("BUNQ_API_KEY", "").strip()
    if not api_key:
        api_key = BunqClient.create_sandbox_user()

    client = BunqClient(api_key=api_key, sandbox=True)
    client.authenticate()
    account_id = client.get_primary_account_id()
    return client, account_id


def create_payment_links(result: SplitResult, description_prefix: str = "SplitBill") -> dict[str, str | None]:
    """
    Create one bunq.me payment link per person in the split result.

    Returns a dict mapping person name → share URL (or None if amount is 0).
    """
    client, account_id = _get_client()
    urls: dict[str, str | None] = {}

    for person in result.people:
        if person.total_owed <= 0:
            urls[person.name] = None
            continue

        amount_str = f"{person.total_owed:.2f}"
        resp = client.post(
            f"user/{client.user_id}/monetary-account/{account_id}/bunqme-tab",
            {
                "bunqme_tab_entry": {
                    "amount_inquired": {"value": amount_str, "currency": "EUR"},
                    "description": f"{description_prefix} — {person.name} owes €{amount_str}",
                },
            },
        )
        tab_id = resp[0]["Id"]["id"]

        tab_data = client.get(
            f"user/{client.user_id}/monetary-account/{account_id}/bunqme-tab/{tab_id}"
        )
        tab = tab_data[0]["BunqMeTab"]
        urls[person.name] = tab.get("bunqme_tab_share_url")

    return urls


def inject_links(split_dict: dict, urls: dict[str, str | None]) -> dict:
    """Merge payment URLs into the dict produced by result_to_dict()."""
    for person in split_dict.get("people", []):
        person["bunqme_url"] = urls.get(person["name"])
        if person["bunqme_url"]:
            person["payment_status"] = "link_created"
    return split_dict
