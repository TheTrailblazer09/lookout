"""The daily portfolio read, cached per portfolio per day."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from app.models.base import execute, query_one


def get(portfolio_id: str, as_of: str) -> dict | None:
    row = query_one(
        "SELECT payload FROM summaries WHERE portfolio_id = ? AND as_of = CAST(? AS DATE)",
        [portfolio_id, as_of])
    if not row or not row[0]:
        return None
    try:
        return json.loads(row[0])
    except (TypeError, ValueError):
        return None


def save(portfolio_id: str, as_of: str, payload: dict) -> dict:
    execute("DELETE FROM summaries WHERE portfolio_id = ? AND as_of = CAST(? AS DATE)",
            [portfolio_id, as_of])
    execute("INSERT INTO summaries VALUES (?, CAST(? AS DATE), ?, ?)",
            [portfolio_id, as_of, json.dumps(payload), datetime.now(timezone.utc)])
    return payload