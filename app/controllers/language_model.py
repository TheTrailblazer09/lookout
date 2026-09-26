"""Local-model setup, driven from the UI instead of a terminal."""
from flask import Blueprint, jsonify, request

from app.services import llm_setup

bp = Blueprint("llm", __name__, url_prefix="/llm")


@bp.get("/status")
def status():
    """Poll this while a download runs."""
    return jsonify(llm_setup.status())


@bp.post("/start")
def start():
    """Start the Ollama server if it is installed but not running."""
    return jsonify(llm_setup.start_server())


@bp.post("/pull")
def pull():
    """Begin downloading a model; returns immediately."""
    model = (request.get_json(silent=True) or {}).get("model")
    return jsonify(llm_setup.pull(model))


@bp.post("/ensure")
def ensure():
    """Start the server and download the model as needed, in one call."""
    model = (request.get_json(silent=True) or {}).get("model")
    return jsonify(llm_setup.ensure(model))