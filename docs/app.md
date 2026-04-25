# Flask App — SplitBill API Reference

## Overview

`src/app.py` is the Flask backend for SplitBill. It wires together OCR, voice transcription, bill splitting, bunq payment links, reconciliation, Tikkie simulation, demo seeding, and Bunq native insights into a single server on port 5000.

---

## File

```
src/app.py
```

---

## Dependencies

```bash
pip install flask python-dotenv openai anthropic boto3
```

---

## Environment Variables

| Variable | Required | Used by |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Bill splitting (Claude Sonnet) |
| `OPENAI_API_KEY` | Yes | Voice transcription (Whisper) |
| `BUNQ_API_KEY` | No | bunq sandbox (auto-created if absent) |
| `AWS_ACCESS_KEY_ID` | No | OCR via Textract (disabled if absent) |
| `AWS_SECRET_ACCESS_KEY` | No | OCR via Textract |
| `S3_BUCKET` | No | OCR via Textract |

---

## Running

```bash
cd Banq_hackathon
python src/app.py
# → http://localhost:5000
```

---

## Demo Flow (End-to-End)

### Mode A — Hardcoded Dutch expenses
```
POST /api/demo/setup                          ← seeds 6 Dutch expenses + categories
GET  /api/recent-expenses                     ← pick "Restaurant De Halve Maan"
POST /api/split  {ocr_text, transcript, expense_transaction_id}
POST /api/links
POST /api/demo/simulate-all
GET  /api/reconcile                           ← summary_line: "your actual share was €X"
GET  /api/insights?month=YYYY-MM             ← category breakdown (sandbox overlay)
```

### Mode B — Real test receipt images
```
POST /api/demo/setup  {"source":"receipts"}  ← seeds 5 receipt-based expenses + categories
GET  /api/demo/receipts                       ← browse receipts, get ocr_text + transaction_id
POST /api/split  {ocr_text: receipt.ocr_text, transcript: "...", expense_transaction_id: receipt.transaction_id}
POST /api/links
POST /api/demo/simulate-all
GET  /api/reconcile
GET  /api/insights?month=YYYY-MM
```

---

## Session State

```python
_state = {
    "split_result": None,        # SplitResult dataclass from matcher.py
    "split_dict":   None,        # plain dict from result_to_dict()
    "bunq_client":  None,        # authenticated BunqClient (cached)
    "account_id":   None,        # int — primary bunq account ID (cached)
    "expense_transaction_id": None,  # outgoing payment being split
    "demo_expenses": None,       # list of seeded transactions from /api/demo/setup
}
```

State resets on process restart. Sufficient for single-session hackathon demos.

---

## Routes

### `GET /`

Serves the single-page UI from `src/templates/index.html`.

---

### `POST /api/demo/setup`

Seeds the sandbox with demo expense transactions and assigns spending categories locally so `/api/insights` returns real data (Tapix is production-only). Takes ~5 seconds.

**Body (optional):**

```json
{"source": "hardcoded"}
```

| `source` | Description |
|---|---|
| `"hardcoded"` (default) | 6 preset Dutch expenses: Restaurant De Halve Maan, Albert Heijn, NS Trein, Pathé, Etos, Vodafone |
| `"receipts"` | 5 expenses from the real test receipt images in `test_receipts/` — see table below |

**Receipt sources (`"receipts"` mode):**

| File | Vendor | Total | Category |
|---|---|---|---|
| receipt_1.jpg | Green Supermarket | €27.35 | GROCERIES |
| receipt_2.jpg | McDonald's Alicante | €1.80 | FOOD_AND_DRINK |
| receipt_3.jpg | Food Lion | €19.55 | GROCERIES |
| receipt_4.jpg | No Frills | €51.38 | GROCERIES |
| receipt_5.jpg | Floor & Decor | €592.27 | SHOPPING |

**Response (`"hardcoded"`):**

```json
{
  "source": "hardcoded",
  "seeded": [
    {"id": 12345, "description": "Restaurant De Halve Maan", "amount": 78.40, "category": "FOOD_AND_DRINK", "label": "Group dinner — this is the one you split"}
  ],
  "count": 6,
  "tip": "..."
}
```

**Response (`"receipts"`):**

