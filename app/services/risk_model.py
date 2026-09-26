"""Drawdown risk model: how likely is this stock to fall hard in the next
five trading days?

Two decisions do most of the work here.

The label is scaled per stock. "Falls more than 8%" would flag TSLA
constantly and NVDA never, telling you nothing. Instead a stock is marked
risky when its worst point over the next five days drops below
-1.5 x its own volatility x sqrt(5), where that volatility is estimated
only from data up to today. Calm stocks and wild stocks are then judged on
the same footing.

The split is by time, with a gap. Each label peeks five days ahead, so
neighbouring rows overlap; training on a random split would leak the
answer. We train on the earliest years, tune on the next, and touch the
final year exactly once for the reported numbers, with a purge gap between
each so no training row's window reaches into the test period.

Probabilities are calibrated with isotonic regression, because a raw score
of 0.8 does not mean 80%. Alerts quote these numbers to users, so they
have to mean what they say.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from app.models import prediction as prediction_model
from app.models import price as price_model
from app.models.base import query
from config import get_config

cfg = get_config()
MODEL_VERSION = "risk-v1"

FEATURES = ["ret1_z", "ret5_z", "ret20_z", "vol_ratio", "rsi", "dist_ma50",
            "dist_ma200", "volume_z", "drawdown_from_high", "market_vol_ratio",
            "mood", "mood_change"]

# Human wording for the driver list shown in alerts.
FEATURE_LABELS = {
    "ret1_z": "today's move, relative to its usual size",
    "ret5_z": "the last week's move",
    "ret20_z": "the last month's move",
    "vol_ratio": "recent swings vs its normal swings",
    "rsi": "momentum (RSI)",
    "dist_ma50": "distance from its 50-day average",
    "dist_ma200": "distance from its 200-day average",
    "volume_z": "unusual trading volume",
    "drawdown_from_high": "how far below its recent high it sits",
    "market_vol_ratio": "how jumpy the whole market is",
    "mood": "tone of recent news",
    "mood_change": "how fast news tone is shifting",
}


def _rsi(r: pd.Series, window: int = 14) -> pd.Series:
    up = r.clip(lower=0).ewm(alpha=1 / window, adjust=False).mean()
    down = (-r.clip(upper=0)).ewm(alpha=1 / window, adjust=False).mean()
    return 100 - 100 / (1 + up / down.replace(0, np.nan))


def build_features(as_of: str, tickers: list[str] | None = None) -> pd.DataFrame:
    """One row per stock per day. Every feature uses data known by that day."""
    tickers = tickers or price_model.known_tickers()
    tickers = [t for t in tickers if t != cfg.MARKET_TICKER]
    wide = price_model.with_market(tickers, as_of)
    if wide.empty:
        return pd.DataFrame()

    rets = np.log(wide / wide.shift(1))
    market = rets[cfg.MARKET_TICKER]
    market_vol = market.ewm(alpha=0.06).std()
    market_vol_ratio = market_vol / market_vol.rolling(252, min_periods=60).mean()

    mood_all = query("SELECT ticker, date, mood FROM sentiment_daily")
    frames = []
    for t in tickers:
        if t not in wide.columns:
            continue
        px, r = wide[t], rets[t]
        # volatility known through YESTERDAY: a crash must not shrink the
        # yardstick used to judge that same crash
        vol = r.ewm(alpha=0.06).std().shift(1)
        f = pd.DataFrame(index=px.index)
        f["ret1_z"] = r / vol
        f["ret5_z"] = r.rolling(5).sum() / (vol * np.sqrt(5))
        f["ret20_z"] = r.rolling(20).sum() / (vol * np.sqrt(20))
        f["vol_ratio"] = r.rolling(5).std() / r.rolling(60).std()
        f["rsi"] = _rsi(r) / 100
        f["dist_ma50"] = px / px.rolling(50).mean() - 1
        f["dist_ma200"] = px / px.rolling(200, min_periods=100).mean() - 1
        f["volume_z"] = 0.0
        f["drawdown_from_high"] = px / px.rolling(252, min_periods=60).max() - 1
        f["market_vol_ratio"] = market_vol_ratio
        if not mood_all.empty:
            m = mood_all[mood_all["ticker"] == t].set_index("date")["mood"]
            m.index = pd.to_datetime(m.index)
            idx = pd.to_datetime(f.index)
            aligned = m.reindex(idx).ffill()
            f["mood"] = aligned.fillna(0).to_numpy()
            f["mood_change"] = aligned.diff(3).fillna(0).to_numpy()
        else:
            f["mood"] = 0.0
            f["mood_change"] = 0.0

        # label: worst cumulative return over the next 5 sessions
        fwd = pd.concat([r.shift(-k) for k in range(1, 6)], axis=1).cumsum(axis=1)
        f["worst_forward"] = fwd.min(axis=1)
        f["threshold"] = -1.5 * vol * np.sqrt(5)
        f["label"] = (f["worst_forward"] < f["threshold"]).astype(int)
        f["ticker"] = t
        f["date"] = f.index
        frames.append(f)

    df = pd.concat(frames).reset_index(drop=True)
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=FEATURES)
    df["date"] = pd.to_datetime(df["date"])
    return df


def _fit(train: pd.DataFrame) -> LogisticRegression:
    model = LogisticRegression(max_iter=2000, C=0.5, class_weight="balanced")
    model.fit(train[FEATURES], train["label"])
    return model


def train_and_score(as_of: str, tickers: list[str] | None = None) -> dict:
    df = build_features(as_of, tickers)
    if df.empty or df["label"].nunique() < 2:
        raise RuntimeError("Not enough labelled data to train. Ingest more history.")

    purge = pd.Timedelta(days=cfg.PURGE_DAYS)
    end = df["date"].max()
    test_start = (end - pd.Timedelta(days=365)).normalize()
    val_start = (test_start - pd.Timedelta(days=365)).normalize()

    train = df[df["date"] <= val_start - purge]
    val = df[(df["date"] >= val_start) & (df["date"] <= test_start - purge)]
    test = df[df["date"] >= test_start]
    if min(len(train), len(val), len(test)) < 200:
        raise RuntimeError(
            f"Splits too small (train {len(train)}, tune {len(val)}, test {len(test)}). "
            "Ingest a longer history.")

    model = _fit(train)
    calib = IsotonicRegression(out_of_bounds="clip").fit(
        model.predict_proba(val[FEATURES])[:, 1], val["label"])
    p_test = calib.predict(model.predict_proba(test[FEATURES])[:, 1])

    # baseline: the obvious thing a person would do without a model
    base = LogisticRegression(max_iter=1000, class_weight="balanced")
    base.fit(train[["vol_ratio"]], train["label"])
    p_base = base.predict_proba(test[["vol_ratio"]])[:, 1]

    # uncertainty: resample whole weeks, since days within a week move together
    weeks = test["date"].dt.to_period("W")
    rng = np.random.default_rng(5)
    uniq = weeks.unique()
    diffs = []
    for _ in range(200):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        mask = weeks.isin(pick)
        if test.loc[mask, "label"].nunique() < 2:
            continue
        diffs.append(average_precision_score(test.loc[mask, "label"], p_test[mask.to_numpy()])
                     - average_precision_score(test.loc[mask, "label"], p_base[mask.to_numpy()]))
    lift_lo, lift_hi = (float(np.quantile(diffs, 0.025)), float(np.quantile(diffs, 0.975))) \
        if diffs else (float("nan"), float("nan"))

    metrics = {
        "model_version": MODEL_VERSION,
        "train_rows": int(len(train)), "tune_rows": int(len(val)), "test_rows": int(len(test)),
        "test_from": str(test["date"].min().date()), "test_to": str(test["date"].max().date()),
        "base_rate": round(float(test["label"].mean()), 4),
        "pr_auc_model": round(float(average_precision_score(test["label"], p_test)), 4),
        "pr_auc_baseline": round(float(average_precision_score(test["label"], p_base)), 4),
        "roc_auc_model": round(float(roc_auc_score(test["label"], p_test)), 4),
        "brier_model": round(float(brier_score_loss(test["label"], p_test)), 4),
        "brier_baseline": round(float(brier_score_loss(test["label"], p_base)), 4),
        "pr_auc_lift_ci95": [round(lift_lo, 4), round(lift_hi, 4)],
        "beats_baseline": bool(lift_lo > 0),
    }

    # refit on everything up to the test period, then score every day
    full = df[df["date"] <= test_start - purge]
    final = _fit(full)
    final_calib = IsotonicRegression(out_of_bounds="clip").fit(
        final.predict_proba(val[FEATURES])[:, 1], val["label"])
    df["p_drawdown"] = final_calib.predict(final.predict_proba(df[FEATURES])[:, 1])

    coefs = dict(zip(FEATURES, final.coef_[0]))
    X = df[FEATURES].to_numpy()
    contrib = X * np.array([coefs[f] for f in FEATURES])
    order = np.argsort(-np.abs(contrib), axis=1)[:, :3]
    drivers = [
        json.dumps([{
            "feature": FEATURES[j],
            "label": FEATURE_LABELS[FEATURES[j]],
            "value": round(float(X[i, j]), 3),
            "push": round(float(contrib[i, j]), 3),
            "direction": "raises risk" if contrib[i, j] > 0 else "lowers risk",
        } for j in order[i]])
        for i in range(len(df))
    ]
    out = pd.DataFrame({
        "ticker": df["ticker"].to_numpy(),
        "date": df["date"].dt.date.to_numpy(),
        "p_drawdown": df["p_drawdown"].astype(float).to_numpy(),
        "drivers": drivers,
        "model_version": MODEL_VERSION,
    })
    prediction_model.replace_all(out)
    metrics["scored_rows"] = int(len(out))
    return metrics