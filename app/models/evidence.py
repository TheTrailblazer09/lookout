"""The evidence ledger: one row per stock per past event, with what
actually happened afterwards. The fingerprint is only a summary of this,
so every number in the UI can be clicked through to these rows."""
from __future__ import annotations

import pandas as pd

from app.models.base import execute, insert_df, query

COLUMNS = ["ticker", "event_id", "event_type", "subtype", "day0", "window_days",
           "outcome_known_at", "surprise_z", "ret20_before", "vol_before",
           "stock_ret", "market_ret", "abnormal_ret", "normal_spread", "move_z",
           "included", "exclusion_reason", "description", "alpha", "beta",
           "method_version"]


def replace_all(df: pd.DataFrame) -> int:
    execute("DELETE FROM evidence")
    return insert_df("evidence", df.reindex(columns=COLUMNS))


def usable(as_of: str, ticker: str | None = None,
           event_type: str | None = None) -> pd.DataFrame:
    """Rows whose outcome window had closed by as_of. An event that happened
    but whose 5 days have not finished is not evidence yet."""
    where = [f"outcome_known_at <= TIMESTAMP '{as_of} 23:59:59'", "included"]
    if ticker:
        where.append(f"ticker = '{ticker.upper()}'")
    if event_type:
        where.append(f"event_type = '{event_type}'")
    return query(f"SELECT * FROM evidence WHERE {' AND '.join(where)} ORDER BY day0 DESC")


def for_display(as_of: str, ticker: str, event_type: str | None = None,
                limit: int = 25) -> pd.DataFrame:
    df = usable(as_of, ticker, event_type)
    cols = ["day0", "event_type", "subtype", "description", "surprise_z",
            "stock_ret", "market_ret", "abnormal_ret", "move_z"]
    return df[cols].head(limit)


def analogs(as_of: str, ticker: str, event_type: str,
            surprise_z: float | None, ret20_before: float | None,
            k: int = 5) -> pd.DataFrame:
    """The k past events most like the one happening now: same type, then
    nearest on surprise size and how the stock had been trading."""
    pool = usable(as_of, ticker, event_type)
    if pool.empty:
        return pool
    d = pd.Series(0.0, index=pool.index)
    if surprise_z is not None and pool["surprise_z"].notna().any():
        d += (pool["surprise_z"].fillna(0) - surprise_z).abs()
    if ret20_before is not None and pool["ret20_before"].notna().any():
        scale = pool["ret20_before"].std(ddof=0) or 1.0
        d += (pool["ret20_before"].fillna(0) - ret20_before).abs() / scale
    return pool.assign(distance=d).nsmallest(k, "distance")


def counts() -> pd.DataFrame:
    return query("""SELECT event_type,
                           CAST(count(*) AS INTEGER) AS n,
                           CAST(sum(CASE WHEN included THEN 1 ELSE 0 END) AS INTEGER) AS kept
                    FROM evidence GROUP BY 1 ORDER BY n DESC""")