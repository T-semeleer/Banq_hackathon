# bunq Payments — SplitBill

## Overview

`src/bunq.py` creates bunq.me payment links for each person in a split result and injects them into the split dict for display on the front-end.

---

## File

```
src/bunq.py
```

---

## Dependencies

```
hackathon_toolkit-main/bunq_client.py  (BunqClient)
src/matcher.py                         (SplitResult)
```

---

## Environment Variables

```
BUNQ_API_KEY=...    # optional — auto-created sandbox key used if absent
```

---

## Public API

### `create_payment_links(result, description_prefix) -> dict[str, str | None]`

Creates one bunq.me payment link per person in the split result.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `result` | `SplitResult` | — | Split result from `matcher.match()` |
| `description_prefix` | `str` | `"SplitBill"` | Prefix for the payment link description |

**Returns:** `{person_name: share_url}` — `None` for people who owe €0.

**How it works:**
1. Authenticates with bunq (creates sandbox user if `BUNQ_API_KEY` is not set)
2. For each person with `total_owed > 0`, posts a `bunqme-tab` with the exact amount
3. Fetches the tab to get the shareable `bunqme_tab_share_url`
4. Returns a name → URL mapping

**Description format:** `"SplitBill — {person.name} owes €{amount}"`

---

### `inject_links(split_dict, urls) -> dict`

Merges payment URLs into the dict produced by `result_to_dict()`.

| Parameter | Type | Description |
|---|---|---|
| `split_dict` | `dict` | Dict from `matcher.result_to_dict()` |
| `urls` | `dict[str, str \| None]` | Name → URL mapping from `create_payment_links()` |

**Returns:** Updated `split_dict` with `bunqme_url` and `payment_status` fields set per person.

**Status values set:**
- `"link_created"` — when a URL is available
- `"pending"` — default (unchanged) when no URL

---

## Integration Points

### Backend API route

```python
from bunq import create_payment_links, inject_links

urls = create_payment_links(split_result)
updated_dict = inject_links(split_dict, urls)
```

Called by `POST /api/links` in `src/app.py`.

---

## bunq sandbox notes

- `BunqClient.create_sandbox_user()` creates a temporary test account with pre-loaded funds
- Payment links created in sandbox are not real — they expire and cannot be paid outside the sandbox
- For demo purposes, use `POST /api/simulate` (via `src/app.py`) or `scripts/simulate_tikkie_payment.py` to generate incoming payments without real money

---

## Status

| Component | Status |
|---|---|
| bunq.me tab creation | Done — `src/bunq.py create_payment_links()` |
| URL injection into split dict | Done — `src/bunq.py inject_links()` |
| Backend route integration | Done — `src/app.py /api/links` |
| Unit tests | Done — `tests/test_bunq_functions.py` (14 tests) |
