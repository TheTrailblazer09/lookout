"""Overview: the home screen numbers."""
from flask import Blueprint, jsonify, request

from app.models import summary as summary_model
from app.services import auth as auth_service
from app.services import llm_setup
from app.services import narrator
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

    # Only ever a cached read here. Generating one means loading a model
    # into memory, which can take half a minute on the first call, and the
    # whole page would sit on "Reading your portfolio…" waiting for it.
    read = summary_model.get(auth_service.portfolio_id(), as_of)
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
        read=read,
        narrator=_narrator_status(),
    )


def _narrator_status() -> dict:
    st = llm_setup.status()
    return {"ready": st["ready"], "model": st["model"], "message": st["message"]}


@bp.post("/overview/read")
@auth_service.optional_auth
def generate_read():
    """Write today's paragraph. Called separately by the UI so the page can
    render instantly and fill this in when it arrives."""
    as_of = request.args.get("as_of") or cfg.default_as_of()
    portfolio_id = auth_service.portfolio_id()
    cached = summary_model.get(portfolio_id, as_of)
    if cached:
        return jsonify(read=cached, cached=True)

    stats = portfolio_math.analyze(portfolio_id, as_of)
    if stats.get("empty"):
        return jsonify(read=None, cached=False)
    return jsonify(read=_daily_read(portfolio_id, as_of, stats), cached=False)


def _daily_read(portfolio_id: str, as_of: str, stats: dict) -> dict | None:
    """Qwen's paragraph for this day, written once and cached.

    The model only ever sees figures our own maths produced, and its output
    is checked the same way alert text is. If it is not running we return
    nothing and the screen says so, rather than showing something that
    looks written but is not.
    """
    cached = summary_model.get(portfolio_id, as_of)
    if cached:
        return cached

    weights = stats.get("weights") or {}
    risk = stats.get("risk_share") or {}
    biggest = max(weights, key=weights.get) if weights else None
    gap = max(((t, risk.get(t, 0) - w) for t, w in weights.items()),
              key=lambda x: x[1], default=(None, 0))

    facts = {
        "day_move_pct": round(stats["day_change_pct"], 2),
        "sea_state": stats["sea_state"],
        "value": int(stats["value"]),
        "return_pct": round(stats["return_pct"], 1),
        "market_return_pct": round(stats["market_return_pct"], 1),
        "volatility_pct": round(stats["volatility_pct"], 1),
        "holdings": len(weights),
    }
    if biggest:
        facts["biggest_holding"] = {"ticker": biggest, "weight_pct": round(weights[biggest], 1)}
    if gap[0] and gap[1] > 3:
        facts["concentration_note"] = {
            "ticker": gap[0],
            "weight_pct": round(weights[gap[0]], 1),
            "risk_share_pct": round(risk[gap[0]], 1),
        }

    text, how = narrator.portfolio_read(facts)
    if not text:
        return None
    payload = {**text, "written_by": how}
    return summary_model.save(portfolio_id, as_of, payload)