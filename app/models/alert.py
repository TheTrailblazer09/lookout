"""Alerts: the generated cards a user actually reads."""
from __future__ import annotations

import json

import pandas as pd

from app.models.base import execute, insert_df, query

COLUMNS = ["id", "as_of", "ticker", "severity", "category", "facts", "text",
           "analog_event_ids", "grounded"]
ORDER = {"Storm": 0, "Choppy": 1, "Heads-up": 2, "Calm": 3}


def replace_for(as_of: str, portfolio_id: str, df: pd.DataFrame) -> int:
    """Alert ids are prefixed with the portfolio, so one user's rebuild
    never clears another's."""
    execute("DELETE FROM alerts WHERE as_of = CAST(? AS DATE) AND id LIKE ?",
            [as_of, f"{portfolio_id}:%"])
    return insert_df("alerts", df.reindex(columns=COLUMNS)) if not df.empty else 0


def written_by_model(alert: dict) -> bool:
    """True only for text a local model actually produced in this build.

    Rows from earlier versions carry no marker, so they count as stale and
    get rewritten once a model is available.
    """
    text = alert.get("text") or {}
    return str(text.get("_by", "")).startswith("llm")


def _decode(rows: list[dict]) -> list[dict]:
    for r in rows:
        r["facts"] = json.loads(r["facts"]) if r.get("facts") else {}
        # None means the local model did not write this one
        r["text"] = json.loads(r["text"]) if r.get("text") else None
        r["analog_event_ids"] = json.loads(r["analog_event_ids"]) if r.get("analog_event_ids") else []
        # DuckDB hands back a Timestamp; callers build date strings from
        # this, so trim the time component here rather than everywhere.
        r["as_of"] = str(r["as_of"])[:10]
    return rows


def for_day(as_of: str, portfolio_id: str, category: str | None = None) -> list[dict]:
    extra = " AND category = ?" if category else ""
    params = [as_of, f"{portfolio_id}:%"] + ([category] if category else [])
    df = query(f"""SELECT * FROM alerts
                   WHERE as_of = CAST(? AS DATE) AND id LIKE ?{extra}""", params)
    rows = _decode(df.to_dict("records"))
    return sorted(rows, key=lambda r: ORDER.get(r["severity"], 9))


def by_id(alert_id: str) -> dict | None:
    df = query("SELECT * FROM alerts WHERE id = ?", [alert_id])
    if df.empty:
        return None
    return _decode(df.to_dict("records"))[0]


def save_feedback(alert_id: str, vote: str) -> None:
    execute("INSERT INTO feedback VALUES (?, ?, now())", [alert_id, vote])


def category_weights(portfolio_id: str) -> dict[str, float]:
    """How much this person cares about each kind of alert, learned from
    their votes.

    Each "useful" nudges that category up, each "less like this" nudges it
    down, and the effect is capped so a couple of clicks tilt the ranking
    without ever silencing a category outright — someone who dismisses two
    macro alerts should see fewer of them, not go blind to the Fed.
    """
    df = query("""
        SELECT a.category, f.vote, count(*) AS n
        FROM feedback f JOIN alerts a ON a.id = f.alert_id
        WHERE f.alert_id LIKE ?
        GROUP BY 1, 2
    """, [f"{portfolio_id}:%"])
    if df.empty:
        return {}
    weights: dict[str, float] = {}
    for row in df.itertuples():
        step = 0.15 * int(row.n) * (1 if row.vote == "useful" else -1)
        weights[row.category] = weights.get(row.category, 1.0) + step
    # 0.5x to 1.6x: a strong steer, never a mute button
    return {k: max(0.5, min(1.6, v)) for k, v in weights.items()}


def feedback_counts(portfolio_id: str) -> pd.DataFrame:
    return query("""SELECT f.vote, count(*) AS n FROM feedback f
                    WHERE f.alert_id LIKE ? GROUP BY 1""", [f"{portfolio_id}:%"])