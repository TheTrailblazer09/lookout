"""One error shape for the whole API, so the frontend can rely on it:

    {"error": {"message": "...", "status": 401}}
"""
from __future__ import annotations

import traceback

from flask import jsonify
from werkzeug.exceptions import HTTPException


class ApiError(Exception):
    """Raise anywhere in services or controllers; the handler turns it into
    a clean JSON response."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def _api_error(err: ApiError):
        return jsonify(error={"message": err.message, "status": err.status}), err.status

    @app.errorhandler(HTTPException)
    def _http_error(err: HTTPException):
        return jsonify(error={"message": err.description, "status": err.code}), err.code

    @app.errorhandler(Exception)
    def _unhandled(err: Exception):
        app.logger.error("unhandled: %s\n%s", err, traceback.format_exc())
        msg = str(err) if app.config.get("DEBUG") else "Something went wrong"
        return jsonify(error={"message": msg, "status": 500}), 500