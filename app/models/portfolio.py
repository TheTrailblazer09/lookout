"""Holdings: read, replace, and value them as of a date."""
from __future__ import annotations

import pandas as pd

from app.models import price as price_model
from app.models.base import execute, execute_many, query


def get_holdings(portfolio_id: str) -> pd.DataFrame:
    return query("SELECT ticker, shares FROM holdings WHERE portfolio_id = ? ORDER BY ticker",
                 [portfolio_id])


def replace_holdings(portfolio_id: str, holdings: list[dict]) -> int:
    """Whole-portfolio replace: simplest correct behaviour for an editor
    that sends the full list every save."""
    execute("DELETE FROM holdings WHERE portfolio_id = ?", [portfolio_id])
    rows = [(portfolio_id, h["ticker"].upper(), float(h["shares"]))
            for h in holdings if float(h.get("shares", 0)) > 0]
    execute_many("INSERT INTO holdings VALUES (?,?,?)", rows)
    return len(rows)


def copy_portfolio(src_id: str, dst_id: str) -> int:
    """Used when someone signs up after clicking around the demo."""
    src = get_holdings(src_id)
    return replace_holdings(dst_id, src.to_dict("records"))


def valued(portfolio_id: str, as_of: str) -> pd.DataFrame:
    """Holdings priced as of a date.

    Columns: ticker, shares, close, prev_close, value, weight, day_return.
    Empty frame if the portfolio is empty or has no prices yet.
    """
    hold = get_holdings(portfolio_id)
    if hold.empty:
        return pd.DataFrame(columns=["ticker", "shares", "close", "prev_close",
                                     "value", "weight", "day_return"])
    px = price_model.latest(hold["ticker"].tolist(), as_of)
    df = hold.merge(px, on="ticker", how="inner")
    if df.empty:
        return df
    df["value"] = df["shares"] * df["close"]
    total = df["value"].sum()
    df["weight"] = df["value"] / total if total else 0.0
    df["day_return"] = df["close"] / df["prev_close"] - 1
    return df.sort_values("value", ascending=False).reset_index(drop=True)


def total_value(portfolio_id: str, as_of: str) -> float:
    df = valued(portfolio_id, as_of)
    return float(df["value"].sum()) if not df.empty else 0.0