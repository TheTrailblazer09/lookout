"""Alert endpoints."""
from flask import Blueprint, jsonify, request

from app.models import alert as alert_model
from app.models import evidence as evidence_model
from app.services import auth as auth_service
from app.utils.errors import ApiError
from config import get_config

cfg = get_config()
bp = Blueprint("alerts", __name__, url_prefix="/alerts")


@bp.get("")
@auth_service.optional_auth
def list_alerts():
    as_of = request.args.get("as_of") or cfg.default_as_of()
    rows = alert_model.for_day(as_of, auth_service.portfolio_id(),
                               request.args.get("category"))
    return jsonify(as_of=as_of, count=len(rows), alerts=[{
        "id": r["id"], "ticker": r["ticker"], "severity": r["severity"],
        "category": r["category"], "grounded": r["grounded"],
        "title": r["text"].get("title"), "why": r["text"].get("why"),
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