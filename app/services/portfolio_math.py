"""Portfolio statistics: risk contribution, correlation, beta, drawdown.

One idea drives the interesting number here. A stock's share of your money
is not its share of your risk. Risk contribution splits total portfolio
volatility across holdings, so you can say "NVDA is 21% of the money but
38% of the bumpiness" — which is the sentence that makes people act.

Covariance from a single year of daily returns is noisy, so we shrink it
toward a simple structured target (Ledoit-Wolf style): it keeps the matrix
well-behaved and the risk shares stable.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.models import portfolio as portfolio_model
from app.models import preference as preference_model
from app.models import price as price_model
from app.models.base import query, visible
from config import get_config

cfg = get_config()
TRADING_DAYS = 252


def _shrunk_cov(rets: pd.DataFrame) -> pd.DataFrame:
    """Sample covariance pulled toward a constant-correlation target."""
    S = rets.cov().to_numpy() * TRADING_DAYS
    n = len(rets)
    if n <= 2 or S.shape[0] < 2:
        return pd.DataFrame(S, index=rets.columns, columns=rets.columns)
    sd = np.sqrt(np.diag(S))
    corr = S / np.outer(sd, sd)
    off = corr[~np.eye(len(corr), dtype=bool)]
    mean_corr = float(np.nanmean(off)) if off.size else 0.0
    target = np.outer(sd, sd) * mean_corr
    np.fill_diagonal(target, np.diag(S))
    # more shrinkage when we have few observations per asset
    lam = min(1.0, max(0.05, S.shape[0] / max(n, 1)))
    shrunk = lam * target + (1 - lam) * S
    return pd.DataFrame(shrunk, index=rets.columns, columns=rets.columns)


def analyze(portfolio_id: str, as_of: str, lookback: int = TRADING_DAYS) -> dict:
    hold = portfolio_model.valued(portfolio_id, as_of)
    if hold.empty:
        return {"empty": True}

    tickers = hold["ticker"].tolist()
    wide = price_model.with_market(tickers, as_of, lookback_days=int(lookback * 1.8))
    have = [t for t in tickers if t in wide.columns]
    if not have or cfg.MARKET_TICKER not in wide.columns:
        return {"empty": True}

    rets = np.log(wide / wide.shift(1)).dropna(how="all").tail(lookback)
    w = hold.set_index("ticker")["weight"].reindex(have).fillna(0.0)
    w = w / w.sum() if w.sum() else w

    stock_rets = rets[have].dropna()
    cov = _shrunk_cov(stock_rets)
    wv = w.to_numpy()
    var = float(wv @ cov.to_numpy() @ wv)
    vol = float(np.sqrt(max(var, 0)))

    # risk contribution: w_i * (Sigma w)_i / (w' Sigma w), sums to 1
    mrc = cov.to_numpy() @ wv
    risk_share = (wv * mrc / var) if var else np.zeros_like(wv)

    # portfolio value path, for return and drawdown
    shares = hold.set_index("ticker")["shares"].reindex(have)
    values = wide[have].mul(shares, axis=1).dropna()
    port = values.sum(axis=1)
    port_ret = np.log(port / port.shift(1)).dropna().tail(lookback)
    spy = np.log(wide[cfg.MARKET_TICKER] / wide[cfg.MARKET_TICKER].shift(1)).dropna()
    joined = pd.concat([port_ret, spy], axis=1, join="inner").dropna()
    beta = float(np.cov(joined.iloc[:, 0], joined.iloc[:, 1])[0, 1] / joined.iloc[:, 1].var()) \
        if len(joined) > 20 else float("nan")

    path = port.tail(lookback)
    cum = path / path.iloc[0] - 1
    spy_path = wide[cfg.MARKET_TICKER].tail(lookback)
    spy_cum = spy_path / spy_path.iloc[0] - 1
    drawdown = float((path / path.cummax() - 1).min())

    day = float(port.iloc[-1] / port.iloc[-2] - 1) if len(port) > 1 else 0.0
    daily_sd = float(port_ret.std()) or 1e-9
    sea = _sea_state(day, daily_sd)

    pins = _pins(tickers, str(cum.index[0]), as_of)

    return {
        "empty": False,
        "as_of": as_of,
        "pins": pins,
        "value": float(port.iloc[-1]),
        "day_change_pct": day * 100,
        "return_pct": float(cum.iloc[-1]) * 100,
        "market_return_pct": float(spy_cum.iloc[-1]) * 100,
        "volatility_pct": vol * 100,
        "market_volatility_pct": float(spy.tail(lookback).std() * np.sqrt(TRADING_DAYS)) * 100,
        "beta": beta,
        "max_drawdown_pct": drawdown * 100,
        "sea_state": sea,
        "day_move_in_sds": day / daily_sd,
        "weights": {t: float(w[t]) * 100 for t in have},
        "risk_share": {t: float(risk_share[i]) * 100 for i, t in enumerate(have)},
        "correlation": stock_rets.corr().round(3).to_dict(),
        "series": [{"date": str(d.date() if hasattr(d, "date") else d),
                    "portfolio": round(float(p) * 100, 2),
                    "market": round(float(m) * 100, 2)}
                   for d, p, m in zip(cum.index[::3], cum.values[::3], spy_cum.values[::3])],
    }


# Absolute floors, on top of the "unusual for this portfolio" test.
# A portfolio of jumpy stocks has a wide normal range, so judging purely
# against its own history would call a 4% drop ordinary and say nothing.
# Two questions matter to a person: is this unusual FOR ME, and is it a big
# move in plain terms? Either one triggers.
STORMY_MOVE, CHOPPY_MOVE = 0.05, 0.025


def _sea_state(day_return: float, daily_sd: float) -> str:
    move = abs(day_return)
    if move > STORMY_MOVE or move > 2.5 * daily_sd:
        return "Stormy"
    if move > CHOPPY_MOVE or move > 1.2 * daily_sd:
        return "Choppy"
    return "Calm"


def _pins(tickers: list[str], start: str, as_of: str) -> list[dict]:
    """Moments worth marking on the performance line.

    Earnings are marked because they are the single biggest scheduled
    source of movement in a stock; alert days are marked because they are
    what Lookout itself flagged. Both are capped: a line peppered with
    thirty pins tells you nothing, so we keep the most significant ones.
    """
    if not tickers:
        return []
    names = ", ".join(f"'{t.upper()}'" for t in tickers)
    earnings = query(f"""
        SELECT day0 AS date, ticker, subtype, abs(surprise_z) AS weight
        FROM {visible('events', as_of)}
        WHERE type = 'earnings' AND ticker IN ({names})
          AND day0 BETWEEN DATE '{start}' AND DATE '{as_of}'
        ORDER BY weight DESC NULLS LAST
        LIMIT 8
    """)
    alerts = query(f"""
        SELECT as_of AS date, ticker, severity
        FROM alerts
        WHERE severity IN ('Storm', 'Choppy')
          AND as_of BETWEEN DATE '{start}' AND DATE '{as_of}'
        ORDER BY as_of DESC
        LIMIT 6
    """)

    pins = [
        {"date": str(r.date)[:10], "kind": "earnings", "ticker": r.ticker,
         "label": f"{r.ticker} earnings ({r.subtype})"}
        for r in earnings.itertuples()
    ] + [
        {"date": str(r.date)[:10], "kind": "alert", "ticker": r.ticker,
         "label": f"{r.severity}: {r.ticker}"}
        for r in alerts.itertuples()
    ]
    # one pin per day, alerts winning, so markers never stack illegibly
    best: dict[str, dict] = {}
    for pin in pins:
        if pin["date"] not in best or pin["kind"] == "alert":
            best[pin["date"]] = pin
    return sorted(best.values(), key=lambda p: p["date"])


def metrics_for_changes(portfolio_id: str, as_of: str,
                        changes: dict[str, float]) -> dict:
    """Recompute the portfolio's numbers under different weights.

    `changes` maps ticker to a new weight in percent; everything else
    scales proportionally to fill what is left, which is what actually
    happens when you trim one holding and do not touch the others.

    The same covariance is reused rather than re-estimated: we are asking
    "what if I held different amounts of these same stocks", not "what if
    the market behaved differently".
    """
    base = analyze(portfolio_id, as_of)
    if base.get("empty") or not changes:
        return base

    weights = dict(base["weights"])
    for ticker, target in changes.items():
        if ticker in weights:
            weights[ticker] = max(0.0, float(target))

    # Where does the freed money go? Spreading it proportionally across the
    # remaining holdings sounds fair, but it quietly pushes the next-biggest
    # position past the same limit the person just enforced. So we spread it
    # only up to that limit, and whatever will not fit sits in cash.
    limit = float(preference_model.get(portfolio_id).get("concentration_limit_pct", 100))
    fixed = sum(weights[t] for t in changes if t in weights)
    others = [t for t in weights if t not in changes]
    room = max(0.0, 100 - fixed)
    pool = sum(base["weights"][t] for t in others)

    if pool > 0 and others:
        for t in others:
            weights[t] = base["weights"][t] / pool * room
        # push anything over the limit back out, repeatedly, until the
        # remaining holdings can absorb no more
        for _ in range(10):
            excess = sum(max(0.0, weights[t] - limit) for t in others)
            if excess < 1e-6:
                break
            for t in others:
                weights[t] = min(weights[t], limit)
            takers = [t for t in others if weights[t] < limit - 1e-6]
            if not takers:
                break
            headroom = sum(limit - weights[t] for t in takers)
            give = min(excess, headroom)
            for t in takers:
                weights[t] += (limit - weights[t]) / headroom * give

    invested = sum(weights.values())
    cash_pct = max(0.0, 100 - invested)

    tickers = list(weights)
    wide = price_model.with_market(tickers, as_of, lookback_days=int(TRADING_DAYS * 1.8))
    have = [t for t in tickers if t in wide.columns]
    rets = np.log(wide / wide.shift(1)).dropna(how="all").tail(TRADING_DAYS)
    stock_rets = rets[have].dropna()
    cov = _shrunk_cov(stock_rets)

    # Cash has no variance and no beta, so it does not join the covariance
    # maths: the stock weights simply sum to less than 1 and every risk
    # figure scales down accordingly, which is exactly what holding cash
    # does to a portfolio.
    w = np.array([weights[t] for t in have], dtype=float) / 100.0
    var = float(w @ cov.to_numpy() @ w)
    vol = float(np.sqrt(max(var, 0)))
    mrc = cov.to_numpy() @ w
    risk_share = (w * mrc / var) if var else np.zeros_like(w)

    # beta of the reweighted mix, from each stock's beta to the market
    market = np.log(wide[cfg.MARKET_TICKER] / wide[cfg.MARKET_TICKER].shift(1)).dropna()
    betas = []
    for t in have:
        joined = pd.concat([stock_rets[t], market], axis=1, join="inner").dropna()
        betas.append(float(np.cov(joined.iloc[:, 0], joined.iloc[:, 1])[0, 1] / joined.iloc[:, 1].var())
                     if len(joined) > 20 else 1.0)
    beta = float(np.dot(w, betas))

    return {
        **base,
        "weights": {t: float(w[i]) * 100 for i, t in enumerate(have)},
        "risk_share": {t: float(risk_share[i]) * 100 for i, t in enumerate(have)},
        "volatility_pct": vol * 100,
        "beta": beta,
        "cash_pct": round(cash_pct, 1),
    }