```json
{
  "source": "receipts",
  "seeded": [
    {
      "id": 12346,
      "file": "receipt_1.jpg",
      "vendor": "Green Supermarket",
      "amount": 27.35,
      "tax": null,
      "category": "GROCERIES",
      "items": [{"name": "Apple (x2)", "price": 1.00}, "..."],
      "ocr_text": "Green Supermarket\nApple (x2)    1.00\n...",
      "label": "Green Supermarket — 27.35"
    }
  ],
  "count": 5,
  "tip": "..."
}
```

---

### `GET /api/demo/receipts`

Lists all 5 test receipt fixtures with their parsed line items and pre-formatted `ocr_text`.

If `POST /api/demo/setup {"source":"receipts"}` has been called, each receipt also includes its `transaction_id` so you can wire it directly into `POST /api/split`.

**Response:**

```json
{
  "receipts": [
    {
      "file": "receipt_1.jpg",
      "vendor": "Green Supermarket",
      "category": "GROCERIES",
      "total": 27.35,
      "tax": null,
      "items": [{"name": "Apple (x2)", "price": 1.00}, "..."],
      "ocr_text": "Green Supermarket\nApple (x2)    1.00\n...",
      "transaction_id": 12346
    }
  ],
  "count": 5
}
```

`transaction_id` is only present after `POST /api/demo/setup {"source":"receipts"}` has been called.

The `ocr_text` field can be passed directly to `POST /api/split` without any image upload or OCR step.

---

### `POST /api/demo/simulate-all`

Simulates Tikkie repayments from every person in the current split result in one call. Each request-inquiry is auto-accepted by Sugar Daddy in sandbox.

**Prerequisites:** `POST /api/split` must have been called first.

**Response:**

```json
{
  "simulated": [
    {
      "person": "Alice",
      "amount": 19.60,
      "request_id": 999,
      "description": "Tikkie from Alice — SPLIT|TXN12345|Alice|19.60",
      "status": "simulated"
    }
  ],
  "count": 2,
  "next": "Call GET /api/reconcile to see who has paid and your net cost."
}
```

---

### `POST /api/transcribe`

Transcribes a voice recording via OpenAI Whisper.

**Request:** `multipart/form-data` with `audio` file (WebM, OGG, MP4, WAV).

**Response:** `{"transcript": "I had the chicken, Sarah had the salad."}`

---

### `POST /api/ocr`

Extracts receipt items from an image via AWS Textract.

**Request:** `multipart/form-data` with `image` file (JPEG, PNG, WebP).

**Response:**

```json
{
  "ocr_text": "Grilled Chicken                          14.50\n...",
  "vendor": "De Silveren Spiegel",
  "items": [{"name": "Grilled Chicken", "price": 14.50}],
  "total": 46.87,
  "tax": 3.87
}
```

Disabled (501) if `AWS_ACCESS_KEY_ID` is not set.

---

### `POST /api/split`

Splits the bill using Claude Sonnet. Stores result in `_state` and writes `last_split.json`.

**Request:**

```json
{
  "ocr_text": "Grilled Chicken 14.50\nTotal 46.87",
  "transcript": "I had the chicken, Sarah had the salad.",
  "expense_transaction_id": 12345
}
```

`expense_transaction_id` is optional — set it to the bunq payment ID of the expense being split so Tikkie descriptions encode the reference for reconciliation.

**Response:** See `docs/matcher.md`.

---

### `POST /api/links`

Creates one bunq.me payment link per person and injects URLs into the split dict.

**Prerequisites:** `POST /api/split` must have been called first.

**Response:** Updated split dict with `bunqme_url` and `payment_status: "link_created"` per person.

---

### `GET /api/reconcile`

Polls recent bunq payments and matches them against the split result.

**Prerequisites:** `POST /api/split` must have been called first.

**Response:**

```json
{
  "original_total": 78.40,
  "payments": [
    {
      "name": "Alice",
      "amount_owed": 19.60,
      "paid": true,
      "paid_at": "2026-04-25T14:23:00",
      "transaction_id": 99901
    }
  ],
  "total_repaid": 39.20,
  "net_cost": 39.20,
  "remaining_owed": 0.0,
  "summary_line": "All repaid. You paid €78.40 total and received €39.20 back — your actual share was €39.20."
}
```

`summary_line` is the footnote: plain-English statement of your actual personal cost after Tikkie repayments.

---

### `GET /api/recent-expenses`

Returns the last 20 outgoing payments with spending category where known.

**Response:**

