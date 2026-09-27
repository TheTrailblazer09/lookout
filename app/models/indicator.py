"""Macro indicator levels, read as of a date."""
from __future__ import annotations

import pandas as pd

from app.models.base import execute, insert_df, query

COLUMNS = ["series_id", "label", "date", "known_at", "value"]


def replace(df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    ids = ", ".join(f"'{i}'" for i in df["series_id"].unique())
    execute(f"DELETE FROM indicators WHERE series_id IN ({ids})")
    return insert_df("indicators", df.reindex(columns=COLUMNS))


def latest(as_of: str) -> pd.DataFrame:
    """Most recent published value per series, plus the one before it."""
    return query(f"""
        WITH ranked AS (
          SELECT *, row_number() OVER (PARTITION BY series_id ORDER BY date DESC) AS rn
          FROM indicators
          WHERE known_at <= TIMESTAMP '{as_of} 23:59:59'
        )
        SELECT a.series_id, a.label, a.date, a.value,
               b.value AS prev_value
        FROM ranked a LEFT JOIN ranked b
          ON b.series_id = a.series_id AND b.rn = 2
        WHERE a.rn = 1
    """)


def history(series_id: str, as_of: str, points: int = 60) -> list[float]:
    df = query(f"""
        SELECT value FROM indicators
        WHERE series_id = '{series_id}' AND known_at <= TIMESTAMP '{as_of} 23:59:59'
        ORDER BY date DESC LIMIT {int(points)}
    """)
    return df["value"].tolist()[::-1] if not df.empty else []