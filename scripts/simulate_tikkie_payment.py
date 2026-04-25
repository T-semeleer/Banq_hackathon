"""
Simulate a Tikkie repayment using the bunq sandbox.

In the bunq sandbox, a request-inquiry sent to sugardaddy@bunq.com is
auto-accepted instantly, producing an incoming payment that the reconciler
can match.  This script simulates one or all people from the last split
paying you back.

Usage:
    python scripts/simulate_tikkie_payment.py --person "Sarah" --amount 13.31
    python scripts/simulate_tikkie_payment.py --all --split-file last_split.json
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_ROOT = Path(__file__).resolve().parents[1]
_TOOLKIT_DIR = _ROOT / "hackathon_toolkit-main"
sys.path.insert(0, str(_TOOLKIT_DIR))

from bunq_client import BunqClient  # noqa: E402

_SELF_NAMES = {"you", "me", "i"}


def simulate_payment(
    client: BunqClient,
    account_id: int,
    person_name: str,
    amount: float,
) -> dict:
    """
    Request money from sugardaddy@bunq.com to simulate receiving a Tikkie.
    The description encodes the person's name for reconciler matching.
    """
    description = f"Tikkie repayment — {person_name}"
    resp = client.post(
        f"user/{client.user_id}/monetary-account/{account_id}/request-inquiry",
        {
            "amount_inquired": {"value": f"{amount:.2f}", "currency": "EUR"},
            "counterparty_alias": {
                "type": "EMAIL",
                "value": "sugardaddy@bunq.com",
                "name": "Sugar Daddy",
            },
            "description": description,
            "allow_bunqme": False,
        },
    )
    request_id = resp[0]["Id"]["id"]
    return {
        "request_id": request_id,
        "person": person_name,
        "amount": amount,
        "description": description,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate Tikkie repayments in bunq sandbox")
    parser.add_argument("--person", help="Person name to simulate paying back")
    parser.add_argument("--amount", type=float, help="Amount in EUR")
    parser.add_argument("--all", dest="simulate_all", action="store_true",
                        help="Simulate all non-self people from split file")
    parser.add_argument("--split-file", default="last_split.json",
                        help="JSON file with split result (default: last_split.json)")
    args = parser.parse_args()

    api_key = os.getenv("BUNQ_API_KEY", "").strip()
    if not api_key:
        print("No BUNQ_API_KEY found — creating sandbox user...")
        api_key = BunqClient.create_sandbox_user()
        print(f"  Created: {api_key}\n")

    client = BunqClient(api_key=api_key, sandbox=True)
    client.authenticate()
    account_id = client.get_primary_account_id()
    print(f"Authenticated — user {client.user_id}, account {account_id}\n")

    to_simulate: list[tuple[str, float]] = []

    if args.simulate_all:
        split_path = Path(args.split_file)
        if not split_path.exists():
            split_path = _ROOT / args.split_file
        if not split_path.exists():
            print(f"Error: split file '{args.split_file}' not found. Run a split first.")
            sys.exit(1)
        with open(split_path) as f:
            data = json.load(f)
        for person in data.get("people", []):
            if person["name"].lower() not in _SELF_NAMES and person.get("total_owed", 0) > 0:
                to_simulate.append((person["name"], person["total_owed"]))
    elif args.person and args.amount is not None:
        to_simulate.append((args.person, args.amount))
    else:
        parser.error("Provide --person NAME --amount X.XX  or  --all")

    results = []
    for name, amount in to_simulate:
        print(f"  Simulating €{amount:.2f} repayment from {name}...")
        result = simulate_payment(client, account_id, name, amount)
        results.append(result)
        print(f"    Request #{result['request_id']} — \"{result['description']}\"")
        time.sleep(0.5)

    print(f"\nSimulated {len(results)} payment(s).")
    print("Wait a moment, then check status with: GET /api/reconcile")


if __name__ == "__main__":
    main()
