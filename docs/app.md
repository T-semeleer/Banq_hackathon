# Flask App — SplitBill

## Overview

`src/app.py` is the unified Flask backend for SplitBill. It wires together OCR, voice transcription, bill splitting, bunq payment links, reconciliation, and Tikkie simulation into a single server running on port 5000.

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

## Session State

All route handlers share a module-level dict:

```python
_state = {
    "split_result": None,   # SplitResult dataclass from matcher.py
    "split_dict":   None,   # plain dict from result_to_dict()
    "bunq_client":  None,   # authenticated BunqClient (cached)
    "account_id":   None,   # int — primary bunq account ID (cached)
}
```

State is reset on process restart. Sufficient for single-session hackathon demos.

---

## Routes

### `GET /`

Serves the single-page UI from `src/templates/index.html`.

**Response:** HTML

---

### `POST /api/transcribe`

Transcribes a voice recording using OpenAI Whisper.

**Request:** `multipart/form-data`

| Field | Type | Description |
|---|---|---|
| `audio` | file | Audio file (WebM, OGG, MP4, WAV) |

**Response:**

```json
{"transcript": "I had the chicken, Sarah had the salad."}
```

**Error codes:**

| Code | Reason |
|---|---|
| 400 | No audio file provided |
| 400 | Empty audio file |
| 501 | `OPENAI_API_KEY` not configured |
| 500 | Whisper API error |

---

### `POST /api/ocr`

Extracts receipt items from an image using AWS Textract.

**Request:** `multipart/form-data`

| Field | Type | Description |
|---|---|---|
| `image` | file | Receipt photo (JPEG, PNG, WebP) |

**Response:**

```json
{
  "ocr_text": "Grilled Chicken                          14.50\n...",
  "vendor": "De Silveren Spiegel",
  "items": [{"name": "Grilled Chicken", "price": 14.50}],
  "total": 46.87,
  "tax": 3.87,
  "image_url": "https://splitbill-receipts.s3.amazonaws.com/receipts/..."
}
```

**Error codes:**

| Code | Reason |
|---|---|
| 400 | No image file provided |
| 501 | AWS credentials not configured |
| 500 | Textract or S3 error |

---

### `POST /api/split`

Splits the bill using Claude Sonnet. Stores result in `_state` and writes `last_split.json`.

**Request:** `application/json`

```json
{
  "ocr_text": "Grilled Chicken 14.50\nTotal 46.87",
  "transcript": "I had the chicken, Sarah had the salad."
}
```

**Response:** `result_to_dict()` shape — see `docs/matcher.md`.

**Error codes:**

| Code | Reason |
|---|---|
| 400 | `ocr_text` or `transcript` missing or blank |
| 500 | Claude API error or JSON parse failure |

**Side effect:** Writes `last_split.json` to the project root for use by `scripts/simulate_tikkie_payment.py`.

---

### `POST /api/links`

Creates one bunq.me payment link per person and injects them into `_state["split_dict"]`.

**Prerequisites:** `POST /api/split` must have been called first.

**Response:** Updated split dict with `bunqme_url` and `payment_status: "link_created"` per person.

**Error codes:**

| Code | Reason |
|---|---|
| 400 | No split result in state |
| 500 | bunq API error |

---

### `GET /api/reconcile`

Polls bunq transaction history and returns per-person paid/unpaid status.

**Prerequisites:** `POST /api/split` must have been called first.

**Response:**

```json
{
  "original_total": 46.87,
  "payments": [
    {
      "name": "Sarah",
      "amount_owed": 13.31,
      "paid": true,
      "paid_at": "2024-01-15T14:23:00.000Z",
      "transaction_id": 12345
    }
  ],
  "total_repaid": 13.31,
  "net_cost": 33.56,
  "remaining_owed": 0.0
}
```

**Error codes:**

| Code | Reason |
|---|---|
| 400 | No split result in state |
| 500 | bunq API error |

---

### `POST /api/simulate`

Simulates a Tikkie repayment via bunq sandbox request-inquiry.

**Request:** `application/json`

```json
{"person": "Sarah", "amount": 13.31}
```

**Response:**

```json
{"success": true, "request_id": 999, "person": "Sarah", "amount": 13.31}
```

**Error codes:**

| Code | Reason |
|---|---|
| 400 | `person` or `amount` missing |
| 400 | `person` is blank |
| 500 | bunq API error |

---

## bunq Authentication

`_get_bunq()` caches the client in `_state`:
1. Reads `BUNQ_API_KEY` from environment
2. If not set, calls `BunqClient.create_sandbox_user()` to create a fresh sandbox key
3. Calls `client.authenticate()` (installation → device-server → session-server)
4. Fetches and caches the primary account ID

Subsequent calls return the cached client — authentication happens at most once per process.

---

## Status

| Component | Status |
|---|---|
| Flask server setup | Done — `src/app.py` port 5000 |
| `/api/transcribe` | Done |
| `/api/ocr` | Done |
| `/api/split` | Done |
| `/api/links` | Done |
| `/api/reconcile` | Done |
| `/api/simulate` | Done |
| Single-page UI | Done — `src/templates/index.html` |
| Route tests | Done — `tests/test_app_routes.py` (28 tests) |
