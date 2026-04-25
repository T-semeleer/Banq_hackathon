"""
Example API responses for the full demo flow.

Shows exactly what each endpoint returns, using receipt_4.jpg (No Frills, €51.38)
as the split expense and two people (Alice, Bob) sharing it with you.

Useful as:
  - Reference for frontend integration
  - Copy-paste fixtures for new unit tests
  - Quick sanity-check of expected data shapes

Flow order:
  1.  POST /api/demo/setup {"source":"receipts"}   → DEMO_SETUP_RESPONSE
  2.  GET  /api/demo/receipts                       → DEMO_RECEIPTS_RESPONSE
  3.  GET  /api/recent-expenses                     → RECENT_EXPENSES_RESPONSE
  4.  POST /api/split                               → SPLIT_RESPONSE
  5.  POST /api/links                               → LINKS_RESPONSE
  6.  POST /api/demo/simulate-all                   → SIMULATE_ALL_RESPONSE
  7.  GET  /api/reconcile  (partial)                → RECONCILE_PARTIAL_RESPONSE
  8.  GET  /api/reconcile  (fully paid)             → RECONCILE_PAID_RESPONSE
  9.  GET  /api/insights                            → INSIGHTS_RESPONSE
  10. GET  /api/summary                             → SUMMARY_RESPONSE
  11. GET  /api/events                              → EVENTS_RESPONSE
  12. GET  /api/insights/categories                 → CATEGORIES_RESPONSE
"""

# ── 1. POST /api/demo/setup {"source":"receipts"} ─────────────────────────────

DEMO_SETUP_RESPONSE = {
    "source": "receipts",
    "count": 5,
    "seeded": [
        {
            "id": 10001,
            "file": "receipt_1.jpg",
            "vendor": "Green Supermarket",
            "amount": 27.35,
            "tax": None,
            "category": "GROCERIES",
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
            "label": "Green Supermarket — 27.35",
        },
        {
            "id": 10002,
            "file": "receipt_2.jpg",
            "vendor": "McDonald's Alicante",
            "amount": 1.80,
            "tax": 0.16,
            "category": "FOOD_AND_DRINK",
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
            "label": "McDonald's Alicante — 1.80",
        },
        {
            "id": 10003,
            "file": "receipt_3.jpg",
            "vendor": "Food Lion",
            "amount": 19.55,
            "tax": 0.61,
            "category": "GROCERIES",
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
            "label": "Food Lion — 19.55",
        },
        {
            "id": 10004,
            "file": "receipt_4.jpg",
            "vendor": "No Frills",
            "amount": 51.38,
            "tax": 0.45,
            "category": "GROCERIES",
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
            "label": "No Frills — 51.38",
        },
        {
            "id": 10005,
            "file": "receipt_5.jpg",
            "vendor": "Floor & Decor",
            "amount": 592.27,
            "tax": 45.14,
            "category": "SHOPPING",
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
            "label": "Floor & Decor — 592.27",
        },
    ],
    "tip": (
        "Browse receipts at GET /api/demo/receipts. "
        "Pick any transaction from GET /api/recent-expenses, then "
        "POST /api/split with its ocr_text and expense_transaction_id."
    ),
}


# ── 2. GET /api/demo/receipts ─────────────────────────────────────────────────
# Same structure as seeded items above; transaction_id present because setup ran.

DEMO_RECEIPTS_RESPONSE = {
    "count": 5,
    "receipts": [
        {**entry, "transaction_id": entry["id"]}
        for entry in DEMO_SETUP_RESPONSE["seeded"]
    ],
}


# ── 3. GET /api/recent-expenses ───────────────────────────────────────────────
# Last 20 outgoing payments. The 5 receipt-based expenses appear at the top.

