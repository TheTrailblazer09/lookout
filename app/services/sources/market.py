"""Real market data from Yahoo Finance (yfinance).

Two jobs, and the second is where the care goes:

1. Daily prices. known_at = 4pm ET that day, the close.
2. Earnings. Yahoo gives the report timestamp and the EPS estimate vs
   actual. A report released after the close cannot move the stock until
   the NEXT session, so day0 is shifted. Getting this wrong is the single
   most common way an event study accidentally sees the future.

Surprises are standardized per company (divided by that company's own
history of surprises) so a 3-cent miss at a company that never misses
counts for more than a 3-cent miss at a volatile one.
"""
from __future__ import annotations

import datetime as dt
import time

import numpy as np
import pandas as pd

MARKET_CLOSE_HOUR = 16  # ET


def to_date(value) -> "dt.date":
    """Everything in this app compares trading days as datetime.date.
    Pandas hands back Timestamps, numpy datetime64, or dates depending on
    version and source, and comparing across those types raises. Normalize
    once, here, rather than guarding at every comparison."""
    if value is None:
        return None
    if isinstance(value, dt.date) and not isinstance(value, dt.datetime):
        return value
    return pd.Timestamp(value).date()


def fetch_prices(tickers: list[str], start: str, end: str | None = None) -> pd.DataFrame:
    """Daily bars for every ticker. Returns rows matching the prices table."""
    import yfinance as yf

    raw = yf.download(tickers, start=start, end=end, auto_adjust=False,
                      group_by="ticker", threads=True, progress=False)
    if raw.empty:
        raise RuntimeError("Yahoo returned no price data (rate limited, or bad tickers)")

    frames = []
    for t in tickers:
        try:
            d = raw[t] if isinstance(raw.columns, pd.MultiIndex) else raw
        except KeyError:
            continue
        d = d.dropna(subset=["Close"])
        if d.empty:
            continue
        frames.append(pd.DataFrame({
            "ticker": t,
            "date": [ts.date() for ts in d.index],
            "open": d["Open"].astype(float).values,
            "high": d["High"].astype(float).values,
            "low": d["Low"].astype(float).values,
            "close": d["Close"].astype(float).values,
            "adj_close": d.get("Adj Close", d["Close"]).astype(float).values,
            "volume": d["Volume"].fillna(0).astype("int64").values,
            # the close is public at the close
            "known_at": [pd.Timestamp(ts.date()) + pd.Timedelta(hours=MARKET_CLOSE_HOUR)
                         for ts in d.index],
        }))
    if not frames:
        raise RuntimeError("No usable price rows came back")
    return pd.concat(frames, ignore_index=True)


def _next_session(day, sessions: list):
    """First trading day strictly after `day`, from the sessions we have."""
    day = to_date(day)
    for s in sessions:
        if to_date(s) > day:
            return to_date(s)
    return None


