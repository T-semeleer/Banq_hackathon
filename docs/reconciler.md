# Reconciler — SplitBill

## Overview

The reconciler compares incoming bunq transactions against the split result to determine who has paid and how much remains outstanding.

**Flow:**
1. Poll the last 50 payments on the bunq account
2. Filter to incoming transactions (positive value)
3. Match each non-self person to a transaction (name in description first, then amount proximity)
4. Return a footnote JSON with per-person paid status and a net-cost calculation

---

## File

```
src/reconciler.py
```

---

## Dependencies

```
hackathon_toolkit-main/bunq_client.py  (BunqClient)
src/matcher.py                         (SplitResult)
```

---

## Constants

| Name | Value | Description |
|---|---|---|
| `_AMOUNT_TOL` | `0.02` | EUR tolerance for amount-based matching |
| `_SELF_NAMES` | `{"you", "me", "i"}` | Names excluded from incoming payment tracking (the bill payer) |

---

## Public API

### `reconcile(client, account_id, split_result) -> dict`

Polls bunq and returns a JSON footnote showing payment status for each person.

| Parameter | Type | Description |
|---|---|---|
| `client` | `BunqClient` | Authenticated bunq client |
| `account_id` | `int` | bunq monetary account ID |
| `split_result` | `SplitResult` | Result from `matcher.match()` |

**Returns:**

```python
{
  "original_total": float,        # total from the split
  "payments": [
    {
      "name": str,                # person name
      "amount_owed": float,       # their total_owed, rounded to 2dp
      "paid": bool,               # True if a matching transaction was found
      "paid_at": str | None,      # ISO timestamp of transaction, or None
      "transaction_id": int | None  # bunq payment ID, or None
    }
  ],
  "total_repaid": float,          # sum of amount_owed for paid entries
  "net_cost": float,              # original_total - total_repaid
  "remaining_owed": float         # sum of amount_owed for unpaid entries
}
```

**Matching logic (in priority order):**
1. Person name found (case-insensitive) in transaction description
2. Transaction amount within `_AMOUNT_TOL` (€0.02) of `total_owed`
3. Each transaction can only be claimed by one person (`used_ids` set prevents double-counting)

**Self-name exclusion:** People whose names match `_SELF_NAMES` are skipped — they are the bill payer and do not owe money to themselves.

---

## Integration Points

### Backend API route

```python
from reconciler import reconcile

status = reconcile(client, account_id, split_result)
# Returns the footnote dict described above
```

Called by `GET /api/reconcile` in `src/app.py`.

### Front-end display

The `/api/reconcile` response drives the payment status badges and net-cost display in `src/templates/index.html`.

---

## How net cost works

```
original_total  = total bill (your card charge)
total_repaid    = sum of confirmed incoming payments
net_cost        = original_total - total_repaid
                  → converges to your own share as everyone pays back
```

---

## Status

| Component | Status |
|---|---|
| Incoming payment polling | Done — `src/reconciler.py reconcile()` |
| Name-based matching | Done — `src/reconciler.py _find_match()` |
| Amount-based fallback matching | Done — `src/reconciler.py _find_match()` |
| Duplicate-prevention (`used_ids`) | Done — `src/reconciler.py reconcile()` |
| Self-name exclusion | Done — `_SELF_NAMES` constant |
| Backend route integration | Done — `src/app.py /api/reconcile` |
| Unit tests | Done — `tests/test_reconciler.py` (10 tests) |
| Edge case tests | Done — `tests/test_reconciler_edge.py` (20 tests) |
