"""Model output: one drawdown probability per stock per day."""
from __future__ import annotations

import json

import pandas as pd

from app.models.base import execute, insert_df, query, visible

COLUMNS = ["ticker", "date", "p_drawdown", "drivers", "model_version"]


def replace_all(df: pd.DataFrame) -> int:
    execute("DELETE FROM predictions")
    return insert_df("predictions", df.reindex(columns=COLUMNS))


def latest(tickers: list[str], as_of: str) -> pd.DataFrame:
    """Most recent score on or before as_of, per ticker."""
    if not tickers:
        return pd.DataFrame(columns=COLUMNS)
    names = ", ".join(f"'{t.upper()}'" for t in tickers)
    return query(f"""
        SELECT * FROM (
          SELECT *, row_number() OVER (PARTITION BY ticker ORDER BY date DESC) AS rn
          FROM predictions
          WHERE ticker IN ({names}) AND date <= DATE '{as_of}'
        ) WHERE rn = 1
    """).drop(columns=["rn"], errors="ignore")


def for_ticker(ticker: str, as_of: str, days: int = 120) -> pd.DataFrame:
    return query(f"""SELECT date, p_drawdown FROM predictions
                     WHERE ticker = '{ticker.upper()}' AND date <= DATE '{as_of}'
                     ORDER BY date DESC LIMIT {int(days)}""")


def drivers_of(row: pd.Series | dict) -> list[dict]:
    raw = row.get("drivers") if isinstance(row, dict) else row["drivers"]
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return []