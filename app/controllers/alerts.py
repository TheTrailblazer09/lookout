"""Alert endpoints."""
from flask import Blueprint, jsonify, request

from app.models import alert as alert_model
from app.models import evidence as evidence_model
from app.models import portfolio as portfolio_model
from app.services import auth as auth_service
from app.models import fingerprint as fingerprint_model
from app.services import event_study
from app.services import llm_setup
from app.services import severity as severity_service
from app.services.bots import technical as technical_bot
from app.utils.errors import ApiError
from config import get_config

cfg = get_config()
bp = Blueprint("alerts", __name__, url_prefix="/alerts")


def _ensure(as_of: str, portfolio_id: str, refresh: bool = False) -> None:
    """Build this day's alerts if nobody has yet.

    Alerts are normally precomputed by `flask alerts`, which is what keeps
    the demo instant. But the time machine can land on any date, and an
    empty screen there looks like the product is broken rather than like a
    day nobody prepared. So on a miss we run the bots for the held tickers
    and generate once; the rows are stored, so the same date is instant
    afterwards.
    """
    # Generated alerts are cached, which is what keeps replay instant. Two
    # things still force a rebuild: an explicit ?refresh=1, and the local
    # model having come online since these were written. Without the second
    # check, starting Ollama appears to do nothing, because every alert on
    # screen was stored back when nothing could write them.
    existing = alert_model.for_day(as_of, portfolio_id)
    if existing and not refresh:
        model_ready = llm_setup.status()["ready"]
        stale = any(not alert_model.written_by_model(a) for a in existing)
        if not (model_ready and stale):
            return
    holdings = portfolio_model.get_holdings(portfolio_id)["ticker"].tolist()
    if not holdings:
        return

    # a short lookback: we only need events dated on or near this day
    technical_bot.run(as_of, tickers=holdings, lookback_days=5)

    # The fingerprint is a dated snapshot. `flask build` writes one for the
    # day it runs, so replaying an earlier date finds nothing at or before
    # it and every alert says "no comparable past events". Build the missing
    # snapshot here, from evidence whose outcome window had already closed
    # by that date, so replayed history stays honest.
    if fingerprint_model.latest_as_of(as_of) is None:
        event_study.build_fingerprint(as_of)

    severity_service.build(as_of, portfolio_id, use_llm=True)


@bp.get("")
@auth_service.optional_auth
def list_alerts():
    as_of = request.args.get("as_of") or cfg.default_as_of()
    portfolio_id = auth_service.portfolio_id()
    refresh = request.args.get("refresh") == "1"
    if refresh:
        # a forced rebuild should also refresh the day's fingerprint
        fingerprint_model.replace_for(as_of, __import__("pandas").DataFrame())
    if request.args.get("generate", "1") != "0":
        _ensure(as_of, portfolio_id, refresh=refresh)
    rows = alert_model.for_day(as_of, portfolio_id,
                               request.args.get("category"))
    status = llm_setup.status()
    # what the person's votes have taught us, so the UI can show it rather
    # than quietly reordering things behind their back
    tuning = [
        {"category": cat, "weight": round(w, 2),
         "direction": "more" if w > 1 else "fewer"}
        for cat, w in sorted(alert_model.category_weights(portfolio_id).items())
        if abs(w - 1) > 0.05
    ]
    return jsonify(as_of=as_of, count=len(rows), tuning=tuning,
                   # so the UI can explain a missing write-up instead of
                   # silently showing nothing
                   narrator={"ready": status["ready"], "model": status["model"],
                             "message": status["message"]},
                   alerts=[{
        "id": r["id"], "ticker": r["ticker"], "severity": r["severity"],
        "category": r["category"], "grounded": r["grounded"],
        "title": (r["text"] or {}).get("title") or r["facts"].get("headline"),
        "why": (r["text"] or {}).get("why"),
        "day_move_pct": r["facts"].get("day_move_pct"),
        "weight_pct": r["facts"].get("weight_pct"),
    } for r in rows])


@bp.get("/<alert_id>")
def alert_detail(alert_id):
    row = alert_model.by_id(alert_id)
    if not row:
        raise ApiError("No such alert", 404)
    ids = row["analog_event_ids"]
    analogs = []
    if ids:
        ev = evidence_model.usable(row["as_of"], row["ticker"])
        hit = ev[ev["event_id"].isin(ids)]
        analogs = [{
            "date": str(a.day0), "description": a.description,
            "moved_pct": round(float(a.abnormal_ret) * 100, 1),
            "how_unusual": round(float(a.move_z), 2),
        } for a in hit.itertuples()]
    return jsonify(id=row["id"], as_of=row["as_of"], ticker=row["ticker"],
                   severity=row["severity"], category=row["category"],
                   grounded=row["grounded"], text=row["text"], facts=row["facts"],
                   past_events=analogs)


@bp.post("/<alert_id>/feedback")
def feedback(alert_id):
    body = request.get_json(silent=True) or {}
    vote = str(body.get("vote", "")).lower()
    if vote not in {"useful", "less"}:
        raise ApiError('vote must be "useful" or "less"', 400)
    if not alert_model.by_id(alert_id):
        raise ApiError("No such alert", 404)
    alert_model.save_feedback(alert_id, vote)
    return jsonify(ok=True)