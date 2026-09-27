"""Per-stock: price history, fingerprint, and the evidence behind it."""
import numpy as np
from flask import Blueprint, jsonify, request

from app.models import evidence as evidence_model
from app.models import fingerprint as fingerprint_model
from app.models import price as price_model
from app.models.base import query
from app.services import auth as auth_service
from app.services import stock_detail
from app.services.bots import topics as topic_rules
from app.utils.errors import ApiError
from config import get_config

cfg = get_config()
bp = Blueprint("stocks", __name__, url_prefix="/stocks")


def _clean(df, cols=None):
    """DataFrame -> JSON-safe records (NaN is not valid JSON)."""
    if df is None or df.empty:
        return []
    out = df[cols] if cols else df
    return out.replace({np.nan: None}).to_dict("records")


@bp.get("/<ticker>/detail")
@auth_service.optional_auth
def detail(ticker):
    """Everything the holdings page needs about one stock, in one call."""
    as_of = request.args.get("as_of") or cfg.default_as_of()
    days = int(request.args.get("days", 260))
    data = stock_detail.build(auth_service.portfolio_id(), ticker, as_of, days)
    if data.get("empty"):
        raise ApiError(f"No price history for {ticker.upper()}", 404)
    return jsonify(data)


@bp.get("/<ticker>/prices")
def prices(ticker):
    as_of = request.args.get("as_of") or cfg.default_as_of()
    days = int(request.args.get("days", 260))
    # fetch extra history so the 50-day average is defined on the first
    # day we actually return, then trim
    df = price_model.history([ticker], as_of, lookback_days=int(days * 1.5) + 120)
    if df.empty:
        raise ApiError(f"No price history for {ticker.upper()}", 404)
    df = df.copy()
    df["ma50"] = df["adj_close"].rolling(50, min_periods=10).mean().round(2)
    df = df.tail(days)
    df["date"] = df["date"].astype(str)
    df["adj_close"] = df["adj_close"].round(2)
    return jsonify(ticker=ticker.upper(), as_of=as_of,
                   prices=_clean(df, ["date", "adj_close", "ma50", "volume"]))


@bp.get("/<ticker>/fingerprint")
def fingerprint(ticker):
    as_of = request.args.get("as_of") or cfg.default_as_of()
    df = fingerprint_model.for_ticker(ticker, as_of)
    if df.empty:
        return jsonify(ticker=ticker.upper(), as_of=as_of, cells=[],
                       message="No fingerprint yet. Run `flask build`.")
    for col in ("typical_move", "baseline_move", "shrunk_move", "ci_low", "ci_high"):
        df[col + "_pct"] = (df[col] * 100).round(2)
    df["share_up_pct"] = (df["share_up"] * 100).round(0)
    cols = ["event_type", "direction", "n", "typical_move_pct", "baseline_move_pct",
            "shrunk_move_pct", "ci_low_pct", "ci_high_pct", "share_up_pct", "reliable"]
    return jsonify(ticker=ticker.upper(), as_of=as_of, cells=_clean(df, cols))


@bp.get("/<ticker>/evidence")
def evidence(ticker):
    as_of = request.args.get("as_of") or cfg.default_as_of()
    df = evidence_model.for_display(as_of, ticker, request.args.get("event_type"),
                                    int(request.args.get("limit", 25)))
    if df.empty:
        return jsonify(ticker=ticker.upper(), as_of=as_of, events=[])
    df = df.copy()
    df["day0"] = df["day0"].astype(str)
    for col in ("stock_ret", "market_ret", "abnormal_ret"):
        df[col + "_pct"] = (df[col] * 100).round(2)
    df["surprise_z"] = df["surprise_z"].round(2)
    df["how_unusual"] = df["move_z"].round(2)
    cols = ["day0", "event_type", "subtype", "description", "surprise_z",
            "stock_ret_pct", "market_ret_pct", "abnormal_ret_pct", "how_unusual"]
    return jsonify(ticker=ticker.upper(), as_of=as_of, events=_clean(df, cols))


@bp.get("/<ticker>/fingerprint/history")
def fingerprint_history(ticker):
    event_type = request.args.get("event_type", "earnings")
    df = fingerprint_model.history(ticker, event_type)
    if df.empty:
        return jsonify(ticker=ticker.upper(), event_type=event_type, snapshots=[])
    df = df.copy()
    df["as_of"] = df["as_of"].astype(str)
    for col in ("shrunk_move", "ci_low", "ci_high"):
        df[col + "_pct"] = (df[col] * 100).round(2)
    return jsonify(ticker=ticker.upper(), event_type=event_type,
                   snapshots=_clean(df, ["as_of", "n", "shrunk_move_pct",
                                         "ci_low_pct", "ci_high_pct", "reliable"]))


@bp.get("/<ticker>/news")
def news(ticker):
    """Recent articles, most relevant first, each with its topic."""
    as_of = request.args.get("as_of") or cfg.default_as_of()
    min_rel = float(request.args.get("min_relevance", 0.4))
    topic = request.args.get("topic")
    extra = f" AND s.topic = '{topic}'" if topic else ""
    df = query(f"""
        SELECT a.known_at, a.title, a.url, a.source, s.topic,
               round(s.relevance, 2) AS relevance,
               round(s.sentiment, 2) AS sentiment,
               round(s.novelty, 2) AS novelty
        FROM news_scores s JOIN news_articles a ON a.id = s.article_id
        WHERE s.ticker = '{ticker.upper()}'
          AND a.known_at <= TIMESTAMP '{as_of} 23:59:59'
          AND s.relevance >= {min_rel}{extra}
        ORDER BY a.known_at DESC LIMIT {int(request.args.get('limit', 25))}
    """)
    if df.empty:
        return jsonify(ticker=ticker.upper(), as_of=as_of, articles=[])
    df = df.copy()
    df["known_at"] = df["known_at"].astype(str)
    df["topic_label"] = df["topic"].map(topic_rules.label)
    return jsonify(ticker=ticker.upper(), as_of=as_of, articles=_clean(df))


@bp.get("/<ticker>/news/topics")
def news_topics(ticker):
    """What kinds of news this stock gets, and how it reacts to each."""
    as_of = request.args.get("as_of") or cfg.default_as_of()
    counts = query(f"""
        SELECT s.topic, count(*) AS articles, round(avg(s.sentiment), 2) AS avg_sentiment
        FROM news_scores s JOIN news_articles a ON a.id = s.article_id
        WHERE s.ticker = '{ticker.upper()}'
          AND a.known_at <= TIMESTAMP '{as_of} 23:59:59'
        GROUP BY 1 ORDER BY articles DESC
    """)
    moves = query(f"""
        SELECT subtype AS topic, count(*) AS events,
               round(avg(abs(abnormal_ret)) * 100, 2) AS typical_move_pct
        FROM evidence
        WHERE ticker = '{ticker.upper()}' AND event_type = 'news' AND included
          AND outcome_known_at <= TIMESTAMP '{as_of} 23:59:59'
        GROUP BY 1
    """)
    if counts.empty:
        return jsonify(ticker=ticker.upper(), as_of=as_of, topics=[])
    merged = counts.merge(moves, on="topic", how="left")
    merged["label"] = merged["topic"].map(topic_rules.label)
    return jsonify(ticker=ticker.upper(), as_of=as_of, topics=_clean(merged))