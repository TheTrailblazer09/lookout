"""Alert preferences, stored as JSON so adding a setting needs no migration."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from app.models.base import execute, query_one

DEFAULTS = {
    # How much has to be at stake before Lookout speaks up. The names map to
    # severity floors used when listing alerts.
    "sensitivity": "balanced",          # calm | balanced | vigilant
    "bots": ["technical", "earnings", "news", "macro"],
    "concentration_limit_pct": 25,      # nudge when one stock passes this
    "sector_limit_pct": 40,
    "digest": "daily",                  # daily | weekly | off
}


def get(portfolio_id: str) -> dict:
    row = query_one("SELECT payload FROM preferences WHERE portfolio_id = ?", [portfolio_id])
    if not row or not row[0]:
        return dict(DEFAULTS)
    try:
        stored = json.loads(row[0])
    except (TypeError, ValueError):
        return dict(DEFAULTS)
    return {**DEFAULTS, **stored}      # new defaults appear for old rows


def save(portfolio_id: str, prefs: dict) -> dict:
    merged = {**DEFAULTS, **{k: v for k, v in prefs.items() if k in DEFAULTS}}
    execute("DELETE FROM preferences WHERE portfolio_id = ?", [portfolio_id])
    execute("INSERT INTO preferences VALUES (?, ?, ?)",
            [portfolio_id, json.dumps(merged), datetime.now(timezone.utc)])
    return merged