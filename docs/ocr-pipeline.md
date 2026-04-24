# OCR Pipeline — SplitBill

## Overview

The OCR pipeline converts a receipt photo into a structured list of line items and prices that the LLM matching step can use to assign costs to people.

**Two-step flow:**
1. **Upload** — Receipt image is stored in AWS S3
2. **Analyze** — AWS Textract `AnalyzeExpense` extracts items, prices, tax, and vendor

---

## File

```
src/ocr.py
```

---

## Dependencies

```bash
pip install boto3 python-dotenv
```

---

## Environment Variables

Add to `.env` (never commit this file):

```
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_SESSION_TOKEN=...          # required for temporary credentials
AWS_DEFAULT_REGION=us-east-1
S3_BUCKET=splitbill-receipts
```

---

## Public API

### `upload_to_s3(image_path) -> tuple[str, str]`

Uploads the receipt image to S3 under `receipts/<uuid>.<ext>`.

| Parameter | Type | Description |
|---|---|---|
| `image_path` | `Path \| str` | Local path to the receipt image |

**Returns:** `(s3_key, image_url)` — S3 object key and public HTTPS URL

---

### `analyze_receipt(s3_key) -> dict`

Calls Textract `AnalyzeExpense` on an already-uploaded S3 object.

| Parameter | Type | Description |
|---|---|---|
| `s3_key` | `str` | S3 object key returned by `upload_to_s3` |

**Returns:** raw Textract response dict (pass to `parse_response`)

---

### `parse_response(response, image_url) -> ReceiptResult`

Parses a raw Textract response into structured data.

| Parameter | Type | Description |
|---|---|---|
| `response` | `dict` | Raw Textract `AnalyzeExpense` response |
| `image_url` | `str` | S3 URL to attach to the result |

**Returns:** `ReceiptResult`

```python
@dataclass
class ReceiptItem:
    name: str
    price: float

@dataclass
class ReceiptResult:
    items: list[ReceiptItem]   # line items extracted from the receipt
    total: float | None        # grand total (if detected)
    tax: float | None          # tax amount (if detected)
    vendor: str | None         # restaurant/vendor name (if detected)
    image_url: str             # S3 URL of the uploaded receipt image
```

---

### `process_receipt(image_path) -> ReceiptResult`

Runs the full pipeline (upload → analyze → parse) in one call.

| Parameter | Type | Description |
|---|---|---|
| `image_path` | `Path \| str` | Local path to the receipt image (JPEG, PNG, WebP, HEIC) |

**Returns:** `ReceiptResult`

---

## CLI Usage (testing)

```bash
cd Banq_hackathon
python src/ocr.py path/to/receipt.jpg
```

Example output:

```
Vendor : De Silveren Spiegel
Image  : https://splitbill-receipts.s3.us-east-1.amazonaws.com/receipts/a3f1...jpg
Items  :
  Grilled Chicken                     €14.50
  Caesar Salad                        €11.00
  Pasta Carbonara                     €13.00
  Heineken                            €4.50
Tax    : €3.87
Total  : €46.87
```

---

## Integration Points

### Backend API route

```python
from src.ocr import process_receipt

# Inside the POST /api/upload handler:
receipt = process_receipt(saved_image_path)

# Pass to LLM matching step
run_llm_matching(
    ocr_items=receipt.items,
    transcript=audio_result.transcript,
)
```

### LLM matching (Terrence — Claude Opus prompt)

Pass `receipt.items` as a list of `{name, price}` dicts alongside the audio transcript. Textract `AnalyzeExpense` is designed for receipts so item names and prices are reliably separated.

---

## Fallback

If Textract fails or the image is unreadable, fall back to Claude's vision capability:

```python
import anthropic, base64

client = anthropic.Anthropic()
with open(image_path, "rb") as f:
    b64 = base64.b64encode(f.read()).decode()

response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    messages=[{
        "role": "user",
        "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
            {"type": "text", "text": "Extract all line items and prices from this receipt as JSON: [{\"name\": ..., \"price\": ...}]"}
        ]
    }]
)
```

---

## Supported Image Formats

| Format | Notes |
|---|---|
| JPEG / JPG | Default camera format on most phones |
| PNG | Screenshots or scanned receipts |
| WebP | Modern browser uploads |
| HEIC | iOS default (convert server-side if needed) |

Max image size: **5 MB** (Textract synchronous API limit)

---

## Cost

| Step | Service | Cost |
|---|---|---|
| S3 upload + storage | AWS S3 | ~$0.023 / GB stored |
| OCR analysis | AWS Textract AnalyzeExpense | $0.0015 per page |

For a single receipt: **< $0.01 total**

---

## Status

| Component | Status |
|---|---|
| S3 image upload | Done |
| Textract AnalyzeExpense call | Done |
| Response parsing (items, tax, total, vendor) | Done |
| Backend API route integration | Pending (Adam) |
| Receipt image display on website | Pending (Pepijn / Noah) |
| Testing with real receipts | Pending (Pepijn) |
