"""Everything about one holding, in a single response.

The holdings page asks about one stock at a time, and asking for its
price, technicals, risk score, fingerprint, evidence and news as six
separate requests makes the page assemble itself in pieces. One call,
one render.

Every part is as-of aware, so the page works inside a replay.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from app.models import evidence as evidence_model
from app.models import event as event_model
from app.models import fingerprint as fingerprint_model
from app.models import portfolio as portfolio_model
from app.models import prediction as prediction_model
from app.models import price as price_model
from app.models.base import query, visible
from app.services.bots import topics as topic_rules
from config import get_config

cfg = get_config()


def build(portfolio_id: str, ticker: str, as_of: str, days: int = 260) -> dict:
    ticker = ticker.upper()
    prices = price_model.history([ticker], as_of, lookback_days=int(days * 1.6) + 260)
    if prices.empty:
        return {"empty": True, "ticker": ticker}

    px = prices.set_index("date")["adj_close"].astype(float)
    rets = np.log(px / px.shift(1))

    return {
        "empty": False,
        "ticker": ticker,
        "as_of": as_of,
        "position": _position(portfolio_id, ticker, as_of),
        "series": _series(px, days),
        "pins": _pins(ticker, as_of, px.index[-days:] if len(px) > days else px.index),
        "technicals": _technicals(px, rets),
        "risk": _risk(ticker, as_of),
        "fingerprint": _fingerprint(ticker, as_of),
        "evidence": _evidence(ticker, as_of),
        "news": _news(ticker, as_of),
    }


def _position(portfolio_id: str, ticker: str, as_of: str) -> dict | None:
    held = portfolio_model.valued(portfolio_id, as_of)
    if held.empty:
        return None
    row = held[held["ticker"] == ticker]
    if row.empty:
        return None
    r = row.iloc[0]
    return {
        "shares": float(r["shares"]),
        "price": round(float(r["close"]), 2),
        "value": round(float(r["value"]), 2),
        "weight_pct": round(float(r["weight"]) * 100, 1),
        "day_change_pct": round(float(r["day_return"]) * 100, 2),
    }


def _series(px: pd.Series, days: int) -> list[dict]:
    ma50 = px.rolling(50, min_periods=10).mean()
    ma200 = px.rolling(200, min_periods=60).mean()
    tail = px.tail(days)
    return [
        {"date": str(d)[:10], "close": round(float(v), 2),
         "ma50": None if pd.isna(ma50.get(d)) else round(float(ma50[d]), 2),
         "ma200": None if pd.isna(ma200.get(d)) else round(float(ma200[d]), 2)}
        for d, v in tail.items()
    ]


def _pins(ticker: str, as_of: str, window) -> list[dict]:
    """Events for this stock inside the charted window."""
    if len(window) == 0:
        return []
    start, end = str(window[0])[:10], str(window[-1])[:10]
    df = query(f"""
        SELECT day0, type, subtype, description, surprise_z
        FROM {visible('events', as_of)}
        WHERE ticker = '{ticker}' AND day0 BETWEEN DATE '{start}' AND DATE '{end}'
        ORDER BY abs(coalesce(surprise_z, 0)) DESC
        LIMIT 10
    """)
    if df.empty:
        return []
    kind = {"earnings": "E", "news": "N"}
    return [{
        "date": str(r.day0)[:10],
        "kind": kind.get(r.type, "!"),
        "type": r.type,
        "label": str(r.description),
    } for r in df.itertuples()]


def _technicals(px: pd.Series, rets: pd.Series) -> dict:
    window = 14
    up = rets.clip(lower=0).ewm(alpha=1 / window, adjust=False).mean()
    down = (-rets.clip(upper=0)).ewm(alpha=1 / window, adjust=False).mean()
    rsi = float((100 - 100 / (1 + up / down.replace(0, np.nan))).iloc[-1])

    ma50 = float(px.rolling(50, min_periods=10).mean().iloc[-1])
    ma200v = px.rolling(200, min_periods=60).mean().iloc[-1]
    high = float(px.tail(252).max())
    vol_recent = float(rets.tail(20).std() * np.sqrt(252))
    vol_normal = float(rets.tail(252).std() * np.sqrt(252))

    return {
        "rsi": round(rsi, 0) if not np.isnan(rsi) else None,
        "ma50": round(ma50, 2),
        "vs_ma50_pct": round((float(px.iloc[-1]) / ma50 - 1) * 100, 1),
        "ma200": None if pd.isna(ma200v) else round(float(ma200v), 2),
        "vs_ma200_pct": None if pd.isna(ma200v) else round((float(px.iloc[-1]) / float(ma200v) - 1) * 100, 1),
        "from_high_pct": round((float(px.iloc[-1]) / high - 1) * 100, 1),
        "volatility_pct": round(vol_normal * 100, 0),
        "vol_ratio": round(vol_recent / vol_normal, 1) if vol_normal else None,
    }


def _risk(ticker: str, as_of: str) -> dict | None:
    df = prediction_model.latest([ticker], as_of)
    if df.empty:
        return None
    r = df.iloc[0]
    return {
        "p_drawdown_pct": round(float(r["p_drawdown"]) * 100, 1),
        "date": str(r["date"])[:10],
        "drivers": prediction_model.drivers_of(r.to_dict()),
    }


def _fingerprint(ticker: str, as_of: str) -> list[dict]:
    df = fingerprint_model.for_ticker(ticker, as_of, direction="all")
    if df.empty:
        return []
    out = []
    for r in df.itertuples():
        baseline = float(r.baseline_move) or 1e-9
        out.append({
            "event_type": r.event_type,
            "n": int(r.n),
            "typical_move_pct": round(float(r.shrunk_move) * 100, 1),
            "baseline_move_pct": round(baseline * 100, 1),
            "vs_baseline": round(float(r.shrunk_move) / baseline, 2),
            "share_up_pct": round(float(r.share_up) * 100, 0),
            "reliable": bool(r.reliable),
        })
    return sorted(out, key=lambda c: -c["vs_baseline"])


def _evidence(ticker: str, as_of: str, limit: int = 12) -> list[dict]:
    df = evidence_model.for_display(as_of, ticker, None, limit)
    if df.empty:
        return []
    df = df.copy()
    df["day0"] = df["day0"].astype(str).str[:10]
    return [{
        "date": r.day0,
        "event_type": r.event_type,
        "subtype": r.subtype,
        "description": r.description,
        "stock_pct": round(float(r.stock_ret) * 100, 1),
        "market_pct": round(float(r.market_ret) * 100, 1),
        "abnormal_pct": round(float(r.abnormal_ret) * 100, 1),
        "how_unusual": round(float(r.move_z), 1),
    } for r in df.itertuples()]


def _news(ticker: str, as_of: str, limit: int = 6) -> dict:
    articles = query(f"""
        SELECT a.known_at, a.title, a.url, a.source, s.topic,
               round(s.relevance, 2) AS relevance, round(s.sentiment, 2) AS sentiment
        FROM news_scores s JOIN {visible('news_articles', as_of)} a ON a.id = s.article_id
        WHERE s.ticker = '{ticker}'
        ORDER BY a.known_at DESC LIMIT {int(limit)}
    """)
    mood = query(f"""
        SELECT date, mood, headline_count FROM sentiment_daily
        WHERE ticker = '{ticker}' AND date <= DATE '{as_of}'
        ORDER BY date DESC LIMIT 60
    """)
    topics = query(f"""
        SELECT s.topic, count(*) AS n
        FROM news_scores s JOIN {visible('news_articles', as_of)} a ON a.id = s.article_id
        WHERE s.ticker = '{ticker}' GROUP BY 1 ORDER BY n DESC LIMIT 6
    """)
    return {
        "articles": [] if articles.empty else [{
            "date": str(r.known_at)[:10], "title": r.title, "url": r.url,
            "source": r.source, "topic": r.topic,
            "topic_label": topic_rules.label(r.topic),
            "relevance": float(r.relevance), "sentiment": float(r.sentiment),
        } for r in articles.itertuples()],
        "mood": [] if mood.empty else [
            {"date": str(r.date)[:10], "mood": round(float(r.mood), 3),
             "count": int(r.headline_count)}
            for r in mood.itertuples()][::-1],
        "topics": [] if topics.empty else [
            {"topic": r.topic, "label": topic_rules.label(r.topic), "n": int(r.n)}
            for r in topics.itertuples()],
    }