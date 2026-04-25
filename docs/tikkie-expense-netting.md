# Tikkie Expense Netting

## Problem

When a user pays for a group dinner and receives Tikkie reimbursements, a naive
monthly summary inflates both sides of the ledger:

| Before this feature | After this feature |
|---|---|
| Food expense: **€57.48** | Food expense: **€57.48** (gross) |
| Income: **€43.50** | Reimbursements: **€43.50** (offset against expense) |
| Net: €13.98 ✓ | **Your cost: €13.98** ✓ |
| Income shown: €43.50 ✗ | Income shown: €0 ✓ |

The net is correct either way, but the gross figures are misleading. This feature
corrects that by linking Tikkie reimbursements back to the original expense.

---

## How It Works

### 1. User selects the original expense

Before splitting a bill, the user clicks **"Pick from Bunq"** in the Split card.
This calls `GET /api/recent-expenses` and shows the last 10 outgoing transactions.
The user selects the one that represents the dinner payment.

The selected bunq payment ID is stored in server-side state and saved into
`last_split.json` as `expense_transaction_id`.

### 2. Tikkies are tagged with the expense reference

When a Tikkie is simulated (or sent through the app), the description is encoded
with a structured reference:

```
SPLIT|TXN{expense_id}|{person}|{amount}

Example:
SPLIT|TXN26174613|Sarah|19.00
```

This description is written into the bunq `request-inquiry` object, and bunq
carries it through to the resulting incoming payment when the request is accepted.

Tikkies created **without** a linked expense fall back to the old format
(`Tikkie repayment — {name}`) and continue to work for reconciliation but are
not netted in the monthly summary.

### 3. Monthly summary nets the amounts

`GET /api/summary?month=YYYY-MM` calls `summarize_month()` which:

1. Fetches all payments for the month (paginates with `older_id`)
2. Classifies each payment:
   - **Negative value** → expense
   - **Positive value + SPLIT|TXN match** → Tikkie reimbursement
   - **Positive value, no match** → other income (salary, transfers, etc.)
3. For each Tikkie reimbursement, subtracts it from the referenced expense's
   `net_personal_amount`
4. Returns expenses, income, and totals separately

Tikkie reimbursements **never appear in the income section**.

---

## New API Endpoints

### `GET /api/recent-expenses`

Returns the last 10 outgoing payments from the bunq account for the user to
identify the expense being split.

**Response:**
```json
[
  {
    "id": 26174613,
    "amount": 57.48,
    "description": "Restaurant De Keuken",
    "date": "2026-04-15",
    "counterparty": "De Keuken"
  }
]
```

### `GET /api/summary?month=YYYY-MM`

Returns the monthly expense summary with Tikkie reimbursements netted out.
Defaults to the current month if `month` is omitted or invalid.

**Response:**
```json
{
  "period": "2026-04",
  "expenses": [
    {
      "transaction_id": 26174613,
      "description": "Restaurant De Keuken",
      "gross_amount": 57.48,
      "reimbursements": [
        {"transaction_id": 45001, "from": "Sarah", "amount": 19.00},
        {"transaction_id": 45002, "from": "Mark", "amount": 24.50}
      ],
      "net_personal_amount": 13.98,
      "date": "2026-04-15",
      "type": "BUNQ"
    }
  ],
  "income": [
    {"transaction_id": 99001, "description": "Salary", "amount": 3000.00, "date": "2026-04-25"}
  ],
  "unmatched_tikkies": [],
  "totals": {
    "gross_expenses": 57.48,
    "tikkie_reimbursements_received": 43.50,
    "net_personal_expenses": 13.98,
    "other_income": 3000.00
  }
}
```

`unmatched_tikkies` contains any `SPLIT|TXN{id}` payments where the referenced
expense ID was not found in the same month (e.g. the original dinner was in a
previous month).

### `POST /api/split` — updated

Now accepts an optional `expense_transaction_id` field in the request body.
When provided, it is stored in server state and saved to `last_split.json`.

```json
{
  "ocr_text": "...",
  "transcript": "...",
  "expense_transaction_id": 26174613
}
```

---

## Changed Files

| File | Change |
|---|---|
| `src/summarizer.py` | **New.** Core netting logic and payment fetching |
| `src/app.py` | Added `/api/recent-expenses`, `/api/summary`; updated `/api/split` and `/api/simulate` |
| `src/templates/index.html` | Added expense picker (Step 3) and monthly summary (Step 6) |
| `scripts/simulate_tikkie_payment.py` | Reads `expense_transaction_id` from split file; new `--expense-txn-id` CLI arg |
| `tests/test_summarizer.py` | **New.** 11 unit tests for netting logic |

---

## Scope and Limitations

- **Only works for Tikkies created through this app.** Reimbursements sent via
  the standalone Tikkie app (not through bunq's request-inquiry API) will not
  carry the `SPLIT|TXN` reference and will not be netted. They appear in
  `unmatched_tikkies` if they happen to use the pattern, or in `income` otherwise.

- **The expense must be in the same calendar month** as the reimbursements for
  automatic netting. Cross-month cases land in `unmatched_tikkies`.

- **One expense per split.** Each split links to a single outgoing transaction.
  Multiple splits against the same expense are not yet supported.
