"""Ideas for the "Chart a course" page.

Every idea is derived from something measurable about this portfolio and
the rules the person set in onboarding. Nothing is generic advice: if
Lookout cannot point at a number, it does not raise the idea.

Two deliberate limits:

  - Ideas are framed as questions about *position size and shape*, never
    as "buy this" or "sell that". Telling a specific person to trade a
    specific stock is investment advice, which needs a licence; telling
    them "this is 40% of your money and your own rule says 25%" is just
    reading their portfolio back to them.
  - Every idea carries what could go wrong. An idea without a stated
    downside is a sales pitch.
"""
from __future__ import annotations

import numpy as np

from app.models import event as event_model
from app.models import fingerprint as fingerprint_model
from app.models import preference as preference_model
from app.services import portfolio_math

# how strongly each idea usually fits, before portfolio-specific tuning
BASE_FIT = {"trim": 4, "diversify": 3, "cushion": 3, "steady": 3, "hold": 4, "review": 3}


def _pct(x: float) -> float:
    return round(float(x), 1)


def build(portfolio_id: str, as_of: str) -> dict:
    stats = portfolio_math.analyze(portfolio_id, as_of)
    if stats.get("empty"):
        return {"empty": True, "ideas": [], "compass": {}, "explore": []}

    prefs = preference_model.get(portfolio_id)
    weights = stats["weights"]
    risk = stats["risk_share"]
    corr = stats["correlation"]
    limit = float(prefs.get("concentration_limit_pct", 25))

    ideas: list[dict] = []
    ranked = sorted(weights.items(), key=lambda kv: -kv[1])
    top_ticker, top_weight = ranked[0]

    # --- 1. one position past the limit the person set themselves --------
    over = [(t, w) for t, w in ranked if w > limit]
    for t, w in over[:2]:
        risk_share = risk.get(t, 0)
        ideas.append({
            "id": f"trim-{t}",
            "kind": "Rebalance",
            "ticker": t,
            "title": f"{t} is past the size limit you set",
            "fit": BASE_FIT["trim"] + (1 if risk_share > w + 8 else 0),
            "reasons": [
                {"text": f"{t} is {_pct(w)}% of your money; your own limit is {_pct(limit)}%.",
                 "source": "your rules"},
                {"text": f"It causes {_pct(risk_share)}% of your portfolio's bumpiness.",
                 "source": "risk contribution"},
                {"text": "Bringing it back to the limit in steps avoids acting on one day's price.",
                 "source": "Lookout"},
            ],
            "risk": (f"If {t} keeps rising you will own less of it. Selling shares that have "
                     "gained may also mean tax — your broker can show what you would owe."),
            "effect": f"{t} moves from {_pct(w)}% to {_pct(limit)}%, and the rest scales up to fill the gap.",
            "change": {t: limit},
        })

    # --- 2. holdings that all move together ------------------------------
    cluster = _tightest_cluster(corr, weights)
    if cluster:
        members, avg_corr, share = cluster
        ideas.append({
            "id": "diversify-cluster",
            "kind": "Diversify",
            "ticker": "+".join(members[:3]),
            "title": "Several holdings move as one",
            "fit": BASE_FIT["diversify"] + (1 if share > 50 else 0),
            "reasons": [
                {"text": f"{', '.join(members)} move together (average correlation {avg_corr:.2f}).",
                 "source": "correlation"},
                {"text": f"Together they are {_pct(share)}% of your portfolio.",
                 "source": "your holdings"},
                {"text": "When they fall they tend to fall on the same day, so the rest cushions little.",
                 "source": "Lookout"},
            ],
            "risk": ("Spreading out can mean owning less of what has done well. Diversifying "
                     "reduces swings, not the chance of losing money."),
            "effect": f"Trimming the largest of them to {_pct(limit)}% loosens how tightly your portfolio moves as one.",
            "change": {members[0]: min(limit, weights[members[0]])},
        })

    # --- 3. a stock carrying far more risk than money --------------------
    gaps = sorted(((t, risk.get(t, 0) - w) for t, w in weights.items()), key=lambda x: -x[1])
    if gaps and gaps[0][1] > 8:
        t, gap = gaps[0]
        ideas.append({
            "id": f"review-{t}",
            "kind": "Take a look",
            "ticker": t,
            "title": f"{t} punches above its weight",
            "fit": BASE_FIT["review"],
            "reasons": [
                {"text": f"{t} is {_pct(weights[t])}% of your money but {_pct(risk.get(t, 0))}% of the bumpiness.",
                 "source": "risk contribution"},
                {"text": f"That gap is {_pct(gap)} points — the widest in your portfolio.",
                 "source": "risk contribution"},
            ],
            "risk": "A jumpy stock is not a bad stock. This is about how much of the ride it owns.",
            "effect": f"Halving the gap would take {t} to about {_pct(max(1.0, weights[t] * 0.7))}%.",
            "change": {t: round(max(1.0, weights[t] * 0.7), 1)},
        })

    # --- 4. a steady holding worth leaning on ----------------------------
    # never a holding we just asked them to trim: suggesting "own less of
    # this" and "lean on this" in the same list reads as noise
    flagged = {t for t, _ in over} | {i["ticker"] for i in ideas}
    steady = _steadiest(weights, risk, exclude=flagged)
    if steady:
        t, w, r = steady
        ideas.append({
            "id": f"steady-{t}",
            "kind": "Cushion",
            "ticker": t,
            "title": f"{t} is doing the cushioning",
            "fit": BASE_FIT["steady"],
            "reasons": [
                {"text": f"{t} is {_pct(w)}% of your money but only {_pct(r)}% of the bumpiness.",
                 "source": "risk contribution"},
                {"text": "Holdings like this soften the days when everything else falls.",
                 "source": "Lookout"},
            ],
            "risk": "Steady usually means slower growth. More of it calms the ride, not speeds it up.",
            "effect": f"Raising {t} to {_pct(min(limit, w + 5))}% lowers your overall swings.",
            "change": {t: round(min(limit, w + 5), 1)},
        })

    # --- 5. hold through a drop, when nothing has actually broken --------
    worst = _worst_recent(weights, as_of)
    if worst:
        t, move = worst
        cell = fingerprint_model.cell(t, "earnings", as_of) or {}
        reasons = [
            {"text": f"{t} moved {_pct(move)}% recently, which looks dramatic on a chart.",
             "source": "daily prices"},
        ]
        if cell.get("n"):
            reasons.append({
                "text": (f"Across {int(cell['n'])} past earnings events it typically moved "
                         f"{_pct(cell['shrunk_move'] * 100)}%, against "
                         f"{_pct(cell['baseline_move'] * 100)}% in an ordinary stretch."),
                "source": "fingerprint",
            })
        reasons.append({"text": "Nothing in your rules is broken by this move alone.",
                        "source": "your rules"})
        ideas.append({
            "id": f"hold-{t}",
            "kind": "Stay put",
            "ticker": t,
            "title": f"A move in {t} is not by itself a reason to act",
            "fit": BASE_FIT["hold"],
            "reasons": reasons,
            "risk": "If the reason you bought it has changed, sitting still is its own decision.",
            "effect": "Nothing changes today.",
            "change": None,
        })

    ideas.sort(key=lambda i: -i["fit"])
    return {
        "empty": False,
        "as_of": as_of,
        "compass": {
            "concentration_limit_pct": limit,
            "sector_limit_pct": prefs.get("sector_limit_pct"),
            "sensitivity": prefs.get("sensitivity"),
            "bots": prefs.get("bots"),
            "broken": [{"rule": f"No single stock above {_pct(limit)}%",
                        "by": t, "value": _pct(w)} for t, w in over],
        },
        "today": _snapshot(stats, limit),
        "ideas": ideas,
    }


