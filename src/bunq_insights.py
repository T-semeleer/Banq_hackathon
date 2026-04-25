"""
Bunq native insights, event feed, and category integration.

Wraps /insights, /insights-search, /insight-preference-date,
/event, and /additional-transaction-information-category.

In sandbox environments, Tapix categorisation is not active, so
fetch_category_summary() falls back to build_sandbox_insights() which
computes the same breakdown from raw payments + the local category store
populated by demo_seeder.seed_demo().
"""
import calendar
import sys
from pathlib import Path

_SRC_DIR = Path(__file__).parent
_TOOLKIT_DIR = _SRC_DIR.parent / "hackathon_toolkit-main"
for _p in (str(_SRC_DIR), str(_TOOLKIT_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bunq_client import BunqClient  # noqa: E402
from category_store import all_assignments, LABELS, COLORS  # noqa: E402


def _period_bounds(year: int, month: int) -> tuple[str, str]:
    """Return (time_start, time_end) in bunq datetime format for a calendar month."""
    _, last_day = calendar.monthrange(year, month)
    time_start = f"{year:04d}-{month:02d}-01 00:00:00.000000"
    time_end = f"{year:04d}-{month:02d}-{last_day:02d} 23:59:59.999999"
    return time_start, time_end


def _unwrap(item: dict, *candidate_keys: str) -> dict:
    """Unwrap a bunq response item by trying known wrapper keys, then first key."""
    for key in candidate_keys:
        if key in item:
            return item[key]
    first = next(iter(item), None)
    return item[first] if first else item


def build_sandbox_insights(
    client: BunqClient,
    account_id: int,
    year: int,
    month: int,
) -> dict:
    """
    Compute a Tapix-style category breakdown from raw payments + local category store.

    Called automatically when /insights returns empty (sandbox environment).
    Requires demo_seeder.seed_demo() to have been called first to populate
    the category assignments.
    """
    from summarizer import fetch_payments_for_month  # avoid circular at module level

    category_map = all_assignments()
    payments = fetch_payments_for_month(client, account_id, year, month)

    buckets: dict[str, dict] = {}
    for p in payments:
        if p["value"] >= 0:
            continue  # only outgoing (negative value) expenses
        txn_id = p["id"]
        category = category_map.get(txn_id, "OTHER")
        amount = abs(p["value"])

        if category not in buckets:
            buckets[category] = {
                "category": category,
                "category_translated": LABELS.get(category, category.replace("_", " ").title()),
                "color": COLORS.get(category, "#888888"),
                "icon": category.lower(),
                "amount_total": {"value": "0.00", "currency": "EUR"},
                "number_of_transactions": 0,
            }
        current = float(buckets[category]["amount_total"]["value"])
        buckets[category]["amount_total"]["value"] = f"{round(current + amount, 2):.2f}"
        buckets[category]["number_of_transactions"] += 1

    categories = sorted(
        buckets.values(),
        key=lambda c: float(c["amount_total"]["value"]),
        reverse=True,
    )
    total_spend = round(sum(float(c["amount_total"]["value"]) for c in categories), 2)

    return {
        "period": f"{year:04d}-{month:02d}",
        "categories": categories,
        "total_spend": total_spend,
        "currency": "EUR",
        "source": "sandbox_overlay",
    }


def fetch_category_summary(
    client: BunqClient,
    year: int,
    month: int,
    account_id: int | None = None,
) -> dict:
    """
    Bunq-native category spend breakdown for a month via /insights.

    Returns:
        {
          "period": "YYYY-MM",
          "categories": [
            {
              "category": str,
              "category_translated": str,
              "color": str,
              "icon": str,
              "amount_total": {"value": str, "currency": str},
              "number_of_transactions": int
            }
          ],
          "total_spend": float,
          "currency": str
        }
    """
    time_start, time_end = _period_bounds(year, month)
    account_ids = [account_id] if account_id else None
    raw = client.get_insights(time_start, time_end, account_ids=account_ids)

    categories = []
    total_spend = 0.0
    currency = "EUR"

    for item in raw:
        insight = _unwrap(item, "InsightByCategory", "Insight")
        amount_obj = insight.get("amount_total", {})
        try:
            amount_val = float(amount_obj.get("value", 0))
        except (TypeError, ValueError):
            amount_val = 0.0
        currency = amount_obj.get("currency", "EUR")
        total_spend += amount_val
        categories.append({
            "category": insight.get("category", ""),
            "category_translated": insight.get("category_translated", ""),
            "color": insight.get("category_color", ""),
            "icon": insight.get("category_icon", ""),
            "amount_total": amount_obj,
            "number_of_transactions": insight.get("number_of_transactions", 0),
        })

    categories.sort(key=lambda c: float(c["amount_total"].get("value", 0) or 0), reverse=True)

    if not categories and account_id is not None:
        # Tapix returned nothing — we're in sandbox. Use the local overlay instead.
        return build_sandbox_insights(client, account_id, year, month)

    return {
        "period": f"{year:04d}-{month:02d}",
        "categories": categories,
        "total_spend": round(total_spend, 2),
        "currency": currency,
        "source": "tapix",
    }


def fetch_category_transactions(
    client: BunqClient,
    category: str,
    year: int,
    month: int,
    account_id: int | None = None,
) -> dict:
    """
    Individual transactions for a Bunq category in a month via /insights-search.

    Returns:
        {
          "period": "YYYY-MM",
          "category": str,
          "transactions": [
            {
              "id": int,
              "created": str,
              "type": str,
              "amount": float,
              "description": str,
              "counterparty": str
            }
          ],
          "count": int,
          "total": float
        }
    """
    time_start, time_end = _period_bounds(year, month)
    raw = client.get_insights_search(category, time_start, time_end, account_id=account_id)

    transactions = []
    total = 0.0

    for item in raw:
        obj_key = next(iter(item), None)
        obj = item.get(obj_key, {}) if obj_key else {}

        amount_obj = obj.get("amount", {})
        try:
            amount_val = float(amount_obj.get("value", 0))
        except (TypeError, ValueError):
            amount_val = 0.0
        total += abs(amount_val)

        counterparty = (
            (obj.get("counterparty_alias") or {}).get("display_name", "")
            or (obj.get("alias") or {}).get("display_name", "")
        )

        transactions.append({
            "id": obj.get("id"),
            "created": (obj.get("created") or "")[:19],
            "type": obj_key,
            "amount": amount_val,
            "currency": amount_obj.get("currency", "EUR"),
            "description": obj.get("description", ""),
            "counterparty": counterparty,
        })

    return {
        "period": f"{year:04d}-{month:02d}",
        "category": category,
        "transactions": transactions,
        "count": len(transactions),
        "total": round(total, 2),
    }


def fetch_event_feed(
    client: BunqClient,
    account_id: int | None = None,
    count: int = 50,
) -> dict:
    """
    Activity event feed via /event. Each event may carry a Tapix-assigned category
    in additional_transaction_information.

    Returns:
        {
          "events": [
            {
              "id": int,
              "created": str,
              "action": str,
              "monetary_account_id": int | None,
              "type": str | None,
              "status": str,
              "category": str | None,
              "amount": float | None,
              "description": str,
              "counterparty": str,
              "object": {...}
            }
          ],
          "count": int
        }
    """
    raw = client.get_events(account_id=account_id, count=count)

    events = []
    for item in raw:
        ev = _unwrap(item, "Event")
        obj = ev.get("object", {})
        obj_key = next(iter(obj), None)
        inner = obj.get(obj_key, {}) if obj_key else {}

        ati = ev.get("additional_transaction_information") or {}
        cat_field = ati.get("category")
        if isinstance(cat_field, dict):
            category = cat_field.get("category")
        else:
            category = cat_field

        amount_obj = inner.get("amount", {})
        try:
            amount_val = float(amount_obj.get("value", 0)) if amount_obj else None
        except (TypeError, ValueError):
            amount_val = None

        counterparty = (
            (inner.get("counterparty_alias") or {}).get("display_name", "")
            or (inner.get("alias") or {}).get("display_name", "")
        )

        events.append({
            "id": ev.get("id"),
            "created": (ev.get("created") or "")[:19],
            "action": ev.get("action"),
            "monetary_account_id": ev.get("monetary_account_id"),
            "type": obj_key,
            "status": ev.get("status"),
            "category": category,
            "amount": amount_val,
            "currency": amount_obj.get("currency") if amount_obj else None,
            "description": inner.get("description", ""),
            "counterparty": counterparty,
        })

    return {"events": events, "count": len(events)}


def fetch_insight_preference(client: BunqClient) -> dict:
    """
    User's configured monthly period start day via /insight-preference-date.
    This is the day-of-month boundary bunq uses for insight aggregations.
    """
    raw = client.get_insight_preference_date()
    if not raw:
        return {"preference_date": None}
    pref = _unwrap(raw[0], "InsightPreferenceDate")
    return {"preference_date": pref}


def fetch_all_categories(client: BunqClient) -> dict:
    """
    All spending categories (system Tapix-assigned + any user-defined overrides)
    via /additional-transaction-information-category.

    Returns:
        {
          "categories": [
            {
              "category": str,
              "type": str,
              "description": str,
              "description_translated": str,
              "color": str,
              "icon": str,
              "order": int
            }
          ]
        }
    """
    raw = client.get_transaction_categories()
    categories = []
    for item in raw:
        cat = _unwrap(item, "AdditionalTransactionInformationCategory")
        categories.append({
            "category": cat.get("category", ""),
            "type": cat.get("type", "SYSTEM"),
            "description": cat.get("description", ""),
            "description_translated": cat.get("description_translated", ""),
            "color": cat.get("color", ""),
            "icon": cat.get("icon", ""),
            "order": cat.get("order", 0),
        })
    categories.sort(key=lambda c: c.get("order", 0))
    return {"categories": categories}
