"""Alert preferences: step 2 of onboarding, and the settings screen later."""
from flask import Blueprint, jsonify, request

from app.models import preference as preference_model
from app.services import auth as auth_service
from app.utils.errors import ApiError

bp = Blueprint("preferences", __name__)

SENSITIVITY = {"calm", "balanced", "vigilant"}
BOTS = {"technical", "earnings", "news", "macro"}
DIGEST = {"daily", "weekly", "off"}


@bp.get("/preferences")
@auth_service.optional_auth
def get_preferences():
    return jsonify(preference_model.get(auth_service.portfolio_id()))


@bp.put("/preferences")
@auth_service.optional_auth
def put_preferences():
    body = request.get_json(silent=True) or {}

    if "sensitivity" in body and body["sensitivity"] not in SENSITIVITY:
        raise ApiError(f"sensitivity must be one of {sorted(SENSITIVITY)}", 400)
    if "digest" in body and body["digest"] not in DIGEST:
        raise ApiError(f"digest must be one of {sorted(DIGEST)}", 400)
    if "bots" in body:
        bots = body["bots"]
        if not isinstance(bots, list) or not bots:
            raise ApiError("Pick at least one bot to watch with", 400)
        unknown = [b for b in bots if b not in BOTS]
        if unknown:
            raise ApiError(f"unknown bots: {', '.join(unknown)}", 400)
    for key in ("concentration_limit_pct", "sector_limit_pct"):
        if key in body:
            try:
                v = float(body[key])
            except (TypeError, ValueError):
                raise ApiError(f"{key} must be a number", 400)
            if not 1 <= v <= 100:
                raise ApiError(f"{key} must be between 1 and 100", 400)

    saved = preference_model.save(auth_service.portfolio_id(), body)
    return jsonify(saved)