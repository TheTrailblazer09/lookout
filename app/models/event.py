"""Events: earnings, macro releases, news swings, technical flags.

known_at is when the fact became public; day0 is the first trading day that
could react to it. They differ whenever news breaks after the close, which
is most earnings reports.
"""
from __future__ import annotations

import pandas as pd

from app.models.base import execute, insert_df, query, visible

COLUMNS = ["id", "ticker", "type", "subtype", "known_at", "day0",
           "value", "surprise_z", "source", "description"]


def upsert(df: pd.DataFrame) -> int:
    """Insert events, replacing any with the same id (re-running ingestion
    must not duplicate rows)."""
    if df.empty:
        return 0
    df = df.reindex(columns=COLUMNS)
    ids = ", ".join(f"'{i}'" for i in df["id"].tolist())
    execute(f"DELETE FROM events WHERE id IN ({ids})")
    return insert_df("events", df)


def on_day(as_of: str, ticker: str | None = None) -> pd.DataFrame:
    """Events whose day0 is as_of. Macro events (ticker IS NULL) always
    come back; a ticker filter adds that stock's own events."""
    where = "day0 = DATE '{}'".format(as_of)
    if ticker:
        where += f" AND (ticker = '{ticker.upper()}' OR ticker IS NULL)"
    return query(f"SELECT * FROM {visible('events', as_of)} WHERE {where}")


def upcoming(as_of: str, days: int = 14, tickers: list[str] | None = None) -> pd.DataFrame:
    """Scheduled events still ahead. Only events already announced (known_at
    <= as_of) count, which is why an unannounced earnings date never shows."""
    filt = ""
    if tickers:
        names = ", ".join(f"'{t.upper()}'" for t in tickers)
        filt = f"AND (ticker IN ({names}) OR ticker IS NULL)"
    return query(f"""
        SELECT * FROM {visible('events', as_of)}
        WHERE day0 > DATE '{as_of}' AND day0 <= DATE '{as_of}' + INTERVAL {int(days)} DAY {filt}
        ORDER BY day0
    """)


def history(event_types: list[str] | None = None, as_of: str | None = None) -> pd.DataFrame:
    """All events usable for the event study."""
    src = visible("events", as_of) if as_of else "events"
    where = ""
    if event_types:
        kinds = ", ".join(f"'{t}'" for t in event_types)
        where = f"WHERE type IN ({kinds})"
    return query(f"SELECT * FROM {src} {where} ORDER BY day0")


def counts_by_type() -> pd.DataFrame:
    return query("SELECT type, count(*) AS n, min(day0) AS first, max(day0) AS last "
                 "FROM events GROUP BY type ORDER BY n DESC")