def fetch_earnings(tickers: list[str], sessions: list, limit: int = 40,
                   pause: float = 0.6, progress=None) -> pd.DataFrame:
    """Earnings events with standardized surprises.

    `sessions` is the sorted list of trading dates from the price table; it
    is how we decide which day an after-hours report lands on.
    """
    import yfinance as yf

    sessions = sorted({to_date(s) for s in sessions})
    session_set = set(sessions)
    rows = []
    failed = []
    for i, t in enumerate(tickers, 1):
        if progress:
            progress(i, len(tickers), t)
        try:
            df = yf.Ticker(t).get_earnings_dates(limit=limit)
            time.sleep(pause)  # Yahoo rate-limits aggressively
        except Exception as exc:  # noqa: BLE001 - one bad ticker must not stop ingestion
            failed.append(t)
            continue
        if df is None or df.empty:
            continue
        df = df.dropna(subset=["Reported EPS", "EPS Estimate"])
        if df.empty:
            continue

        # Yahoo repeats a report timestamp sometimes (restatements, dupes).
        # A duplicated index makes .loc return a Series instead of a number,
        # which silently poisons every value built from it, so collapse
        # duplicates to one row per timestamp and work positionally.
        df = (df[~df.index.duplicated(keep="first")]
              .sort_index()
              .reset_index()
              .rename(columns={df.index.name or "index": "when"}))
        when_col = "when" if "when" in df.columns else df.columns[0]

        est = df["EPS Estimate"].astype(float)
        act = df["Reported EPS"].astype(float)
        surprise = ((act - est) / est.abs().replace(0, np.nan)) \
            .replace([np.inf, -np.inf], np.nan)
        keep = surprise.notna()
        if int(keep.sum()) < 4:
            continue  # too few reports to standardize meaningfully
        vals = surprise[keep]
        sd = float(vals.std(ddof=0)) or 1.0
        mean = float(vals.mean())

        for pos in np.flatnonzero(keep.to_numpy()):
            raw = float(surprise.iat[pos])
            s = (raw - mean) / sd
            ts = df[when_col].iat[pos]
            when = pd.Timestamp(ts)
            when = when.tz_localize(None) if when.tzinfo else when
            report_day = when.date()
            after_close = when.hour >= MARKET_CLOSE_HOUR
            day0 = _next_session(report_day, sessions) if after_close else report_day
            if day0 is None:
                continue
            if day0 not in session_set:
                # report landed on a holiday or a day we have no bar for:
                # roll forward to the next session we do have
                day0 = _next_session(day0, sessions)
                if day0 is None:
                    continue
            sub = "beat" if s > 0.15 else "miss" if s < -0.15 else "inline"
            rows.append({
                "id": f"earn-{t}-{report_day}",
                "ticker": t, "type": "earnings", "subtype": sub,
                "known_at": when, "day0": day0,
                "value": raw, "surprise_z": float(s),
                "source": "yahoo",
                "description": f"{t} reported: {sub}, surprise {s:+.1f} sd vs its own history",
            })
    if failed:
        print(f"  ! no earnings data for {len(failed)}: {', '.join(failed[:12])}"
              + (" ..." if len(failed) > 12 else ""))
    return pd.DataFrame(rows)

# Fields worth showing a person, and what to call them. Anything Yahoo
# doesn't return is simply absent rather than shown as zero.
FUNDAMENTAL_FIELDS = {
    "longName": "name",
    "sector": "sector",
    "industry": "industry",
    "country": "country",
    "fullTimeEmployees": "employees",
    "marketCap": "market_cap",
    "trailingPE": "pe_trailing",
    "forwardPE": "pe_forward",
    "priceToBook": "price_to_book",
    "trailingEps": "eps",
    "dividendYield": "dividend_yield",
    "beta": "beta",
    "fiftyTwoWeekHigh": "high_52w",
    "fiftyTwoWeekLow": "low_52w",
    "totalRevenue": "revenue",
    "revenueGrowth": "revenue_growth",
    "profitMargins": "profit_margin",
    "returnOnEquity": "return_on_equity",
    "debtToEquity": "debt_to_equity",
    "freeCashflow": "free_cash_flow",
    "targetMeanPrice": "analyst_target",
    "recommendationKey": "analyst_view",
    "numberOfAnalystOpinions": "analyst_count",
    "longBusinessSummary": "about",
}


def fetch_fundamentals(tickers: list[str], pause: float = 0.4,
                       progress=None) -> list[dict]:
    """Company facts per ticker.

    Yahoo's info endpoint is slow and occasionally returns nothing, so each
    ticker is fetched independently and a failure costs only that one.
    """
    import yfinance as yf

    out = []
    for i, t in enumerate(tickers, 1):
        if progress:
            progress(i, len(tickers), t)
        try:
            info = yf.Ticker(t).get_info()
            time.sleep(pause)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(info, dict) or not info:
            continue
        payload = {}
        for src, dest in FUNDAMENTAL_FIELDS.items():
            value = info.get(src)
            if value in (None, "", "None"):
                continue
            if dest == "about":
                value = str(value)[:600]
            payload[dest] = value
        if payload:
            out.append({"ticker": t, "known_at": pd.Timestamp.now(), "payload": payload})
    return out