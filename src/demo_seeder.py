"""
Demo transaction seeder.

Creates realistic outgoing expense payments in the bunq sandbox and assigns
spending categories locally so /api/insights returns meaningful breakdowns
without needing Tapix (which is production-only).

Call seed_demo() once via POST /api/demo/setup before running the demo flow.
"""
import sys
import time
from pathlib import Path

_TOOLKIT_DIR = Path(__file__).resolve().parents[1] / "hackathon_toolkit-main"
if str(_TOOLKIT_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLKIT_DIR))

from bunq_client import BunqClient  # noqa: E402
from category_store import assign as _assign  # noqa: E402

# Six realistic Dutch expenses that cover distinct spending categories.
# The first one (Restaurant De Halve Maan) is the one the demo splits.
DEMO_EXPENSES: list[dict] = [
    {
        "description": "Restaurant De Halve Maan",
        "amount": "78.40",
        "category": "FOOD_AND_DRINK",
        "label": "Group dinner — this is the one you split",
    },
    {
        "description": "Albert Heijn Boodschappen",
        "amount": "34.20",
        "category": "GROCERIES",
        "label": "Shared groceries",
    },
    {
        "description": "NS Trein Amsterdam CS",
        "amount": "12.60",
        "category": "TRANSPORT",
        "label": "Train tickets",
    },
    {
        "description": "Pathé City Amsterdam",
        "amount": "23.50",
        "category": "ENTERTAINMENT",
        "label": "Cinema night",
    },
    {
        "description": "Etos Drogisterij",
        "amount": "15.90",
        "category": "HEALTH_AND_BEAUTY",
        "label": "Pharmacy run",
    },
    {
        "description": "Vodafone Maandelijks Abonnement",
        "amount": "29.99",
        "category": "BILLS_AND_UTILITIES",
        "label": "Phone bill",
    },
]


def seed_demo(client: BunqClient, account_id: int) -> list[dict]:
    """
    Seed sandbox with realistic expense transactions.

    Steps:
      1. Requests €500 from Sugar Daddy to fund the account.
      2. Makes one outgoing payment per demo expense.
      3. Stores category assignments in category_map.json for the insights overlay.

    Returns the list of seeded transactions (id, description, amount, category).
    """
    client.add_funds(account_id, "500.00")
    time.sleep(1)  # allow sandbox to process the funding

    seeded: list[dict] = []
    for expense in DEMO_EXPENSES:
        txn_id = client.make_payment(account_id, expense["amount"], expense["description"])
        _assign(txn_id, expense["category"])
        seeded.append({
            "id": txn_id,
            "description": expense["description"],
            "amount": float(expense["amount"]),
            "category": expense["category"],
            "label": expense["label"],
        })
        time.sleep(0.3)  # brief pause to let sandbox sequence the transactions

    return seeded