def simulate(portfolio_id: str, as_of: str, idea_ids: list[str]) -> dict:
    """What the portfolio's numbers become if these ideas were acted on."""
    plan = build(portfolio_id, as_of)
    if plan.get("empty"):
        return {"empty": True}

    chosen = [i for i in plan["ideas"] if i["id"] in set(idea_ids) and i.get("change")]
    changes: dict[str, float] = {}
    for idea in chosen:
        for ticker, target in idea["change"].items():
            # if two ideas touch the same holding, the smaller target wins:
            # acting on both should not undo either
            changes[ticker] = min(target, changes.get(ticker, target))

    after = portfolio_math.metrics_for_changes(portfolio_id, as_of, changes)
    limit = plan["compass"]["concentration_limit_pct"]
    return {
        "empty": False,
        "applied": [i["id"] for i in chosen],
        "before": plan["today"],
        "after": _snapshot(after, limit) if not after.get("empty") else None,
    }


def _snapshot(stats: dict, limit: float) -> dict:
    weights = stats.get("weights", {})
    risk = stats.get("risk_share", {})
    top = max(weights, key=weights.get) if weights else None
    return {
        "cash_pct": stats.get("cash_pct", 0),
        "top_ticker": top,
        "top_weight_pct": _pct(weights.get(top, 0)) if top else None,
        "top_risk_pct": _pct(risk.get(top, 0)) if top else None,
        "volatility_pct": _pct(stats.get("volatility_pct", 0)),
        "beta": round(float(stats.get("beta") or 0), 2),
        "over_limit": [t for t, w in weights.items() if w > limit],
        "holdings": len(weights),
    }


def _tightest_cluster(corr: dict, weights: dict, threshold: float = 0.55):
    """The biggest group of holdings that all move together."""
    names = list(corr.keys())
    best = None
    for anchor in names:
        group = [anchor] + [o for o in names
                            if o != anchor and (corr.get(anchor, {}).get(o) or 0) >= threshold]
        if len(group) < 2:
            continue
        pairs = [corr[a][b] for i, a in enumerate(group) for b in group[i + 1:]
                 if corr.get(a, {}).get(b) is not None]
        if not pairs:
            continue
        share = sum(weights.get(g, 0) for g in group)
        score = (len(group), share)
        if best is None or score > best[0]:
            best = (score, group, float(np.mean(pairs)), share)
    if not best:
        return None
    _, group, avg, share = best
    return sorted(group, key=lambda g: -weights.get(g, 0)), avg, share


def _steadiest(weights: dict, risk: dict, exclude: set[str] | None = None):
    """The holding giving the most calm per dollar."""
    exclude = exclude or set()
    candidates = [(t, w, risk.get(t, 0)) for t, w in weights.items()
                  if t not in exclude and w > 2 and risk.get(t, 0) < w - 3]
    if not candidates:
        return None
    return min(candidates, key=lambda c: c[2] / max(c[1], 1e-9))


def _worst_recent(weights: dict, as_of: str):
    """The biggest recent one-day move among held stocks, if there was one."""
    events = event_model.on_day(as_of)
    if events.empty:
        return None
    own = events[events["ticker"].isin(weights.keys())]
    own = own[own["type"].isin(["technical", "news", "earnings"])]
    if own.empty:
        return None
    row = own.loc[own["surprise_z"].abs().idxmax()]
    return row["ticker"], float(row["value"] or 0) * 100 if abs(float(row["value"] or 0)) < 1 else float(row["value"])