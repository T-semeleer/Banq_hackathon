# Matcher — SplitBill

## Overview

The matcher takes raw OCR text and a voice transcript, sends both to Claude Sonnet, and returns a structured breakdown of who owes what.

**Flow:**
1. OCR text + transcript are formatted into a prompt
2. Claude Sonnet returns a JSON split
3. Result is parsed into typed dataclasses

---

## File

```
src/matcher.py
```

---

## Dependencies

```bash
pip install anthropic python-dotenv
```

---

## Environment Variables

```
ANTHROPIC_API_KEY=sk-ant-...
```

---

## Data Types

```python
@dataclass
class ReceiptItem:
    name: str
    price: float

@dataclass
class PersonShare:
    name: str
    items: list[ReceiptItem]
    subtotal: float
    tax_share: float
    tip_share: float
    total_owed: float

@dataclass
class SplitResult:
    people: list[PersonShare]
    unassigned: list[ReceiptItem]
    total: float
    tax: float
    tip: float
```

---

## Public API

### `match(ocr_text, transcript) -> SplitResult`

Sends OCR text and voice transcript to Claude Sonnet (`claude-sonnet-4-6`) and returns a structured split.

| Parameter | Type | Description |
|---|---|---|
| `ocr_text` | `str` | Raw text from OCR (line items, prices, tax, total) |
| `transcript` | `str` | Voice memo text describing who ordered what |

**Returns:** `SplitResult`

**Behaviour:**
- "I" / "me" in the transcript → assigned to person named `"You"`
- Items with no clear owner → placed in `unassigned`
- Tax and tip are distributed proportionally by subtotal
- Shared items are split equally among those who shared them

---

### `result_to_dict(result) -> dict`

Serialises a `SplitResult` to a plain dict suitable for JSON responses or writing to `last_split.json`.

| Parameter | Type | Description |
|---|---|---|
| `result` | `SplitResult` | Parsed split result |

**Returns:** dict with shape:

```python
{
  "people": [
    {
      "name": "string",
      "items": [{"name": "string", "price": 0.00}],
      "subtotal": 0.00,
      "tax_share": 0.00,
      "tip_share": 0.00,
      "total_owed": 0.00,
      "bunqme_url": None,
      "payment_status": "pending",
    }
  ],
  "unassigned": [{"name": "string", "price": 0.00}],
  "total": 0.00,
  "tax": 0.00,
  "tip": 0.00,
  "status": "review",
}
```

---

## CLI Usage (testing)

```bash
cd Banq_hackathon
python src/matcher.py
```

Or with custom input files:

```bash
python src/matcher.py ocr.txt transcript.txt
```

---

## Integration Points

### Backend API route

```python
from matcher import match as do_split, result_to_dict

result = do_split(ocr_text, transcript)
split_dict = result_to_dict(result)
```

Called by `POST /api/split` in `src/app.py`.

### Downstream consumers

- `src/bunq.py` — `create_payment_links(result)` takes a `SplitResult`
- `src/reconciler.py` — `reconcile(client, account_id, split_result)` takes a `SplitResult`

---

## Model

| Step | Model | Max tokens |
|---|---|---|
| Bill splitting | `claude-sonnet-4-6` | 2000 |

---

## Cost

~$0.003–0.015 per split depending on receipt length.

---

## Status

| Component | Status |
|---|---|
| Claude Sonnet integration | Done — `src/matcher.py match()` |
| JSON parsing + dataclasses | Done — `src/matcher.py _parse()` |
| Serialisation helper | Done — `src/matcher.py result_to_dict()` |
| Backend route integration | Done — `src/app.py /api/split` |
| Unit + integration tests | Done — `tests/test_matcher_full.py`, `tests/test_merge.py` |
