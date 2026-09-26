"""Price reads. Every function takes as_of and goes through visible()."""
from __future__ import annotations

import pandas as pd

from app.models.base import query, visible
from config import get_config

cfg = get_config()


def history(tickers: list[str], as_of: str, lookback_days: int | None = None) -> pd.DataFrame:
    """Long frame: ticker, date, adj_close, volume."""
    if not tickers:
        return pd.DataFrame(columns=["ticker", "date", "adj_close", "volume"])
    names = ", ".join(f"'{t.upper()}'" for t in tickers)
    limit = ""
    if lookback_days:
        limit = f"AND date >= (DATE '{as_of}' - INTERVAL {int(lookback_days)} DAY)"
    return query(f"""
        SELECT ticker, date, adj_close, volume
        FROM {visible('prices', as_of)}
        WHERE ticker IN ({names}) {limit}
        ORDER BY date
    """)


def wide(tickers: list[str], as_of: str, lookback_days: int | None = None) -> pd.DataFrame:
    """Date-indexed frame, one column per ticker. The shape most math wants."""
    df = history(tickers, as_of, lookback_days)
    if df.empty:
        return df
    return df.pivot(index="date", columns="ticker", values="adj_close").sort_index()


def with_market(tickers: list[str], as_of: str, lookback_days: int | None = None) -> pd.DataFrame:
    """Same as wide(), plus the market index column."""
    return wide(list(dict.fromkeys([*tickers, cfg.MARKET_TICKER])), as_of, lookback_days)


def latest(tickers: list[str], as_of: str) -> pd.DataFrame:
    """Last close on or before as_of, plus the close before it, so callers
    can compute a one-day move. Columns: ticker, date, close, prev_close."""
    if not tickers:
        return pd.DataFrame(columns=["ticker", "date", "close", "prev_close"])
    names = ", ".join(f"'{t.upper()}'" for t in tickers)
    return query(f"""
        WITH ranked AS (
            SELECT ticker, date, adj_close,
                   row_number() OVER (PARTITION BY ticker ORDER BY date DESC) AS rn
            FROM {visible('prices', as_of)}
            WHERE ticker IN ({names})
        )
        SELECT a.ticker, a.date, a.adj_close AS close, b.adj_close AS prev_close
        FROM ranked a LEFT JOIN ranked b ON b.ticker = a.ticker AND b.rn = 2
        WHERE a.rn = 1
    """)


def search(term: str, limit: int = 8) -> list[str]:
    term = (term or "").upper().replace("'", "")
    return query(f"""
        SELECT DISTINCT ticker FROM prices
        WHERE ticker LIKE '%{term}%' AND ticker != '{cfg.MARKET_TICKER}'
        ORDER BY ticker LIMIT {int(limit)}
    """)["ticker"].tolist()


def known_tickers() -> list[str]:
    return query("SELECT DISTINCT ticker FROM prices ORDER BY ticker")["ticker"].tolist()


def last_trading_day(as_of: str) -> str | None:
    row = query(f"SELECT max(date) AS d FROM {visible('prices', as_of)}")["d"][0]
    return None if pd.isna(row) else str(row)