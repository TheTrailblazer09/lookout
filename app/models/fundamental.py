"""Company facts, stored as JSON so a new field needs no migration."""
from __future__ import annotations

import json

import pandas as pd

from app.models.base import execute, insert_df, query_one


def replace(rows: list[dict]) -> int:
    """rows: [{ticker, known_at, payload(dict)}]"""
    if not rows:
        return 0
    tickers = ", ".join(f"'{r['ticker']}'" for r in rows)
    execute(f"DELETE FROM fundamentals WHERE ticker IN ({tickers})")
    df = pd.DataFrame([
        {"ticker": r["ticker"], "known_at": r["known_at"],
         "payload": json.dumps(r["payload"])}
        for r in rows
    ])
    return insert_df("fundamentals", df)


def get(ticker: str) -> dict | None:
    row = query_one("SELECT payload, known_at FROM fundamentals WHERE ticker = ?",
                    [ticker.upper()])
    if not row or not row[0]:
        return None
    try:
        data = json.loads(row[0])
    except (TypeError, ValueError):
        return None
    data["fetched_at"] = str(row[1])[:10]
    return data