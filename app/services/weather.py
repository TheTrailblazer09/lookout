"""The weather report: the forces that push every holding at once.

The number that matters here is **exposure**: not "is inflation high", but
"how hard do inflation surprises push THIS portfolio". That comes from the
fingerprint — each stock's measured reaction to each macro event type,
weighted by how much of the portfolio it is, and compared against what an
ordinary stretch looks like for the same stock.

So a portfolio of rate-sensitive tech and one of steady staples can look at
the same Fed meeting and get different answers, which is the whole point.
"""
from __future__ import annotations

import numpy as np

from app.models import event as event_model
from app.models import fingerprint as fingerprint_model
from app.models import indicator as indicator_model
from app.services import portfolio_math

# macro event types, in the order a person cares about them
MACRO = [
    ("fed", "Interest rates", "What the Fed does with rates"),
    ("cpi", "Inflation surprises", "Whether prices rose faster than expected"),
    ("jobs", "Jobs data", "How many people are working"),
    ("oil", "Oil prices", "The cost of energy"),
]

# how a ratio of event-day movement to an ordinary stretch reads in words
def _level(ratio: float) -> tuple[str, int]:
    if ratio >= 1.35:
        return "High", 3
    if ratio >= 1.12:
        return "Medium", 2
    return "Low", 1


def build(portfolio_id: str, as_of: str) -> dict:
    stats = portfolio_math.analyze(portfolio_id, as_of)
    if stats.get("empty"):
        return {"empty": True}

    weights = stats["weights"]
    exposure = _exposure(weights, as_of)
    upcoming = _upcoming(as_of, list(weights), exposure)

    return {
        "empty": False,
        "as_of": as_of,
        "exposure": exposure,
        "upcoming": upcoming,
        "indicators": _indicators(as_of),
        "facts": _facts(stats, exposure, upcoming),
    }


def _exposure(weights: dict, as_of: str) -> list[dict]:
    """How hard each macro force pushes this particular portfolio."""
    out = []
    for etype, label, plain in MACRO:
        contributions: list[tuple[str, float, float]] = []
        for ticker, weight in weights.items():
            cell = fingerprint_model.cell(ticker, etype, as_of)
            if not cell or not cell.get("baseline_move"):
                continue
            ratio = float(cell["shrunk_move"]) / float(cell["baseline_move"])
            contributions.append((ticker, weight, ratio))
        if not contributions:
            out.append({"type": etype, "label": label, "plain": plain,
                        "level": "Unknown", "score": 0, "ratio": None,
                        "why": "Lookout has not measured enough of these yet.",
                        "drivers": []})
            continue

        total_w = sum(c[1] for c in contributions)
        ratio = sum(c[1] * c[2] for c in contributions) / total_w
        level, score = _level(ratio)
        # who is actually responsible for that exposure
        drivers = sorted(contributions, key=lambda c: -(c[1] * (c[2] - 1)))[:2]
        driver_txt = ", ".join(d[0] for d in drivers if d[2] > 1.05)

        if level == "Low":
            why = (f"On days like these your holdings move about as much as they do on any "
                   f"other day ({ratio:.2f}× an ordinary stretch).")
        else:
            why = (f"Your mix moves about {ratio:.2f}× its ordinary amount on these days"
                   + (f", mostly through {driver_txt}." if driver_txt else "."))

        out.append({
            "type": etype, "label": label, "plain": plain,
            "level": level, "score": score, "ratio": round(ratio, 2),
            "why": why,
            "drivers": [{"ticker": d[0], "weight_pct": round(d[1], 1), "ratio": round(d[2], 2)}
                        for d in drivers],
        })
    return out


def _upcoming(as_of: str, tickers: list[str], exposure: list[dict]) -> list[dict]:
    """Scheduled events ahead, tagged with how much they matter here."""
    by_type = {e["type"]: e for e in exposure}
    # monthly releases can be five weeks out; a three-week window misses them
    df = event_model.upcoming(as_of, days=38, tickers=tickers)
    if df.empty:
        return []

    rows = []
    for e in df.itertuples():
        etype = e.type
        is_macro = etype in by_type
        exp = by_type.get(etype)
        if is_macro:
            level = exp["level"] if exp else "Unknown"
            why = exp["why"] if exp else ""
            title = {"fed": "Fed rate decision", "cpi": "Inflation reading",
                     "jobs": "Jobs report", "oil": "Oil market update"}.get(etype, etype.upper())
        else:
            # a company event: size it by how much of the portfolio it is
            level = "High" if etype == "earnings" else "Medium"
            title = f"{e.ticker} {etype}"
            why = str(e.description)
        rows.append({
            "date": str(e.day0)[:10],
            "type": etype,
            "ticker": e.ticker if isinstance(e.ticker, str) else None,
            "title": title,
            "level": level,
            "why": why,
        })
    # one row per day per type keeps a busy week readable
    seen = set()
    unique = []
    for r in rows:
        key = (r["date"], r["type"], r["ticker"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)
    return unique[:8]


def _indicators(as_of: str) -> list[dict]:
    df = indicator_model.latest(as_of)
    if df.empty:
        return []
    out = []
    for r in df.itertuples():
        change = None
        if r.prev_value not in (None, 0) and not np.isnan(r.prev_value):
            change = float(r.value) - float(r.prev_value)
        out.append({
            "series_id": r.series_id,
            "label": r.label,
            "value": round(float(r.value), 2),
            "change": round(change, 2) if change is not None else None,
            "as_of_date": str(r.date)[:10],
            "history": [round(v, 3) for v in indicator_model.history(r.series_id, as_of)],
        })
    return out


def _facts(stats: dict, exposure: list[dict], upcoming: list[dict]) -> dict:
    """The fact sheet the local model is allowed to write from."""
    ranked = [e for e in exposure if e["ratio"]]
    ranked.sort(key=lambda e: -e["ratio"])
    facts = {
        "holdings": len(stats.get("weights", {})),
        "volatility_pct": round(stats.get("volatility_pct", 0), 1),
        "beta": round(float(stats.get("beta") or 0), 2),
        "day_move_pct": round(stats.get("day_change_pct", 0), 2),
    }
    if ranked:
        top = ranked[0]
        facts["biggest_exposure"] = {"label": top["label"], "ratio": top["ratio"],
                                     "level": top["level"]}
    if upcoming:
        facts["next_event"] = {"title": upcoming[0]["title"], "date": upcoming[0]["date"],
                               "level": upcoming[0]["level"]}
    return facts