RECENT_EXPENSES_RESPONSE = [
    {
        "id": 10005,
        "amount": 592.27,
        "description": "Floor & Decor",
        "date": "2026-04-25",
        "counterparty": "Sugar Daddy",
        "category": "SHOPPING",
    },
    {
        "id": 10004,
        "amount": 51.38,
        "description": "No Frills",
        "date": "2026-04-25",
        "counterparty": "Sugar Daddy",
        "category": "GROCERIES",
    },
    {
        "id": 10003,
        "amount": 19.55,
        "description": "Food Lion",
        "date": "2026-04-25",
        "counterparty": "Sugar Daddy",
        "category": "GROCERIES",
    },
    {
        "id": 10002,
        "amount": 1.80,
        "description": "McDonald's Alicante",
        "date": "2026-04-25",
        "counterparty": "Sugar Daddy",
        "category": "FOOD_AND_DRINK",
    },
    {
        "id": 10001,
        "amount": 27.35,
        "description": "Green Supermarket",
        "date": "2026-04-25",
        "counterparty": "Sugar Daddy",
        "category": "GROCERIES",
    },
]


# ── 4. POST /api/split ────────────────────────────────────────────────────────
# Splitting the No Frills receipt (€51.38) three ways.
# Transcript: "I got the milk and grapes. Alice took the chips and bread.
#              Bob grabbed the sauce, masala, and baguettes."
# expense_transaction_id: 10004

SPLIT_RESPONSE = {
    "status": "review",
    "total": 51.38,
    "tax": 0.45,
    "tip": 0.0,
    "expense_transaction_id": 10004,
    "people": [
        {
            "name": "You",
            "items": [
                {"name": "Beatrice Homo Milk", "price": 12.36},
                {"name": "Green Seedless Grapes", "price": 10.64},
                {"name": "Strawberries 1LB", "price": 2.94},
            ],
            "subtotal": 25.94,
            "tax_share": 0.23,
            "tip_share": 0.0,
            "total_owed": 26.17,
            "bunqme_url": None,
            "payment_status": "pending",
        },
        {
            "name": "Alice",
            "items": [
                {"name": "Chips Ahoy Original", "price": 5.19},
                {"name": "FL White Sandwich Bread", "price": 2.39},
                {"name": "Strawberries", "price": 4.00},
            ],
            "subtotal": 11.58,
            "tax_share": 0.10,
            "tip_share": 0.0,
            "total_owed": 11.68,
            "bunqme_url": None,
            "payment_status": "pending",
        },
        {
            "name": "Bob",
            "items": [
                {"name": "Classic Sauce Rosee", "price": 3.27},
                {"name": "Lays Magic Masala", "price": 3.99},
                {"name": "Lays Tomato Tandoori", "price": 3.99},
                {"name": "Kraft Dinner Original", "price": 3.18},
                {"name": "Baguette White (x3)", "price": 2.97},
                {"name": "Baguette Wheat (x2)", "price": 1.98},
                {"name": "Reusable Shopping Bag", "price": 0.99},
            ],
            "subtotal": 20.37,
            "tax_share": 0.18,
            "tip_share": 0.0,
            "total_owed": 20.55,
            "bunqme_url": None,
            "payment_status": "pending",
        },
    ],
    "unassigned": [],
}


# ── 5. POST /api/links ────────────────────────────────────────────────────────
# Same shape as SPLIT_RESPONSE but with bunqme_url + payment_status filled in.

LINKS_RESPONSE = {
    **SPLIT_RESPONSE,
    "people": [
        {**SPLIT_RESPONSE["people"][0], "bunqme_url": None},  # "You" — no link needed
        {
            **SPLIT_RESPONSE["people"][1],
            "bunqme_url": "https://bunq.me/splitbill/alice-11.68-abc123",
            "payment_status": "link_created",
        },
        {
            **SPLIT_RESPONSE["people"][2],
            "bunqme_url": "https://bunq.me/splitbill/bob-20.55-def456",
            "payment_status": "link_created",
        },
    ],
}


# ── 6. POST /api/demo/simulate-all ────────────────────────────────────────────
# Simulates Tikkie repayments from Alice and Bob.

