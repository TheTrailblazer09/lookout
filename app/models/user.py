"""User records. Password hashing lives in services/auth.py; this module
only reads and writes rows."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.models.base import execute, query, query_one


def _row_to_dict(row) -> dict | None:
    if row is None:
        return None
    return {"id": row[0], "email": row[1], "password_hash": row[2],
            "display_name": row[3], "created_at": row[4]}


def create(email: str, password_hash: str, display_name: str) -> dict:
    user_id = uuid.uuid4().hex[:12]
    execute(
        "INSERT INTO users (id, email, password_hash, display_name, created_at) VALUES (?,?,?,?,?)",
        [user_id, email, password_hash, display_name, datetime.now(timezone.utc)],
    )
    return {"id": user_id, "email": email, "display_name": display_name}


def find_by_email(email: str) -> dict | None:
    return _row_to_dict(query_one(
        "SELECT id, email, password_hash, display_name, created_at FROM users WHERE email = ?",
        [email.strip().lower()],
    ))


def find_by_id(user_id: str) -> dict | None:
    return _row_to_dict(query_one(
        "SELECT id, email, password_hash, display_name, created_at FROM users WHERE id = ?",
        [user_id],
    ))


def email_taken(email: str) -> bool:
    return find_by_email(email) is not None


def count() -> int:
    return int(query("SELECT count(*) AS c FROM users")["c"][0])