# Tikkie Simulation — SplitBill

## Overview

`scripts/simulate_tikkie_payment.py` simulates people paying you back via Tikkie using the bunq sandbox. A `request-inquiry` sent to `sugardaddy@bunq.com` is auto-accepted instantly, producing an incoming payment that `src/reconciler.py` can match.

---

## File

```
scripts/simulate_tikkie_payment.py
```

---

## Dependencies

```bash
pip install python-dotenv
# also requires: hackathon_toolkit-main/bunq_client.py
```

---

## Environment Variables

```
BUNQ_API_KEY=...    # optional — auto-created sandbox key used if absent
```

---

## How bunq sandbox simulation works

1. Script sends `POST request-inquiry` to `sugardaddy@bunq.com` with amount and description
2. bunq sandbox auto-accepts the request immediately
3. An incoming payment appears in your transaction history with description `"Tikkie repayment — {person}"`
4. The reconciler matches this by finding the person name in the transaction description

---

## Public API

### `simulate_payment(client, account_id, person_name, amount) -> dict`

Sends one request-inquiry to simulate a Tikkie repayment.

| Parameter | Type | Description |
|---|---|---|
| `client` | `BunqClient` | Authenticated bunq client |
| `account_id` | `int` | bunq monetary account ID |
| `person_name` | `str` | Person name (encoded in description for reconciler matching) |
| `amount` | `float` | Amount in EUR |

**Returns:**

```python
{
  "request_id": int,       # bunq request-inquiry ID
  "person": str,           # person name
  "amount": float,         # amount in EUR
  "description": str,      # "Tikkie repayment — {person_name}"
}
```

---

## CLI Usage

### Simulate one person

```bash
cd Banq_hackathon
python scripts/simulate_tikkie_payment.py --person "Sarah" --amount 13.31
```

### Simulate all non-self people from the last split

```bash
python scripts/simulate_tikkie_payment.py --all
```

Uses `last_split.json` in the project root (written automatically by `POST /api/split`).

### Custom split file

```bash
python scripts/simulate_tikkie_payment.py --all --split-file path/to/split.json
```

---

## CLI Options

| Flag | Description |
|---|---|
| `--person NAME` | Person name to simulate paying back |
| `--amount X.XX` | Amount in EUR |
| `--all` | Simulate all non-self people from split file |
| `--split-file PATH` | Split JSON file path (default: `last_split.json`) |

Either `--person` + `--amount` or `--all` is required.

---

## Self-name exclusion

People matching `_SELF_NAMES = {"you", "me", "i"}` are skipped when using `--all`. These names represent the bill payer (yourself) and should not be simulated as incoming payments.

---

## Example output

```
Authenticated — user 1234, account 5678

  Simulating €13.31 repayment from Sarah...
    Request #999 — "Tikkie repayment — Sarah"
  Simulating €11.00 repayment from Tom...
    Request #1000 — "Tikkie repayment — Tom"

Simulated 2 payment(s).
Wait a moment, then check status with: GET /api/reconcile
```

---

## Integration with reconciler

After running the simulation, call `GET /api/reconcile` to see the updated payment status:

```bash
curl http://localhost:5000/api/reconcile
```

The reconciler will match the incoming transactions by name in description and mark the relevant people as paid.

---

## Web alternative

The same simulation can be triggered from the front-end UI or via `POST /api/simulate` in `src/app.py`:

```bash
curl -X POST http://localhost:5000/api/simulate \
  -H "Content-Type: application/json" \
  -d '{"person": "Sarah", "amount": 13.31}'
```

---

## Status

| Component | Status |
|---|---|
| Single-person simulation | Done — `simulate_payment()` |
| Bulk simulation from split file | Done — `--all` flag |
| bunq sandbox auto-accept flow | Done — request to `sugardaddy@bunq.com` |
| Reconciler integration | Done — description encodes person name |
| CLI tests | Done — `tests/test_simulate.py` (14 tests) |
| Web route equivalent | Done — `src/app.py /api/simulate` |