SIMULATE_ALL_RESPONSE = {
    "count": 2,
    "simulated": [
        {
            "person": "Alice",
            "amount": 11.68,
            "request_id": 20001,
            "description": "Tikkie from Alice — SPLIT|TXN10004|Alice|11.68",
            "status": "simulated",
        },
        {
            "person": "Bob",
            "amount": 20.55,
            "request_id": 20002,
            "description": "Tikkie from Bob — SPLIT|TXN10004|Bob|20.55",
            "status": "simulated",
        },
    ],
    "next": "Call GET /api/reconcile to see who has paid and your net cost.",
}


# ── 7. GET /api/reconcile — partially paid (only Alice has come through) ──────

RECONCILE_PARTIAL_RESPONSE = {
    "original_total": 51.38,
    "payments": [
        {
            "name": "Alice",
            "amount_owed": 11.68,
            "paid": True,
            "paid_at": "2026-04-25T14:31:02",
            "transaction_id": 30001,
        },
        {
            "name": "Bob",
            "amount_owed": 20.55,
            "paid": False,
            "paid_at": None,
            "transaction_id": None,
        },
    ],
    "total_repaid": 11.68,
    "net_cost": 39.70,
    "remaining_owed": 20.55,
    "summary_line": (
        "You paid €51.38. Received €11.68 so far. "
        "Your current net cost is €39.70 (€20.55 still outstanding)."
    ),
}


# ── 8. GET /api/reconcile — fully paid ────────────────────────────────────────

RECONCILE_PAID_RESPONSE = {
    "original_total": 51.38,
    "payments": [
        {
            "name": "Alice",
            "amount_owed": 11.68,
            "paid": True,
            "paid_at": "2026-04-25T14:31:02",
            "transaction_id": 30001,
        },
        {
            "name": "Bob",
            "amount_owed": 20.55,
            "paid": True,
            "paid_at": "2026-04-25T14:32:45",
            "transaction_id": 30002,
        },
    ],
    "total_repaid": 32.23,
    "net_cost": 19.15,
    "remaining_owed": 0.0,
    "summary_line": (
        "All repaid. You paid €51.38 total and received "
        "€32.23 back — your actual share was €19.15."
    ),
}


# ── 9. GET /api/insights?month=2026-04 ────────────────────────────────────────
# Sandbox overlay: computed from raw payments + category_map.json.

INSIGHTS_RESPONSE = {
    "period": "2026-04",
    "source": "sandbox_overlay",
    "currency": "EUR",
    "total_spend": 692.35,
    "categories": [
        {
            "category": "SHOPPING",
            "category_translated": "Shopping",
            "color": "#9C27B0",
            "icon": "shopping",
            "amount_total": {"value": "592.27", "currency": "EUR"},
            "number_of_transactions": 1,
        },
        {
            "category": "GROCERIES",
            "category_translated": "Groceries",
            "color": "#4CAF50",
            "icon": "groceries",
            "amount_total": {"value": "98.28", "currency": "EUR"},
            "number_of_transactions": 3,
        },
        {
            "category": "FOOD_AND_DRINK",
            "category_translated": "Food & Drink",
            "color": "#FF6B35",
            "icon": "food_and_drink",
            "amount_total": {"value": "1.80", "currency": "EUR"},
            "number_of_transactions": 1,
        },
    ],
}


# ── 10. GET /api/summary?month=2026-04 ────────────────────────────────────────
# Monthly netting: No Frills expense with Alice + Bob Tikkies matched.

SUMMARY_RESPONSE = {
    "period": "2026-04",
    "totals": {
        "gross_expenses": 692.35,
        "tikkie_reimbursements_received": 32.23,
        "net_personal_expenses": 660.12,
        "other_income": 0.0,
    },
    "expenses": [
        {
            "transaction_id": 10005,
            "description": "Floor & Decor",
            "gross_amount": 592.27,
            "reimbursements": [],
            "net_personal_amount": 592.27,
            "date": "2026-04-25",
            "type": "BUNQ",
        },
        {
            "transaction_id": 10004,
            "description": "No Frills",
            "gross_amount": 51.38,
            "reimbursements": [
                {"transaction_id": 30001, "from": "Alice", "amount": 11.68},
                {"transaction_id": 30002, "from": "Bob", "amount": 20.55},
            ],
            "net_personal_amount": 19.15,
            "date": "2026-04-25",
            "type": "BUNQ",
        },
        {
            "transaction_id": 10003,
            "description": "Food Lion",
            "gross_amount": 19.55,
            "reimbursements": [],
            "net_personal_amount": 19.55,
            "date": "2026-04-25",
            "type": "BUNQ",
        },
        {
            "transaction_id": 10001,
            "description": "Green Supermarket",
            "gross_amount": 27.35,
            "reimbursements": [],
            "net_personal_amount": 27.35,
            "date": "2026-04-25",
            "type": "BUNQ",
        },
        {
            "transaction_id": 10002,
            "description": "McDonald's Alicante",
            "gross_amount": 1.80,
            "reimbursements": [],
            "net_personal_amount": 1.80,
            "date": "2026-04-25",
            "type": "BUNQ",
        },
    ],
    "income": [],
    "unmatched_tikkies": [],
}


