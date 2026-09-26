"""Application factory. Nothing global: create_app() builds an app from a
config, so the CLI, tests and the server all share one wiring path."""
from flask import Flask, jsonify
from flask_cors import CORS

from app.models.base import init_db
from app.utils.errors import register_error_handlers
from cli import register_commands
from config import get_config


def create_app(env: str | None = None) -> Flask:
    cfg = get_config(env)
    app = Flask(__name__)
    app.config.from_object(cfg)

    CORS(app, resources={r"/*": {"origins": cfg.CORS_ORIGINS}},
         allow_headers=["Content-Type", "Authorization"])

    init_db()
    register_error_handlers(app)
    _register_blueprints(app)
    register_commands(app)

    @app.get("/health")
    def health():
        return jsonify(ok=True, as_of=cfg.default_as_of())

    return app


def _register_blueprints(app: Flask) -> None:
    from app.controllers import auth, insights, overview, portfolio, stocks
    for module in (auth, portfolio, overview, stocks, insights):
        app.register_blueprint(module.bp)
    # Registered as each is written:
    # from app.controllers import alerts