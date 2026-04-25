"""
Reconciles bunq transaction history against a SplitResult.

Polls incoming payments, matches them to the people who owe money, and
returns a JSON-serialisable dict with per-person paid/unpaid status and
a net-cost footnote.
"""
import sys
from pathlib import Path

_TOOLKIT_DIR = Path(__file__).resolve().parents[1] / "hackathon_toolkit-main"
if str(_TOOLKIT_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLKIT_DIR))

from bunq_client import BunqClient  # noqa: E402
from matcher import SplitResult  # noqa: E402

_AMOUNT_TOL = 0.02
_SELF_NAMES = {"you", "me", "i"}


def reconcile(client: BunqClient, account_id: int, split_result: SplitResult) -> dict:
    """
    Compare incoming bunq transactions against the split result.

    Returns:
        {
          "original_total": float,
          "payments": [
            {"name": str, "amount_owed": float, "paid": bool,
             "paid_at": str|None, "transaction_id": int|None}
          ],
          "total_repaid": float,
          "net_cost": float,        # original_total - total_repaid
          "remaining_owed": float,  # sum of unpaid amounts
        }
    """
    raw = client.get(
        f"user/{client.user_id}/monetary-account/{account_id}/payment",
        params={"count": 50},
    )

    incoming: list[dict] = []
    for item in raw:
        p = item.get("Payment", {})
        value = float(p.get("amount", {}).get("value", "0"))
        if value > 0:
            incoming.append({
                "id": p.get("id"),
                "value": value,
                "description": p.get("description", ""),
                "created": p.get("created", ""),
            })

    used_ids: set = set()
    payments: list[dict] = []

    for person in split_result.people:
        if person.name.lower() in _SELF_NAMES:
            continue

        txn = _find_match(person.name, person.total_owed, incoming, used_ids)
        if txn:
            used_ids.add(txn["id"])

        payments.append({
            "name": person.name,
            "amount_owed": round(person.total_owed, 2),
            "paid": txn is not None,
            "paid_at": txn["created"] if txn else None,
            "transaction_id": txn["id"] if txn else None,
        })

    total_repaid = sum(p["amount_owed"] for p in payments if p["paid"])
    original = round(split_result.total, 2)
    net_cost = round(original - total_repaid, 2)
    remaining = round(sum(p["amount_owed"] for p in payments if not p["paid"]), 2)

    if remaining == 0:
        summary_line = (
            f"All repaid. You paid €{original:.2f} total and received "
            f"€{total_repaid:.2f} back — your actual share was €{net_cost:.2f}."
        )
    else:
        summary_line = (
            f"You paid €{original:.2f}. Received €{total_repaid:.2f} so far. "
            f"Your current net cost is €{net_cost:.2f} (€{remaining:.2f} still outstanding)."
        )

    return {
        "original_total": original,
        "payments": payments,
        "total_repaid": round(total_repaid, 2),
        "net_cost": net_cost,
        "remaining_owed": remaining,
        "summary_line": summary_line,
    }


def _find_match(
    name: str,
    amount: float,
    incoming: list[dict],
    used: set,
) -> dict | None:
    """Match by name in description first, then fall back to amount proximity."""
    name_lower = name.lower()
    for txn in incoming:
        if txn["id"] not in used and name_lower in txn["description"].lower():
            return txn
    for txn in incoming:
        if txn["id"] not in used and abs(txn["value"] - amount) <= _AMOUNT_TOL:
            return txn
    return None
