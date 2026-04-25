"""
Demo transaction seeder.

Creates realistic outgoing expense payments in the bunq sandbox and assigns
spending categories locally so /api/insights returns meaningful breakdowns
without needing Tapix (which is production-only).

Two seeding modes:
  seed_demo()          — 6 preset Dutch expenses (Restaurant, AH, NS, Pathé, etc.)
  seed_from_receipts() — 5 expenses from the real test receipt images in test_receipts/
"""
import sys
import time
from pathlib import Path

_TOOLKIT_DIR = Path(__file__).resolve().parents[1] / "hackathon_toolkit-main"
if str(_TOOLKIT_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLKIT_DIR))

from bunq_client import BunqClient  # noqa: E402
from category_store import assign as _assign  # noqa: E402

# ── Hardcoded Dutch expenses ───────────────────────────────────────────────────

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
        "label": "Weekly groceries",
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
    {
        "description": "Jumbo Supermarkt",
        "amount": "41.75",
        "category": "GROCERIES",
        "label": "Mid-week groceries",
    },
    {
        "description": "GVB Maandkaart OV",
        "amount": "98.00",
        "category": "TRANSPORT",
        "label": "Monthly transit pass",
    },
    {
        "description": "Café Brouwerij 't IJ",
        "amount": "18.50",
        "category": "FOOD_AND_DRINK",
        "label": "Drinks with colleagues",
    },
    {
        "description": "Spotify Premium",
        "amount": "10.99",
        "category": "ENTERTAINMENT",
        "label": "Music subscription",
    },
    {
        "description": "H&M Amsterdam",
        "amount": "54.95",
        "category": "SHOPPING",
        "label": "Clothing",
    },
    {
        "description": "Thuisbezorgd.nl",
        "amount": "32.80",
        "category": "FOOD_AND_DRINK",
        "label": "Takeaway delivery",
    },
    {
        "description": "Eneco Energie",
        "amount": "87.50",
        "category": "BILLS_AND_UTILITIES",
        "label": "Energy bill",
    },
    {
        "description": "Coolblue",
        "amount": "149.00",
        "category": "SHOPPING",
        "label": "Electronics",
    },
    {
        "description": "Bagels & Beans",
        "amount": "11.40",
        "category": "FOOD_AND_DRINK",
        "label": "Lunch",
    },
]

# ── Receipt fixtures (extracted from test_receipts/*.jpg) ──────────────────────
# Each entry contains the full parsed receipt data plus pre-formatted ocr_text
# ready to pass directly to POST /api/split.