# ── 11. GET /api/events?count=10 ─────────────────────────────────────────────
# Activity feed. Outgoing payments show their category. Incoming Tikkies show None.

EVENTS_RESPONSE = {
    "count": 7,
    "events": [
        {
            "id": 30002,
            "created": "2026-04-25T14:32:45",
            "action": "CREATE",
            "monetary_account_id": 99,
            "type": "Payment",
            "status": "FINALIZED",
            "category": None,
            "amount": 20.55,
            "currency": "EUR",
            "description": "Tikkie from Bob — SPLIT|TXN10004|Bob|20.55",
            "counterparty": "Sugar Daddy",
        },
        {
            "id": 30001,
            "created": "2026-04-25T14:31:02",
            "action": "CREATE",
            "monetary_account_id": 99,
            "type": "Payment",
            "status": "FINALIZED",
            "category": None,
            "amount": 11.68,
            "currency": "EUR",
            "description": "Tikkie from Alice — SPLIT|TXN10004|Alice|11.68",
            "counterparty": "Sugar Daddy",
        },
        {
            "id": 10005,
            "created": "2026-04-25T14:05:12",
            "action": "CREATE",
            "monetary_account_id": 99,
            "type": "Payment",
            "status": "FINALIZED",
            "category": "SHOPPING",
            "amount": -592.27,
            "currency": "EUR",
            "description": "Floor & Decor",
            "counterparty": "Sugar Daddy",
        },
        {
            "id": 10004,
            "created": "2026-04-25T14:04:58",
            "action": "CREATE",
            "monetary_account_id": 99,
            "type": "Payment",
            "status": "FINALIZED",
            "category": "GROCERIES",
            "amount": -51.38,
            "currency": "EUR",
            "description": "No Frills",
            "counterparty": "Sugar Daddy",
        },
        {
            "id": 10003,
            "created": "2026-04-25T14:04:44",
            "action": "CREATE",
            "monetary_account_id": 99,
            "type": "Payment",
            "status": "FINALIZED",
            "category": "GROCERIES",
            "amount": -19.55,
            "currency": "EUR",
            "description": "Food Lion",
            "counterparty": "Sugar Daddy",
        },
        {
            "id": 10002,
            "created": "2026-04-25T14:04:30",
            "action": "CREATE",
            "monetary_account_id": 99,
            "type": "Payment",
            "status": "FINALIZED",
            "category": "FOOD_AND_DRINK",
            "amount": -1.80,
            "currency": "EUR",
            "description": "McDonald's Alicante",
            "counterparty": "Sugar Daddy",
        },
        {
            "id": 10001,
            "created": "2026-04-25T14:04:16",
            "action": "CREATE",
            "monetary_account_id": 99,
            "type": "Payment",
            "status": "FINALIZED",
            "category": "GROCERIES",
            "amount": -27.35,
            "currency": "EUR",
            "description": "Green Supermarket",
            "counterparty": "Sugar Daddy",
        },
    ],
}


# ── 12. GET /api/insights/categories ─────────────────────────────────────────

