"""News bot: store every article, score it, and raise an event only when
the day's coverage is genuinely unusual for that stock.

Four scores per article per ticker:

  entity    how central the company is to the story (Alpha Vantage's
            relevance, which is a decent proxy for "is this really about
            them or a passing mention")
  novelty   1 minus similarity to that ticker's headlines in the previous
            72 hours. Syndication means the same story arrives ten times;
            without this, a single event would look like a news storm.
  sentiment tone, -1 to +1. FinBERT when it's installed, otherwise the
            vendor's score, recorded either way in model_version so you
            can say which ran.
  relevance the combined score, currently a transparent weighted blend.
            The PRD's trained version replaces this function and nothing
            else has to change.

Daily mood is then a relevance-weighted average, so one front-page story
outweighs twenty copies of a blog post. An event fires when the day's mood
is far from that stock's own normal mood and at least one high-relevance
article is behind it.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from app.models import event as event_model
from app.models.base import execute, insert_df, query
from config import get_config

cfg = get_config()
MODEL_VERSION_RULE = "relevance-rule-v1"
MOOD_Z = 1.8            # how far from normal a day's mood must be
MIN_RELEVANCE = 0.45    # at least one article this relevant behind an event
_WORD = re.compile(r"[a-z0-9]+")


def _tokens(title: str) -> set[str]:
    return set(_WORD.findall((title or "").lower()))


def _novelty(title: str, prior_titles: list[str]) -> float:
    """1.0 = nothing like it recently; 0.0 = a duplicate."""
    t = _tokens(title)
    if not t or not prior_titles:
        return 1.0
    best = 0.0
    for other in prior_titles:
        o = _tokens(other)
        if not o:
            continue
        overlap = len(t & o) / len(t | o)      # Jaccard
        best = max(best, overlap)
    return float(1.0 - best)


def _finbert_scores(titles: list[str]):
    """Local sentiment if transformers is installed; None otherwise."""
    try:
        from transformers import pipeline
    except ImportError:
        return None
    try:
        clf = pipeline("sentiment-analysis", model=cfg.FINBERT_MODEL, truncation=True)
    except Exception as exc:  # noqa: BLE001 - model not downloaded, no torch, etc.
        print(f"  ! FinBERT unavailable ({exc}); using vendor sentiment")
        return None
    out = []
    for i in range(0, len(titles), 32):
        for r in clf(titles[i:i + 32]):
            label = r["label"].lower()
            score = float(r["score"])
            out.append(score if label == "positive" else -score if label == "negative" else 0.0)
    return out


def score(articles: pd.DataFrame, mentions: pd.DataFrame,
          use_finbert: bool = True) -> pd.DataFrame:
    """Turn raw articles + mentions into news_scores rows."""
    if mentions.empty:
        return pd.DataFrame()

    m = mentions.sort_values("known_at").reset_index(drop=True)

    local = _finbert_scores(m["title"].tolist()) if use_finbert else None
    model_version = MODEL_VERSION_RULE + ("+finbert" if local else "+vendor")

    rows = []
    for ticker, chunk in m.groupby("ticker"):
        chunk = chunk.sort_values("known_at")
        titles, times = [], []
        for pos, r in enumerate(chunk.itertuples()):
            cutoff = r.known_at - pd.Timedelta(hours=72)
            prior = [ti for ti, tm in zip(titles, times) if tm >= cutoff]
            nov = _novelty(r.title, prior)
            titles.append(r.title)
            times.append(r.known_at)

            sent = local[r.Index] if local else float(r.vendor_sentiment)
            ent = float(r.entity_score)
            # transparent blend; the trained model replaces exactly this line
            relevance = float(np.clip(0.55 * ent + 0.25 * nov + 0.20 * min(abs(sent) * 2, 1), 0, 1))
            rows.append({
                "article_id": r.article_id, "ticker": ticker,
                "entity_score": ent, "topic": "company", "topic_conf": 0.0,
                "novelty": nov, "sentiment": sent, "relevance": relevance,
                "model_version": model_version,
            })
    return pd.DataFrame(rows)


def store(articles: pd.DataFrame, scores: pd.DataFrame) -> dict:
    """Write articles, scores, and the relevance-weighted daily mood."""
    if articles.empty:
        return {"articles": 0, "scores": 0, "mood_days": 0}

    ids = ", ".join(f"'{i}'" for i in articles["id"].tolist())
    execute(f"DELETE FROM news_articles WHERE id IN ({ids})")
    execute(f"DELETE FROM news_scores WHERE article_id IN ({ids})")
    n_articles = insert_df("news_articles", articles[[
        "id", "url", "source", "source_tier", "published_at", "known_at",
        "title", "summary", "body", "cluster_id"]])
    n_scores = insert_df("news_scores", scores[[
        "article_id", "ticker", "entity_score", "topic", "topic_conf",
        "novelty", "sentiment", "relevance", "model_version"]]) if not scores.empty else 0

    mood = _daily_mood()
    return {"articles": n_articles, "scores": n_scores, "mood_days": mood}


def _daily_mood() -> int:
    df = query("""
        SELECT s.ticker,
               CAST(a.known_at AS DATE) AS date,
               s.sentiment, s.relevance, s.article_id
        FROM news_scores s JOIN news_articles a ON a.id = s.article_id
    """)
    if df.empty:
        return 0
    out = []
    for (ticker, date), chunk in df.groupby(["ticker", "date"]):
        w = chunk["relevance"].to_numpy()
        w = w if w.sum() > 0 else np.ones_like(w)
        top = chunk.nlargest(3, "relevance")["article_id"].tolist()
        out.append({"ticker": ticker, "date": date,
                    "mood": float(np.average(chunk["sentiment"], weights=w)),
                    "headline_count": int(len(chunk)),
                    "top_article_ids": ",".join(top)})
    frame = pd.DataFrame(out)
    execute("DELETE FROM sentiment_daily")
    return insert_df("sentiment_daily", frame)


def detect(as_of: str, lookback_days: int = 30) -> pd.DataFrame:
    """Raise an event when a day's mood is unusual for that stock."""
    mood = query("SELECT * FROM sentiment_daily ORDER BY ticker, date")
    if mood.empty:
        return pd.DataFrame()
    mood["date"] = pd.to_datetime(mood["date"])
    cutoff = pd.Timestamp(as_of)
    window_start = cutoff - pd.Timedelta(days=lookback_days)

    rows = []
    for ticker, chunk in mood.groupby("ticker"):
        chunk = chunk[chunk["date"] <= cutoff].sort_values("date")
        if len(chunk) < 10:
            continue
        # normal mood measured on history BEFORE each day
        mean = chunk["mood"].expanding().mean().shift(1)
        sd = chunk["mood"].expanding().std().shift(1)
        z = (chunk["mood"] - mean) / sd.replace(0, np.nan)
        for row, zz in zip(chunk.itertuples(), z):
            if pd.isna(zz) or abs(zz) < MOOD_Z or row.date < window_start:
                continue
            day = row.date.date()
            best = query(f"""SELECT max(relevance) AS r FROM news_scores s
                             JOIN news_articles a ON a.id = s.article_id
                             WHERE s.ticker = '{ticker}'
                               AND CAST(a.known_at AS DATE) = DATE '{day}'""")["r"][0]
            if best is None or float(best) < MIN_RELEVANCE:
                continue  # a mood swing with no substantial story behind it
            direction = "positive" if zz > 0 else "negative"
            rows.append({
                "id": f"news-{ticker}-{day}",
                "ticker": ticker, "type": "news", "subtype": direction[:3],
                "known_at": pd.Timestamp(day) + pd.Timedelta(hours=9),
                "day0": day, "value": float(row.mood), "surprise_z": float(zz),
                "source": "news-bot",
                "description": (f"{ticker}: unusually {direction} coverage "
                                f"({row.headline_count} stories, "
                                f"{abs(zz):.1f}x its normal mood swing)"),
            })
    return pd.DataFrame(rows)


def run(as_of: str, lookback_days: int = 30) -> int:
    df = detect(as_of, lookback_days)
    return event_model.upsert(df) if not df.empty else 0