RECEIPT_FIXTURES: list[dict] = [
    {
        "file": "receipt_1.jpg",
        "vendor": "Green Supermarket",
        "category": "GROCERIES",
        "total": 27.35,
        "tax": None,
        "items": [
            {"name": "Apple (x2)", "price": 1.00},
            {"name": "Banana (x3)", "price": 1.50},
            {"name": "Orange (x2)", "price": 1.20},
            {"name": "Pear", "price": 0.75},
            {"name": "Grapes (x2)", "price": 3.00},
            {"name": "Strawberry", "price": 2.50},
            {"name": "Blueberry", "price": 2.00},
            {"name": "Kiwi (x2)", "price": 1.80},
            {"name": "Watermelon", "price": 4.50},
            {"name": "Lemon", "price": 0.60},
            {"name": "Raspberry", "price": 3.00},
            {"name": "Milk", "price": 1.50},
            {"name": "Cheese", "price": 2.80},
            {"name": "Yogurt", "price": 1.20},
        ],
        "ocr_text": (
            "Green Supermarket\n"
            "Apple (x2)                               1.00\n"
            "Banana (x3)                              1.50\n"
            "Orange (x2)                              1.20\n"
            "Pear                                     0.75\n"
            "Grapes (x2)                              3.00\n"
            "Strawberry                               2.50\n"
            "Blueberry                                2.00\n"
            "Kiwi (x2)                                1.80\n"
            "Watermelon                               4.50\n"
            "Lemon                                    0.60\n"
            "Raspberry                                3.00\n"
            "Milk                                     1.50\n"
            "Cheese                                   2.80\n"
            "Yogurt                                   1.20\n"
            "Total                                   27.35\n"
        ),
    },
    {
        "file": "receipt_2.jpg",
        "vendor": "McDonald's Alicante",
        "category": "FOOD_AND_DRINK",
        "total": 1.80,
        "tax": 0.16,
        "items": [
            {"name": "McPop Nocilla", "price": 1.00},
            {"name": "Cafe con Leche PQ", "price": 0.64},
        ],
        "ocr_text": (
            "McDonald's Alicante\n"
            "McPop Nocilla                            1.00\n"
            "Cafe con Leche PQ                        0.64\n"
            "IVA (10%)                                0.16\n"
            "Total                                    1.80\n"
        ),
    },
    {
        "file": "receipt_3.jpg",
        "vendor": "Food Lion",
        "category": "GROCERIES",
        "total": 19.55,
        "tax": 0.61,
        "items": [
            {"name": "FL 2% Reduced Fat Milk", "price": 1.69},
            {"name": "Kraft Shredded Mild Cheddar", "price": 3.68},
            {"name": "Kraft Whole Milk Mozzarella", "price": 3.68},
            {"name": "FL White Sandwich Bread", "price": 2.39},
            {"name": "Chips Ahoy Original", "price": 5.19},
            {"name": "FL Hickory Smoked Ham Steak", "price": 2.68},
        ],
        "ocr_text": (
            "Food Lion\n"
            "FL 2% Reduced Fat Milk                   1.69\n"
            "Kraft Shredded Mild Cheddar              3.68\n"
            "Kraft Whole Milk Mozzarella              3.68\n"
            "FL White Sandwich Bread                  2.39\n"
            "Chips Ahoy Original                      5.19\n"
            "FL Hickory Smoked Ham Steak              2.68\n"
            "Tax                                      0.61\n"
            "Total                                   19.55\n"
        ),
    },
    {
        "file": "receipt_4.jpg",
        "vendor": "No Frills",
        "category": "GROCERIES",
        "total": 51.38,
        "tax": 0.45,
        "items": [
            {"name": "Classic Sauce Rosee", "price": 3.27},
            {"name": "Lays Magic Masala", "price": 3.99},
            {"name": "Lays Tomato Tandoori", "price": 3.99},
            {"name": "Kraft Dinner Original", "price": 3.18},
            {"name": "Beatrice Homo Milk", "price": 12.36},
            {"name": "Strawberries", "price": 4.00},
            {"name": "Green Seedless Grapes", "price": 10.64},
            {"name": "Strawberries 1LB", "price": 2.94},
            {"name": "Baguette White (x3)", "price": 2.97},
            {"name": "Baguette Wheat (x2)", "price": 1.98},
            {"name": "Reusable Shopping Bag", "price": 0.99},
        ],
        "ocr_text": (
            "No Frills\n"
            "Classic Sauce Rosee                      3.27\n"
            "Lays Magic Masala                        3.99\n"
            "Lays Tomato Tandoori                     3.99\n"
            "Kraft Dinner Original                    3.18\n"
            "Beatrice Homo Milk                      12.36\n"
            "Strawberries                             4.00\n"
            "Green Seedless Grapes                   10.64\n"
            "Strawberries 1LB                         2.94\n"
            "Baguette White (x3)                      2.97\n"
            "Baguette Wheat (x2)                      1.98\n"
            "Reusable Shopping Bag                    0.99\n"
            "GST                                      0.45\n"
            "Total                                   51.38\n"
        ),
    },
    {
        "file": "receipt_5.jpg",
        "vendor": "Floor & Decor",
        "category": "SHOPPING",
        "total": 592.27,
        "tax": 45.14,
        "items": [
            {"name": "Quadec 3/8 Matte White 10FT", "price": 42.69},
            {"name": "Flexcolor CQ Grout 1GAL", "price": 54.94},
            {"name": "GLA Pure Snow 2x6 Brick (x50)", "price": 449.50},
        ],
        "ocr_text": (
            "Floor & Decor\n"
            "Quadec 3/8 Matte White 10FT             42.69\n"
            "Flexcolor CQ Grout 1GAL                 54.94\n"
            "GLA Pure Snow 2x6 Brick (x50)          449.50\n"
            "Sales Tax                               45.14\n"
            "Grand Total                            592.27\n"
        ),
    },
]


# ── Seeding functions ──────────────────────────────────────────────────────────

def seed_demo(client: BunqClient, account_id: int) -> list[dict]:
    """
    Seed sandbox with 6 preset Dutch expense transactions.

    Steps:
      1. Requests €500 from Sugar Daddy to fund the account.
      2. Makes one outgoing payment per expense.
      3. Stores category assignments in category_map.json for the insights overlay.

    Returns the list of seeded transaction dicts.
    """
    client.add_funds(account_id, "500.00")
    time.sleep(1)

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
        time.sleep(0.3)

    return seeded


def seed_from_receipts(client: BunqClient, account_id: int) -> list[dict]:
    """
    Seed sandbox with 5 expenses derived from the test receipt images.

    Each receipt's actual total becomes the payment amount. The full receipt
    data (items, ocr_text) is returned so the frontend can display the receipt
    and pass ocr_text straight into POST /api/split.

    Steps:
      1. Calculates total spend across all receipts + €100 buffer, requests that
         from Sugar Daddy to fund the account.
      2. Makes one outgoing payment per receipt.
      3. Stores category assignments in category_map.json.

    Returns enriched receipt dicts including the bunq transaction ID.
    """
    total_needed = sum(r["total"] for r in RECEIPT_FIXTURES) + 100.0
    client.add_funds(account_id, f"{total_needed:.2f}")
    time.sleep(1)

    seeded: list[dict] = []
    for receipt in RECEIPT_FIXTURES:
        txn_id = client.make_payment(
            account_id,
            f"{receipt['total']:.2f}",
            receipt["vendor"],
        )
        _assign(txn_id, receipt["category"])
        seeded.append({
            "id": txn_id,
            "file": receipt["file"],
            "vendor": receipt["vendor"],
            "amount": receipt["total"],
            "tax": receipt["tax"],
            "category": receipt["category"],
            "items": receipt["items"],
            "ocr_text": receipt["ocr_text"],
            "label": f"{receipt['vendor']} — {receipt['total']:.2f}",
        })
        time.sleep(0.3)

    return seeded