CATEGORIES_RESPONSE = {
    "categories": [
        {"category": "FOOD_AND_DRINK",        "type": "SYSTEM", "description": "Food and Drink",        "description_translated": "Food & Drink",        "color": "#FF6B35", "icon": "food_and_drink",        "order": 1},
        {"category": "GROCERIES",             "type": "SYSTEM", "description": "Groceries",             "description_translated": "Groceries",           "color": "#4CAF50", "icon": "groceries",             "order": 2},
        {"category": "SHOPPING",              "type": "SYSTEM", "description": "Shopping",              "description_translated": "Shopping",            "color": "#9C27B0", "icon": "shopping",              "order": 3},
        {"category": "TRANSPORT",             "type": "SYSTEM", "description": "Transport",             "description_translated": "Transport",           "color": "#2196F3", "icon": "transport",             "order": 4},
        {"category": "TRAVEL",                "type": "SYSTEM", "description": "Travel",                "description_translated": "Travel",              "color": "#00BCD4", "icon": "travel",                "order": 5},
        {"category": "HEALTH_AND_BEAUTY",     "type": "SYSTEM", "description": "Health and Beauty",     "description_translated": "Health & Beauty",     "color": "#E91E63", "icon": "health_and_beauty",     "order": 6},
        {"category": "ENTERTAINMENT",         "type": "SYSTEM", "description": "Entertainment",         "description_translated": "Entertainment",       "color": "#FF9800", "icon": "entertainment",         "order": 7},
        {"category": "BILLS_AND_UTILITIES",   "type": "SYSTEM", "description": "Bills and Utilities",   "description_translated": "Bills & Utilities",   "color": "#607D8B", "icon": "bills_and_utilities",   "order": 8},
        {"category": "HOUSING",               "type": "SYSTEM", "description": "Housing",               "description_translated": "Housing",             "color": "#795548", "icon": "housing",               "order": 9},
        {"category": "SAVINGS_AND_INVESTMENTS","type":"SYSTEM",  "description": "Savings and Investments","description_translated": "Savings & Investments","color": "#FFD700", "icon": "savings_and_investments","order": 10},
        {"category": "TRANSFERS",             "type": "SYSTEM", "description": "Transfers",             "description_translated": "Transfers",           "color": "#9E9E9E", "icon": "transfers",             "order": 11},
        {"category": "OTHER",                 "type": "SYSTEM", "description": "Other",                 "description_translated": "Other",               "color": "#757575", "icon": "other",                 "order": 12},
    ],
}


# ── Raw bunq payment API response shape ───────────────────────────────────────
# This is what client.get("user/{id}/monetary-account/{id}/payment") returns.
# Useful for building mocks in unit tests.

RAW_BUNQ_PAYMENT_OUTGOING = {
    "Payment": {
        "id": 10004,
        "created": "2026-04-25 14:04:58.000000",
        "updated": "2026-04-25 14:04:58.000000",
        "amount": {"value": "-51.38", "currency": "EUR"},
        "description": "No Frills",
        "type": "BUNQ",
        "merchant_reference": None,
        "alias": {
            "type": "IBAN",
            "value": "NL12BUNQ0123456789",
            "name": "Demo User",
        },
        "counterparty_alias": {
            "type": "EMAIL",
            "value": "sugardaddy@bunq.com",
            "name": "Sugar Daddy",
        },
        "attachment": [],
        "allow_chat": True,
        "monetary_account_id": 99,
    }
}

RAW_BUNQ_PAYMENT_INCOMING_TIKKIE = {
    "Payment": {
        "id": 30001,
        "created": "2026-04-25 14:31:02.000000",
        "updated": "2026-04-25 14:31:02.000000",
        "amount": {"value": "11.68", "currency": "EUR"},
        "description": "Tikkie from Alice — SPLIT|TXN10004|Alice|11.68",
        "type": "BUNQ",
        "merchant_reference": None,
        "alias": {
            "type": "IBAN",
            "value": "NL12BUNQ0123456789",
            "name": "Demo User",
        },
        "counterparty_alias": {
            "type": "EMAIL",
            "value": "sugardaddy@bunq.com",
            "name": "Sugar Daddy",
        },
        "attachment": [],
        "allow_chat": True,
        "monetary_account_id": 99,
    }
}
