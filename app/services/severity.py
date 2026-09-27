"""Severity: decide what deserves the user's attention, and assemble the
fact sheet the narrator is allowed to talk about.

Severity is expected impact on THIS portfolio, not drama in the market:

    impact = P(sharp drop) x weight in portfolio x how much this stock
             typically moves on this kind of event

A 12% crash in a 2% position matters less than a 4% wobble in a 30% one,
and that ordering is the whole point of the product. Thresholds are the
same for everyone so the wording stays comparable across portfolios.
"""
from __future__ import annotations

import json
import time
import uuid

import numpy as np
import pandas as pd

from app.models import alert as alert_model
from app.models import event as event_model
from app.models import evidence as evidence_model
from app.models import fingerprint as fingerprint_model
from app.models import portfolio as portfolio_model
from app.models import prediction as prediction_model
from app.models.base import query
from app.services import narrator
from config import get_config

cfg = get_config()

CATEGORY = {"earnings": "Earnings", "news": "News mood", "technical": "Technical",
            "cpi": "Macro", "fed": "Macro", "jobs": "Macro", "oil": "Macro"}
STORM, CHOPPY, HEADSUP = 0.006, 0.002, 0.0008


def _severity(impact: float, day_move: float) -> str:
    if impact > STORM or abs(day_move) > 0.10:
        return "Storm"
    if impact > CHOPPY or abs(day_move) > 0.04:
        return "Choppy"
    if impact > HEADSUP or abs(day_move) > 0.02:
        return "Heads-up"
    return "Calm"


def _sources(ticker: str, as_of: str, limit: int = 3) -> list[dict]:
    df = query(f"""SELECT a.title, a.url, a.source, round(s.relevance, 2) AS relevance
                   FROM news_scores s JOIN news_articles a ON a.id = s.article_id
                   WHERE s.ticker = '{ticker}'
                     AND CAST(a.known_at AS DATE) = DATE '{as_of}'
                   ORDER BY s.relevance DESC LIMIT {int(limit)}""")
    return [] if df.empty else df.to_dict("records")


def build(as_of: str, portfolio_id: str, use_llm: bool = True) -> list[dict]:
    hold = portfolio_model.valued(portfolio_id, as_of)
    if hold.empty:
        return []
    total = float(hold["value"].sum())

    # what this person has told us they care about
    weights_by_category = alert_model.category_weights(portfolio_id)
    todays = event_model.on_day(as_of)
    upcoming = event_model.upcoming(as_of, days=7, tickers=hold["ticker"].tolist())
    preds = prediction_model.latest(hold["ticker"].tolist(), as_of)
    how_counts: dict[str, int] = {}
    rows = []
    deadline = time.monotonic() + getattr(cfg, "NARRATION_BUDGET_SECONDS", 45)

    for h in hold.itertuples():
        t = h.ticker
        own = todays[todays["ticker"] == t] if not todays.empty else pd.DataFrame()
        macro = todays[todays["ticker"].isna()] if not todays.empty else pd.DataFrame()
        soon = upcoming[upcoming["ticker"] == t] if not upcoming.empty else pd.DataFrame()

        if not own.empty:
            ev = own.sort_values("surprise_z", key=lambda s: s.abs(), ascending=False).iloc[0]
            when = "today"
        elif not soon.empty:
            ev = soon.iloc[0]
            when = "coming up"
        elif not macro.empty:
            ev = macro.iloc[0]
            when = "today"
        else:
            continue

        etype = ev["type"]
        cell = fingerprint_model.cell(t, etype, as_of) or {}
        typical = float(cell.get("shrunk_move") or 0.03)
        baseline = float(cell.get("baseline_move") or typical)
        n_past = int(cell.get("n") or 0)

        p_row = preds[preds["ticker"] == t]
        p = float(p_row["p_drawdown"].iloc[0]) if len(p_row) else 0.10
        drivers = prediction_model.drivers_of(p_row.iloc[0]) if len(p_row) else []

        day_move = float(h.day_return) if not pd.isna(h.day_return) else 0.0
        weight = float(h.weight)
        raw_impact = p * weight * max(typical, abs(day_move))
        category = CATEGORY.get(etype, etype.title())
        taste = weights_by_category.get(category, 1.0)
        impact = raw_impact * taste
        severity = _severity(impact, day_move)

        analogs = evidence_model.analogs(
            as_of, t, etype,
            surprise_z=float(ev["surprise_z"]) if pd.notna(ev.get("surprise_z")) else None,
            ret20_before=None, k=5)

        facts = {
            "ticker": t,
            "as_of": as_of,
            "when": when,
            "category": category,
            "headline": str(ev["description"]),
            "day_move_pct": round(day_move * 100, 1),
            "weight_pct": round(weight * 100, 1),
            "position_usd": int(round(float(h.value))),
            "portfolio_impact_pct": round(day_move * weight * 100, 2),
            "risk_probability_pct": round(p * 100, 1),
            "typical_move_pct": round(typical * 100, 1),
            # the same figure in money: "3.1%" means nothing until it is
            # "$82 of yours", and the narrator must never multiply itself
            "typical_move_dollars": int(round(float(h.value) * typical)),
            "baseline_move_pct": round(baseline * 100, 1),
            "n_past": n_past,
            "drivers": [{"label": d["label"], "direction": d["direction"]} for d in drivers],
            "sources": _sources(t, as_of),
        }
        if not analogs.empty:
            facts["past_examples"] = [
                {"date": str(a.day0), "moved_pct": round(float(a.abnormal_ret) * 100, 1)}
                for a in analogs.itertuples() if pd.notna(a.abnormal_ret)
            ]

        # Past the budget we stop asking the model and store the alert
        # without prose. The next page load picks it up and writes it,
        # because unwritten alerts are treated as stale.
        within_budget = time.monotonic() < deadline
        text, how = (narrator.narrate(facts) if (use_llm and within_budget)
                     else (None, "skipped" if not use_llm else "out-of-time"))
        if text:
            # who wrote this, stored with the text itself. Without it we
            # cannot tell a model-written alert from one left over by an
            # older build, and stale rows never get rewritten.
            text = {**text, "_by": how, "_model": cfg.LLM_FAST}
        how_counts[how] = how_counts.get(how, 0) + 1
        # No text is a valid state: the screen shows the facts and says the
        # local model is not writing. Better an honest gap than prose that
        # pretends to be the model's.
        ok = bool(text) and narrator.grounded(" ".join(text.values()), facts)[0]

        rows.append({
            "id": f"{portfolio_id}:{uuid.uuid4().hex[:8]}",
            "as_of": as_of, "ticker": t, "severity": severity,
            "category": facts["category"],
            "facts": json.dumps(facts), "text": json.dumps(text) if text else None,
            "analog_event_ids": json.dumps(analogs["event_id"].tolist() if not analogs.empty else []),
            "grounded": bool(ok),
            "_impact": impact, "_how": how,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return []
    df = df.sort_values("_impact", ascending=False)
    alert_model.replace_for(as_of, portfolio_id, df.drop(columns=["_impact", "_how"]))
    return df.to_dict("records")