```json
[
  {
    "id": 12345,
    "amount": 78.40,
    "description": "Restaurant De Halve Maan",
    "date": "2026-04-25",
    "counterparty": "Sugar Daddy",
    "category": "FOOD_AND_DRINK"
  }
]
```

`category` is populated from the local store after `POST /api/demo/setup`. Null for transactions without a known category.

---

### `POST /api/simulate`

Simulates a single Tikkie repayment from one person.

**Request:** `{"person": "Alice", "amount": 19.60}`

**Response:**

```json
{
  "success": true,
  "request_id": 999,
  "person": "Alice",
  "amount": 19.60,
  "linked_expense_id": 12345
}
```

The simulated payment description is formatted as:
`"Tikkie from Alice — SPLIT|TXN12345|Alice|19.60"`

This matches how a real Tikkie repayment would look and is parseable by the reconciler.

---

### `GET /api/summary?month=YYYY-MM`

Monthly expense summary with Tikkie reimbursements netted against their originating expenses.

**Response:** See `docs/tikkie-expense-netting.md`.

---

### `GET /api/insights?month=YYYY-MM`

Bunq-native category spend breakdown for a month.

In **production**: powered by Tapix automatic categorisation.
In **sandbox**: automatically falls back to `build_sandbox_insights()` which computes the same breakdown from raw payments + `category_map.json` populated by `POST /api/demo/setup`.

**Response:**

```json
{
  "period": "2026-04",
  "categories": [
    {
      "category": "FOOD_AND_DRINK",
      "category_translated": "Food & Drink",
      "color": "#FF6B35",
      "icon": "food_and_drink",
      "amount_total": {"value": "78.40", "currency": "EUR"},
      "number_of_transactions": 1
    }
  ],
  "total_spend": 194.59,
  "currency": "EUR",
  "source": "sandbox_overlay"
}
```

`source` is `"tapix"` in production, `"sandbox_overlay"` in sandbox.

---

### `GET /api/insights/transactions?category=FOOD_AND_DRINK&month=YYYY-MM`

Individual transactions for a specific spending category via `/insights-search`.

**Response:**

```json
{
  "period": "2026-04",
  "category": "FOOD_AND_DRINK",
  "transactions": [...],
  "count": 1,
  "total": 78.40
}
```

---

### `GET /api/insights/categories`

Lists all available spending categories (system Tapix-assigned + user-defined).

**Response:** `{"categories": [{"category": "FOOD_AND_DRINK", "type": "SYSTEM", ...}]}`

---

### `GET /api/events?count=50`

Bunq activity event feed. Each event may carry a Tapix-assigned `category` field when enrichment is available.

**Response:**

```json
{
  "events": [
    {
      "id": 99901,
      "created": "2026-04-25T14:23:00",
      "action": "CREATE",
      "type": "Payment",
      "category": "FOOD_AND_DRINK",
      "amount": -78.40,
      "description": "Restaurant De Halve Maan",
      "counterparty": "Sugar Daddy",
      "status": "FINALIZED"
    }
  ],
  "count": 50
}
```

---

### `GET /api/insights/preference`

User's configured monthly insight period start day (e.g., the 25th if they're paid on the 25th).

---

## Persistent Files

| File | Contents |
|---|---|
| `bunq_context.json` | Cached OAuth tokens — reused across restarts |
| `last_split.json` | Latest split result — used by `scripts/simulate_tikkie_payment.py` |
| `category_map.json` | `{transaction_id: category}` — populated by `POST /api/demo/setup` |

---

## Status

| Component | Status |
|---|---|
| `/api/demo/setup` | Done — hardcoded (6 expenses) or receipts (5 real images) |
| `/api/demo/receipts` | Done — lists receipt fixtures with ocr_text + transaction_id |
| `/api/demo/simulate-all` | Done — bulk Tikkie simulation |
| `/api/transcribe` | Done |
| `/api/ocr` | Done |
| `/api/split` | Done |
| `/api/links` | Done |
| `/api/reconcile` | Done — includes `summary_line` footnote |
| `/api/recent-expenses` | Done — 20 transactions with category |
| `/api/simulate` | Done — realistic Tikkie description format |
| `/api/summary` | Done |
| `/api/insights` | Done — Tapix in prod, sandbox overlay in sandbox |
| `/api/insights/transactions` | Done |
| `/api/insights/categories` | Done |
| `/api/events` | Done |
| `/api/insights/preference` | Done |
