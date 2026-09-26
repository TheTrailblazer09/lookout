"""Auth endpoints. Thin: parse the body, call the service, return JSON."""
from flask import Blueprint, g, jsonify, request

from app.services import auth as auth_service

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.post("/register")
def register():
    body = request.get_json(silent=True) or {}
    result = auth_service.register(
        email=body.get("email", ""),
        password=body.get("password", ""),
        display_name=body.get("display_name", ""),
    )
    return jsonify(result), 201


@bp.post("/login")
def login():
    body = request.get_json(silent=True) or {}
    return jsonify(auth_service.login(body.get("email", ""), body.get("password", "")))


@bp.get("/me")
@auth_service.require_auth
def me():
    return jsonify(user=g.user)


@bp.post("/logout")
def logout():
    # Tokens are stateless: the client drops it. Here so the frontend has
    # a symmetric endpoint to call.
    return jsonify(ok=True)