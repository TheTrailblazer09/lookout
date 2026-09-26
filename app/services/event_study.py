"""The event study: how much does each stock move when each kind of thing
happens, measured honestly.

Two methods, because one size does not fit:

  Company events (earnings, company news) are measured against the market.
  If NVDA fell 6% on a day the market fell 5%, almost nothing happened to
  NVDA specifically. We fit each stock's normal relationship to the market
  on the 120 sessions ending 10 days before the event, then measure the
  leftover move over days 0..+5.

  Macro events (CPI, Fed, jobs) are NOT market-adjusted. On a Fed day the
  market itself is the thing reacting, so subtracting it would erase the
  effect we are trying to measure. We use the raw move over days 0..+1 and
  compare it to that stock's own ordinary two-day move.

Everything is expressed in "how unusual" units (move_z): the reaction
divided by the stock's normal spread over the same span. That is what
makes a 3% move in KO comparable to a 9% move in TSLA.

Three habits keep this from fooling us:
  - a baseline from random non-event windows, so "sensitive" means
    sensitive compared to an ordinary week, not just volatile;
  - shrinkage toward the cross-stock average, because a mean of 6 events
    is noisy;
  - a bootstrap interval, and a reliable flag only when the interval
    clears the baseline.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.models import event as event_model
from app.models import evidence as evidence_model
from app.models import fingerprint as fingerprint_model
from app.models import price as price_model
from app.models.base import query
from config import get_config

cfg = get_config()
METHOD = "es-v1"
MACRO_TYPES = {"cpi", "fed", "jobs", "oil", "rates", "vix"}
RNG = np.random.default_rng(11)


# --------------------------------------------------------------------------
# evidence
# --------------------------------------------------------------------------

def build_evidence(as_of: str, tickers: list[str] | None = None,
                   progress=None) -> pd.DataFrame:
    tickers = tickers or price_model.known_tickers()
    tickers = [t for t in tickers if t != cfg.MARKET_TICKER]

    wide = price_model.with_market(tickers, as_of)
    if wide.empty:
        return pd.DataFrame()
    rets = np.log(wide / wide.shift(1))
    dates = list(rets.index)
    pos = {d: i for i, d in enumerate(dates)}
    market = rets[cfg.MARKET_TICKER].to_numpy()

    events = event_model.history(as_of=as_of)
    if events.empty:
        return pd.DataFrame()

    rows: list[dict] = []
    total = len(events)
    for n_done, e in enumerate(events.itertuples(), 1):
        if progress and n_done % 250 == 0:
            progress(n_done, total)
        etype = e.type
        is_macro = etype in MACRO_TYPES
        window = cfg.WINDOW_MACRO if is_macro else cfg.WINDOW_COMPANY
        day0 = e.day0
        if day0 not in pos:
            continue
        i0 = pos[day0]
        if i0 + window >= len(dates):
            continue  # window has not closed yet: not evidence
        outcome_known = pd.Timestamp(dates[i0 + window]) + pd.Timedelta(hours=16)

        targets = [e.ticker] if isinstance(e.ticker, str) and e.ticker else tickers
        for t in targets:
            if t not in rets.columns:
                continue
            r = rets[t].to_numpy()
            row = _measure(t, e, etype, is_macro, window, r, market, i0,
                           dates, outcome_known)
            if row:
                rows.append(row)

    df = pd.DataFrame(rows)
    if not df.empty:
        evidence_model.replace_all(df)
    return df


def _measure(t, e, etype, is_macro, window, r, market, i0, dates, outcome_known):
    est_hi = i0 - cfg.EST_GAP
    est_lo = est_hi - cfg.EST_WINDOW
    base = dict(ticker=t, event_id=e.id, event_type=etype, subtype=e.subtype,
                day0=e.day0, window_days=window, outcome_known_at=outcome_known,
                surprise_z=_f(e.surprise_z), description=e.description,
                method_version=METHOD)

    if est_lo < 0:
        return {**base, "included": False, "exclusion_reason": "not enough history",
                "ret20_before": None, "vol_before": None, "stock_ret": None,
                "market_ret": None, "abnormal_ret": None, "normal_spread": None,
                "move_z": None, "alpha": None, "beta": None}

    est_r, est_m = r[est_lo:est_hi], market[est_lo:est_hi]
    ok = ~(np.isnan(est_r) | np.isnan(est_m))
    if ok.sum() < 60:
        return {**base, "included": False, "exclusion_reason": "sparse history",
                "ret20_before": None, "vol_before": None, "stock_ret": None,
                "market_ret": None, "abnormal_ret": None, "normal_spread": None,
                "move_z": None, "alpha": None, "beta": None}

    stock_ret = float(np.nansum(r[i0:i0 + window + 1]))
    market_ret = float(np.nansum(market[i0:i0 + window + 1]))
    ret20 = float(np.nansum(r[max(0, i0 - 20):i0]))
    daily_sd = float(np.nanstd(est_r[ok]))
    vol_before = daily_sd * np.sqrt(252)

    if is_macro:
        # no market adjustment: the market is part of what we are measuring
        reaction = stock_ret
        spread = daily_sd * np.sqrt(window + 1)
        alpha = beta = None
    else:
        beta_, alpha_ = np.polyfit(est_m[ok], est_r[ok], 1)
        resid_sd = float(np.std(est_r[ok] - (alpha_ + beta_ * est_m[ok])))
        reaction = stock_ret - (alpha_ * (window + 1) + beta_ * market_ret)
        spread = resid_sd * np.sqrt(window + 1)
        alpha, beta = float(alpha_), float(beta_)

    if not spread or np.isnan(spread):
        return {**base, "included": False, "exclusion_reason": "zero variance",
                "ret20_before": ret20, "vol_before": vol_before,
                "stock_ret": stock_ret, "market_ret": market_ret,
                "abnormal_ret": None, "normal_spread": None, "move_z": None,
                "alpha": alpha, "beta": beta}

    return {**base, "included": True, "exclusion_reason": None,
            "ret20_before": ret20, "vol_before": vol_before,
            "stock_ret": stock_ret, "market_ret": market_ret,
            "abnormal_ret": float(reaction), "normal_spread": float(spread),
            "move_z": float(reaction / spread), "alpha": alpha, "beta": beta}


def _f(v):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else float(v)


# --------------------------------------------------------------------------
# baseline: what an ordinary window looks like
# --------------------------------------------------------------------------

def _baselines(as_of: str, tickers: list[str], windows: set[int],
               draws: int = 200) -> dict[tuple[str, int], float]:
    """Mean |move_z| over random windows with no event. By construction this
    is near 1.0 (a reaction divided by its own spread), but measuring it
    rather than assuming it catches fat tails and bad data."""
    wide = price_model.with_market(tickers, as_of)
    rets = np.log(wide / wide.shift(1))
    out: dict[tuple[str, int], float] = {}
    n = len(rets)
    for t in tickers:
        if t not in rets.columns:
            continue
        r = rets[t].to_numpy()
        for w in windows:
            lo = cfg.EST_WINDOW + cfg.EST_GAP + 1
            if n - w - 1 <= lo:
                continue
            idx = RNG.integers(lo, n - w - 1, size=draws)
            vals = []
            for i in idx:
                est = r[i - cfg.EST_GAP - cfg.EST_WINDOW:i - cfg.EST_GAP]
                est = est[~np.isnan(est)]
                if len(est) < 60:
                    continue
                sd = float(np.std(est)) * np.sqrt(w + 1)
                if sd:
                    vals.append(abs(float(np.nansum(r[i:i + w + 1]))) / sd)
            if vals:
                out[(t, w)] = float(np.mean(vals))
    return out


# --------------------------------------------------------------------------
# fingerprint
# --------------------------------------------------------------------------

def build_fingerprint(as_of: str, min_n: int = 4, min_n_directional: int = 8) -> pd.DataFrame:
    ev = evidence_model.usable(as_of)
    if ev.empty:
        return pd.DataFrame()

    tickers = sorted(ev["ticker"].unique())
    windows = set(int(w) for w in ev["window_days"].unique())
    base = _baselines(as_of, tickers, windows)

    rows = []
    for etype, chunk in ev.groupby("event_type"):
        # the prior: how much a typical stock reacts to this event type
        column_mean = float(chunk["move_z"].abs().mean())
        window = int(chunk["window_days"].iloc[0])
        for t, cell in chunk.groupby("ticker"):
            for direction, sel in _directions(cell):
                n = len(sel)
                if n < (min_n if direction == "all" else min_n_directional):
                    continue
                z = sel["move_z"].abs().to_numpy()
                typical_z = float(z.mean())
                k = cfg.SHRINK_STRENGTH
                shrunk_z = (n * typical_z + k * column_mean) / (n + k)
                boots = RNG.choice(z, size=(cfg.BOOTSTRAP_N, n), replace=True).mean(axis=1)
                lo_z, hi_z = (float(np.quantile(boots, 0.05)),
                              float(np.quantile(boots, 0.95)))
                base_z = base.get((t, window), 1.0)
                # convert z units back to percent using this stock's own spread
                spread = float(sel["normal_spread"].mean())
                rows.append(dict(
                    ticker=t, event_type=etype, direction=direction, as_of=as_of, n=n,
                    typical_move=typical_z * spread,
                    baseline_move=base_z * spread,
                    shrunk_move=shrunk_z * spread,
                    ci_low=lo_z * spread, ci_high=hi_z * spread,
                    share_up=float((sel["abnormal_ret"] > 0).mean()),
                    reliable=bool(lo_z > base_z and n >= min_n_directional),
                    method_version=METHOD))

    df = pd.DataFrame(rows)
    if not df.empty:
        fingerprint_model.replace_for(as_of, df)
    return df


def _directions(cell: pd.DataFrame):
    """all, plus beats/misses (or hot/cold) when each side has enough rows."""
    yield "all", cell
    s = cell["surprise_z"]
    if s.notna().any():
        yield "pos", cell[s > 0.15]
        yield "neg", cell[s < -0.15]


# --------------------------------------------------------------------------
# placebo: the check that the method is not inventing sensitivity
# --------------------------------------------------------------------------

def placebo(as_of: str, tickers: list[str] | None = None, draws: int = 300) -> dict:
    """Run the same measurement on random dates labelled as fake events.
    If those come out looking as 'sensitive' as real events, the method is
    broken. Report this number; it is the cheapest credibility you can buy.
    """
    tickers = tickers or price_model.known_tickers()
    tickers = [t for t in tickers if t != cfg.MARKET_TICKER][:40]
    base = _baselines(as_of, tickers, {cfg.WINDOW_COMPANY}, draws=draws)
    fake = float(np.mean(list(base.values()))) if base else float("nan")

    ev = evidence_model.usable(as_of)
    real = float(ev[~ev["event_type"].isin(MACRO_TYPES)]["move_z"].abs().mean()) \
        if not ev.empty else float("nan")
    return {"placebo_mean_move_z": round(fake, 3),
            "real_event_mean_move_z": round(real, 3),
            "ratio": round(real / fake, 2) if fake else None}