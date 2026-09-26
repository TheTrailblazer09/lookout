"""Fingerprint rows: evidence summarized per stock x event type x direction.

Stored with an as_of date so snapshots accumulate and the UI can show how
a stock's sensitivity drifted over time."""
from __future__ import annotations

import pandas as pd

from app.models.base import execute, insert_df, query

COLUMNS = ["ticker", "event_type", "direction", "as_of", "n", "typical_move",
           "baseline_move", "shrunk_move", "ci_low", "ci_high", "share_up",
           "reliable", "method_version"]


def replace_for(as_of: str, df: pd.DataFrame) -> int:
    """Replace this snapshot only; earlier snapshots stay."""
    execute("DELETE FROM fingerprint WHERE as_of = CAST(? AS DATE)", [as_of])
    return insert_df("fingerprint", df.reindex(columns=COLUMNS))


def latest_as_of(as_of: str) -> str | None:
    row = query("SELECT max(as_of) AS d FROM fingerprint WHERE as_of <= CAST(? AS DATE)",
                [as_of])["d"][0]
    return None if pd.isna(row) else str(row)


def for_ticker(ticker: str, as_of: str, direction: str | None = None) -> pd.DataFrame:
    snap = latest_as_of(as_of)
    if snap is None:
        return pd.DataFrame()
    extra = f" AND direction = '{direction}'" if direction else ""
    return query(f"""SELECT * FROM fingerprint
                     WHERE ticker = '{ticker.upper()}' AND as_of = DATE '{snap}'{extra}
                     ORDER BY event_type, direction""")


def cell(ticker: str, event_type: str, as_of: str, direction: str = "all") -> dict | None:
    df = for_ticker(ticker, as_of, direction)
    hit = df[df["event_type"] == event_type]
    return None if hit.empty else hit.iloc[0].to_dict()


def matrix(tickers: list[str], as_of: str) -> pd.DataFrame:
    """The heatmap: one row per stock x event type."""
    snap = latest_as_of(as_of)
    if snap is None or not tickers:
        return pd.DataFrame()
    names = ", ".join(f"'{t.upper()}'" for t in tickers)
    return query(f"""SELECT ticker, event_type, n, typical_move, baseline_move,
                            shrunk_move, ci_low, ci_high, share_up, reliable
                     FROM fingerprint
                     WHERE as_of = DATE '{snap}' AND direction = 'all'
                       AND ticker IN ({names})
                     ORDER BY ticker, event_type""")


def history(ticker: str, event_type: str, direction: str = "all") -> pd.DataFrame:
    """Every snapshot for one cell: how this sensitivity moved over time."""
    return query("""SELECT as_of, n, shrunk_move, ci_low, ci_high, reliable
                    FROM fingerprint
                    WHERE ticker = ? AND event_type = ? AND direction = ?
                    ORDER BY as_of""", [ticker.upper(), event_type, direction])