"""Overview: the home screen numbers."""
from flask import Blueprint, jsonify, request

from app.services import auth as auth_service
from app.services import portfolio_math
from config import get_config

cfg = get_config()
bp = Blueprint("overview", __name__)


@bp.get("/overview")
@auth_service.optional_auth
def overview():
    as_of = request.args.get("as_of") or cfg.default_as_of()
    stats = portfolio_math.analyze(auth_service.portfolio_id(), as_of)
    if stats.get("empty"):
        return jsonify(as_of=as_of, empty=True,
                       message="No holdings yet. Save a portfolio first.")

    r2 = lambda x: None if x is None else round(float(x), 2)
    return jsonify(
        as_of=as_of,
        sea_state=stats["sea_state"],
        value=r2(stats["value"]),
        day_change_pct=r2(stats["day_change_pct"]),
        day_move_in_sds=r2(stats["day_move_in_sds"]),
        return_pct=r2(stats["return_pct"]),
        market_return_pct=r2(stats["market_return_pct"]),
        volatility_pct=r2(stats["volatility_pct"]),
        market_volatility_pct=r2(stats["market_volatility_pct"]),
        beta=r2(stats["beta"]),
        max_drawdown_pct=r2(stats["max_drawdown_pct"]),
        weights={k: r2(v) for k, v in stats["weights"].items()},
        risk_share={k: r2(v) for k, v in stats["risk_share"].items()},
        correlation=stats["correlation"],
        series=stats["series"],
        pins=stats["pins"],
    )