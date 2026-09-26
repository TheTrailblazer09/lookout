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
from app.models import price as price_model
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
    sea = ("Stormy" if abs(day) > 2.5 * daily_sd else
           "Choppy" if abs(day) > 1.2 * daily_sd else "Calm")

    return {
        "empty": False,
        "as_of": as_of,
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


def simulate(portfolio_id: str, as_of: str, changes: dict[str, float]) -> dict:
    """What the numbers become under new weights. `changes` maps ticker to
    a new weight in percent; the rest scale to fill what's left."""
    before = analyze(portfolio_id, as_of)
    if before.get("empty"):
        return {"empty": True}
    weights = dict(before["weights"])
    for t, target in changes.items():
        if t in weights:
            weights[t] = float(target)
    fixed = sum(weights[t] for t in changes if t in weights)
    others = [t for t in weights if t not in changes]
    pool = sum(before["weights"][t] for t in others) or 1.0
    for t in others:
        weights[t] = before["weights"][t] / pool * max(0.0, 100 - fixed)
    return {"before": before, "after_weights": weights}