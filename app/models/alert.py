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


def _decode(rows: list[dict]) -> list[dict]:
    for r in rows:
        r["facts"] = json.loads(r["facts"]) if r.get("facts") else {}
        r["text"] = json.loads(r["text"]) if r.get("text") else {}
        r["analog_event_ids"] = json.loads(r["analog_event_ids"]) if r.get("analog_event_ids") else []
        r["as_of"] = str(r["as_of"])
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


def feedback_counts(portfolio_id: str) -> pd.DataFrame:
    return query("""SELECT f.vote, count(*) AS n FROM feedback f
                    WHERE f.alert_id LIKE ? GROUP BY 1""", [f"{portfolio_id}:%"])