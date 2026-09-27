"""Application factory. Nothing global: create_app() builds an app from a
config, so the CLI, tests and the server all share one wiring path."""
from flask import Flask, jsonify
from flask_cors import CORS

from app.utils.errors import register_error_handlers
from cli import register_commands
from config import get_config


def create_app(env: str | None = None) -> Flask:
    cfg = get_config(env)
    app = Flask(__name__)
    app.config.from_object(cfg)

    CORS(app, resources={r"/*": {"origins": cfg.CORS_ORIGINS}},
         allow_headers=["Content-Type", "Authorization"])

    # No database work at startup. Flask's reloader runs TWO processes, and
    # DuckDB allows a single writer, so opening the file here would make the
    # watcher and the server fight over the lock. The first real query opens
    # it (and creates the schema), which only ever happens in the process
    # actually serving requests.
    register_error_handlers(app)
    _register_blueprints(app)
    register_commands(app)

    @app.get("/health")
    def health():
        return jsonify(ok=True, as_of=cfg.default_as_of())

    return app


def _register_blueprints(app: Flask) -> None:
    from app.controllers import (alerts, auth, insights, llm, overview, plan,
                                 portfolio, preferences, stocks)
    for module in (auth, portfolio, preferences, overview, stocks,
                   insights, alerts, plan, llm):
        app.register_blueprint(module.bp)