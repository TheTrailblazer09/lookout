"""Weather report: macro exposure, what's coming, and the indicators."""
from flask import Blueprint, jsonify, request

from app.models import summary as summary_model
from app.services import auth as auth_service
from app.services import llm_setup, narrator, weather as weather_service
from config import get_config

cfg = get_config()
bp = Blueprint("weather", __name__)


@bp.get("/weather")
@auth_service.optional_auth
def weather():
    as_of = request.args.get("as_of") or cfg.default_as_of()
    portfolio_id = auth_service.portfolio_id()
    data = weather_service.build(portfolio_id, as_of)
    if data.get("empty"):
        return jsonify(as_of=as_of, empty=True)

    st = llm_setup.status()
    # cached only: writing happens on its own endpoint so the page is instant
    data["forecast"] = summary_model.get(f"{portfolio_id}:weather", as_of)
    data["narrator"] = {"ready": st["ready"], "model": st["model"], "message": st["message"]}
    return jsonify(data)


@bp.post("/weather/forecast")
@auth_service.optional_auth
def forecast():
    as_of = request.args.get("as_of") or cfg.default_as_of()
    portfolio_id = auth_service.portfolio_id()
    key = f"{portfolio_id}:weather"

    cached = summary_model.get(key, as_of)
    if cached:
        return jsonify(forecast=cached, cached=True)

    data = weather_service.build(portfolio_id, as_of)
    if data.get("empty"):
        return jsonify(forecast=None, cached=False)

    text, how = narrator.write(data["facts"], prompt="weather_forecast",
                               keys=("headline", "forecast"))
    if not text:
        return jsonify(forecast=None, cached=False, why=how)
    return jsonify(forecast=summary_model.save(key, as_of, {**text, "written_by": how}),
                   cached=False)