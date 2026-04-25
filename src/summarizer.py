"""
Monthly expense netting.

Tikkie reimbursements sent through this app embed a SPLIT|TXN{id}|{person}|{amount}
reference in their description. This module parses that reference and offsets
the reimbursement against the original expense rather than counting it as income,
so the monthly summary reflects the user's actual personal spending.
"""
import calendar
import re
import sys
from datetime import date
from pathlib import Path

_TOOLKIT_DIR = Path(__file__).resolve().parents[1] / "hackathon_toolkit-main"
if str(_TOOLKIT_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLKIT_DIR))

from bunq_client import BunqClient  # noqa: E402

_SPLIT_RE = re.compile(r"SPLIT\|TXN(\d+)\|([^|]+)\|(\d+\.\d{2})", re.IGNORECASE)


def summarize_month(client: BunqClient, account_id: int, year: int, month: int) -> dict:
    """
    Return a monthly expense summary with Tikkie reimbursements netted out.

    - gross_expenses: total of all outgoing payments (everything that left your account)
    - tikkie_reimbursements_received: incoming Tikkies that are linked to a specific
      bill split via the SPLIT|TXN format — based on the bill and how it was split
    - net_personal_expenses: gross_expenses - tikkie_reimbursements_received
    - other_income: all other incoming payments (including unlinked Tikkies)
    """
    raw = fetch_payments_for_month(client, account_id, year, month)

    expenses: dict[int, dict] = {}
    tikkies: list[dict] = []
    other_income: list[dict] = []

    for p in raw:
        value = p["value"]
        if value < 0:
            expenses[p["id"]] = {
                "transaction_id": p["id"],
                "description": p["description"],
                "gross_amount": round(abs(value), 2),
                "reimbursements": [],
                "net_personal_amount": abs(value),
                "date": p["created"][:10],
                "type": p.get("type", ""),
            }
        else:
            ref = _parse_split_ref(p["description"])
            if ref:
                exp_id, person, amount = ref
                tikkies.append({
                    "transaction_id": p["id"],
                    "expense_id": exp_id,
                    "from": person,
                    "amount": amount,
                    "date": p["created"][:10],
                })
            else:
                other_income.append({
                    "transaction_id": p["id"],
                    "description": p["description"],
                    "amount": round(value, 2),
                    "date": p["created"][:10],
                })

    # Link each Tikkie to its originating bill
    unmatched_ids: set[int] = set()
    unmatched: list[dict] = []
    for t in tikkies:
        exp = expenses.get(t["expense_id"])
        if exp:
            exp["reimbursements"].append({
                "transaction_id": t["transaction_id"],
                "from": t["from"],
                "amount": t["amount"],
            })
            exp["net_personal_amount"] -= t["amount"]
        else:
            unmatched_ids.add(t["transaction_id"])
            unmatched.append(t)

    for exp in expenses.values():
        exp["net_personal_amount"] = round(max(0.0, exp["net_personal_amount"]), 2)

    expense_list = sorted(expenses.values(), key=lambda x: x["date"], reverse=True)

    gross_expenses = round(sum(e["gross_amount"] for e in expense_list), 2)
    tikkie_total = round(
        sum(t["amount"] for t in tikkies if t["transaction_id"] not in unmatched_ids), 2
    )
    net_personal = round(max(0.0, gross_expenses - tikkie_total), 2)

    return {
        "period": f"{year:04d}-{month:02d}",
        "expenses": expense_list,
        "income": sorted(other_income, key=lambda x: x["date"], reverse=True),
        "unmatched_tikkies": unmatched,
        "totals": {
            "gross_expenses": gross_expenses,
            "tikkie_reimbursements_received": tikkie_total,
            "net_personal_expenses": net_personal,
            "other_income": round(sum(i["amount"] for i in other_income), 2),
        },
    }


def fetch_payments_for_month(
    client: BunqClient, account_id: int, year: int, month: int
) -> list[dict]:
    """
    Fetch all payments for the target month. Paginates using older_id until
    we move past the start of the month or exhaust the account history.
    """
    month_start = date(year, month, 1).isoformat()
    _, last_day = calendar.monthrange(year, month)
    month_end = date(year, month, last_day).isoformat()

    results: list[dict] = []
    older_id: int | None = None

    while True:
        params: dict = {"count": 200}
        if older_id is not None:
            params["older_id"] = older_id

        raw = client.get(
            f"user/{client.user_id}/monetary-account/{account_id}/payment",
            params=params,
        )
        if not raw:
            break

        last_id: int | None = None
        found_any_in_range = False

        for item in raw:
            p = item.get("Payment", {})
            created = (p.get("created") or "")[:10]
            last_id = p.get("id")

            if created > month_end:
                continue
            if created < month_start:
                return results

            value = float(p.get("amount", {}).get("value", "0"))
            results.append({
                "id": p.get("id"),
                "value": value,
                "description": p.get("description", ""),
                "created": p.get("created", ""),
                "type": p.get("type", ""),
            })
            found_any_in_range = True

        if len(raw) < 200:
            break
        if last_id is None:
            break
        older_id = last_id

    return results


def _parse_split_ref(description: str) -> tuple[int, str, float] | None:
    """Return (expense_id, person_name, amount) from a SPLIT|TXN... description, or None."""
    m = _SPLIT_RE.search(description)
    if m:
        return int(m.group(1)), m.group(2).strip(), float(m.group(3))
    return None
