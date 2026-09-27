"""Chart a course: ideas, and what they would change."""
from flask import Blueprint, jsonify, request

from app.services import auth as auth_service
from app.services import plan as plan_service
from config import get_config

cfg = get_config()
bp = Blueprint("plan", __name__, url_prefix="/plan")


@bp.get("/ideas")
@auth_service.optional_auth
def ideas():
    as_of = request.args.get("as_of") or cfg.default_as_of()
    return jsonify(plan_service.build(auth_service.portfolio_id(), as_of))


@bp.post("/simulate")
@auth_service.optional_auth
def simulate():
    as_of = request.args.get("as_of") or cfg.default_as_of()
    body = request.get_json(silent=True) or {}
    ids = body.get("ideas") or []
    return jsonify(plan_service.simulate(auth_service.portfolio_id(), as_of, ids))