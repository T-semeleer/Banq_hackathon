"""
Local category assignment store for sandbox environments.

Maps bunq transaction IDs to spending categories. In production, Tapix handles
this automatically. In sandbox, we store assignments here after seeding demo
transactions, so /api/insights can return realistic category breakdowns.
"""
import json
from pathlib import Path

_STORE_PATH = Path(__file__).resolve().parents[1] / "category_map.json"


def _load() -> dict[str, str]:
    if not _STORE_PATH.exists():
        return {}
    try:
        with open(_STORE_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict[str, str]) -> None:
    with open(_STORE_PATH, "w") as f:
        json.dump(data, f, indent=2)


def assign(txn_id: int, category: str) -> None:
    """Persist a category assignment for a transaction ID."""
    data = _load()
    data[str(txn_id)] = category
    _save(data)


def get(txn_id: int) -> str | None:
    """Return the category for a transaction ID, or None if not assigned."""
    return _load().get(str(txn_id))


def all_assignments() -> dict[int, str]:
    """Return the full {transaction_id: category} map."""
    return {int(k): v for k, v in _load().items()}


def clear() -> None:
    """Remove all stored assignments (useful for resetting between demo runs)."""
    _save({})


LABELS: dict[str, str] = {
    "FOOD_AND_DRINK": "Food & Drink",
    "GROCERIES": "Groceries",
    "SHOPPING": "Shopping",
    "TRANSPORT": "Transport",
    "TRAVEL": "Travel",
    "HEALTH_AND_BEAUTY": "Health & Beauty",
    "ENTERTAINMENT": "Entertainment",
    "BILLS_AND_UTILITIES": "Bills & Utilities",
    "HOUSING": "Housing",
    "SAVINGS_AND_INVESTMENTS": "Savings & Investments",
    "TRANSFERS": "Transfers",
    "OTHER": "Other",
}

COLORS: dict[str, str] = {
    "FOOD_AND_DRINK": "#FF6B35",
    "GROCERIES": "#4CAF50",
    "SHOPPING": "#9C27B0",
    "TRANSPORT": "#2196F3",
    "TRAVEL": "#00BCD4",
    "HEALTH_AND_BEAUTY": "#E91E63",
    "ENTERTAINMENT": "#FF9800",
    "BILLS_AND_UTILITIES": "#607D8B",
    "HOUSING": "#795548",
    "SAVINGS_AND_INVESTMENTS": "#FFD700",
    "TRANSFERS": "#9E9E9E",
    "OTHER": "#757575",
}
