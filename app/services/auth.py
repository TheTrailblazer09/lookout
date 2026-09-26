"""Authentication: password hashing, JWT issue/verify, and the decorator
controllers use to require a logged-in user.

Tokens are stateless: there is no server-side session table, so "log out"
is the client dropping the token. Fine for this product; if you later need
forced revocation, add a token_version column on users and put it in the
payload.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import g, request
from werkzeug.security import check_password_hash, generate_password_hash

from app.models import user as user_model
from app.utils.errors import ApiError
from config import get_config

cfg = get_config()
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# --- passwords -----------------------------------------------------------

def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return check_password_hash(password_hash, password)


# --- tokens --------------------------------------------------------------

def issue_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "iat": now,
               "exp": now + timedelta(hours=cfg.JWT_TTL_HOURS)}
    return jwt.encode(payload, cfg.SECRET_KEY, algorithm=cfg.JWT_ALGORITHM)


def decode_token(token: str) -> str:
    """Returns the user id, or raises ApiError(401)."""
    try:
        payload = jwt.decode(token, cfg.SECRET_KEY, algorithms=[cfg.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise ApiError("Session expired, please sign in again", 401)
    except jwt.InvalidTokenError:
        raise ApiError("Invalid token", 401)
    return payload["sub"]


def _bearer_token() -> str | None:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:].strip()
    return None


# --- use cases -----------------------------------------------------------

def register(email: str, password: str, display_name: str = "") -> dict:
    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email):
        raise ApiError("That doesn't look like an email address", 400)
    if len(password or "") < cfg.PASSWORD_MIN_LENGTH:
        raise ApiError(f"Password must be at least {cfg.PASSWORD_MIN_LENGTH} characters", 400)
    if user_model.email_taken(email):
        raise ApiError("An account with that email already exists", 409)
    user = user_model.create(email, hash_password(password), display_name or email.split("@")[0])
    return {"user": user, "token": issue_token(user["id"])}


def login(email: str, password: str) -> dict:
    user = user_model.find_by_email((email or "").strip().lower())
    # Same message either way: don't reveal which emails have accounts.
    if not user or not verify_password(password or "", user["password_hash"]):
        raise ApiError("Email or password is incorrect", 401)
    public = {"id": user["id"], "email": user["email"], "display_name": user["display_name"]}
    return {"user": public, "token": issue_token(user["id"])}


def current_user() -> dict | None:
    """Resolves the caller from the Authorization header, or None."""
    if "current_user" in g:
        return g.current_user
    token = _bearer_token()
    if not token:
        g.current_user = None
        return None
    user = user_model.find_by_id(decode_token(token))
    g.current_user = None if not user else {
        "id": user["id"], "email": user["email"], "display_name": user["display_name"]}
    return g.current_user


def require_auth(fn):
    """Route decorator. Rejects anonymous callers; sets g.user."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            raise ApiError("Sign in to continue", 401)
        g.user = user
        return fn(*args, **kwargs)
    return wrapper


def optional_auth(fn):
    """Route decorator for endpoints that work signed out, falling back to
    the demo portfolio. Sets g.user to the user or None."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        g.user = current_user()
        return fn(*args, **kwargs)
    return wrapper


def portfolio_id() -> str:
    """Which portfolio the current request reads and writes. Anonymous
    callers get the shared demo portfolio, which is what lets judges click
    around without signing up."""
    user = g.get("user") or current_user()
    return user["id"] if user else cfg.DEMO_PORTFOLIO_ID