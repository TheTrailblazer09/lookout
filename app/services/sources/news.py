"""News from Alpha Vantage, cached to disk.

Why caching matters more than usual: the free tier is tightly rate-limited
(historically 25 requests a day). Every response is written to
data/news_cache/ and re-read from there, so a rate-limit error during your
demo cannot break anything you already fetched.

The endpoint gives us, per article: title, summary, url, source, published
time, an overall sentiment score, and a per-ticker relevance score. We keep
their relevance as one input, but compute our own novelty and (optionally)
our own sentiment, because "we score it locally" is a stronger claim than
"we read a vendor's number".
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

BASE = "https://www.alphavantage.co/query"
SOURCE_TIERS = {  # rough credibility, used as a feature
    "reuters": 1, "bloomberg": 1, "associated press": 1, "wall street journal": 1,
    "cnbc": 2, "barron's": 2, "financial times": 1, "marketwatch": 2,
    "benzinga": 3, "zacks": 3, "motley fool": 3, "seeking alpha": 3,
}


def _tier(source: str) -> int:
    s = (source or "").lower()
    for name, tier in SOURCE_TIERS.items():
        if name in s:
            return tier
    return 3


def _cache_path(cache_dir: Path, params: dict) -> Path:
    key = hashlib.sha1(json.dumps(params, sort_keys=True).encode()).hexdigest()[:16]
    return cache_dir / f"news_{key}.json"


def fetch_raw(api_key: str, tickers: list[str], cache_dir: Path,
              time_from: str | None = None, time_to: str | None = None,
              limit: int = 1000, pause: float = 1.0, refresh: bool = False) -> list[dict]:
    """One request per ticker (their tickers= filter is OR, but per-ticker
    keeps the cache useful and the relevance mapping clean)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    feed: list[dict] = []
    for t in tickers:
        params = {"function": "NEWS_SENTIMENT", "tickers": t,
                  "limit": limit, "sort": "LATEST"}
        if time_from:
            params["time_from"] = time_from
        if time_to:
            params["time_to"] = time_to
        path = _cache_path(cache_dir, params)

        if path.exists() and not refresh:
            payload = json.loads(path.read_text())
        else:
            url = f"{BASE}?{urllib.parse.urlencode({**params, 'apikey': api_key})}"
            try:
                with urllib.request.urlopen(url, timeout=30) as r:
                    payload = json.loads(r.read())
            except urllib.error.HTTPError as err:
                print(f"  ! {t}: HTTP {err.code}")
                continue
            except Exception as exc:  # noqa: BLE001
                print(f"  ! {t}: {exc}")
                continue
            # Alpha Vantage reports limits in the body with a 200 status
            if "Information" in payload or "Note" in payload:
                print(f"  ! {t}: {payload.get('Information') or payload.get('Note')}")
                continue
            path.write_text(json.dumps(payload))
            time.sleep(pause)

        for item in payload.get("feed", []):
            feed.append({**item, "_queried_ticker": t})
    return feed


def to_frames(feed: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split the raw feed into (articles, per-ticker mentions+scores)."""
    articles: dict[str, dict] = {}
    mentions: list[dict] = []
    for item in feed:
        url = item.get("url")
        if not url:
            continue
        aid = hashlib.sha1(url.encode()).hexdigest()[:16]
        published = item.get("time_published")  # 20260926T133000
        try:
            when = pd.to_datetime(published, format="%Y%m%dT%H%M%S")
        except (ValueError, TypeError):
            continue
        source = item.get("source", "")
        title = (item.get("title") or "").strip()
        if aid not in articles:
            articles[aid] = {
                "id": aid, "url": url, "source": source, "source_tier": _tier(source),
                "published_at": when, "known_at": when,
                "title": title, "summary": (item.get("summary") or "").strip(),
                "body": None,
                # cluster by title shape: syndicated copies share a headline
                "cluster_id": hashlib.sha1(title.lower().encode()).hexdigest()[:16],
            }
        for ts in item.get("ticker_sentiment", []):
            sym = ts.get("ticker")
            if not sym:
                continue
            try:
                mentions.append({
                    "article_id": aid, "ticker": sym,
                    "entity_score": float(ts.get("relevance_score", 0)),
                    "vendor_sentiment": float(ts.get("ticker_sentiment_score", 0)),
                    "title": title,
                    "known_at": when,
                })
            except (TypeError, ValueError):
                continue

    return (pd.DataFrame(articles.values()),
            pd.DataFrame(mentions).drop_duplicates(subset=["article_id", "ticker"]))