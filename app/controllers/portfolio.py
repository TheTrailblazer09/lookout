"""Portfolio endpoints: ticker search, read and replace holdings.

Signed-out callers read and write the shared demo portfolio, which is how
judges click around without registering; signed-in callers get their own.
"""
from flask import Blueprint, g, jsonify, request

from app.models import portfolio as portfolio_model
from app.models import price as price_model
from app.services import auth as auth_service
from app.utils.errors import ApiError
from config import get_config

cfg = get_config()
bp = Blueprint("portfolio", __name__)


@bp.get("/tickers/search")
def search():
    term = request.args.get("q", "")
    if not term:
        return jsonify(results=[])
    return jsonify(results=price_model.search(term, limit=int(request.args.get("limit", 8))))


@bp.get("/portfolio")
@auth_service.optional_auth
def get_portfolio():
    as_of = request.args.get("as_of") or cfg.default_as_of()
    pid = auth_service.portfolio_id()
    df = portfolio_model.valued(pid, as_of)
    if df.empty:
        return jsonify(portfolio_id=pid, as_of=as_of, total_value=0, holdings=[])
    holdings = [{
        "ticker": r.ticker,
        "shares": round(float(r.shares), 4),
        "price": round(float(r.close), 2),
        "value": round(float(r.value), 2),
        "weight_pct": round(float(r.weight) * 100, 1),
        "day_change_pct": round(float(r.day_return) * 100, 2),
    } for r in df.itertuples()]
    return jsonify(portfolio_id=pid, as_of=as_of,
                   total_value=round(float(df["value"].sum()), 2), holdings=holdings)


@bp.put("/portfolio")
@auth_service.optional_auth
def put_portfolio():
    body = request.get_json(silent=True) or {}
    holdings = body.get("holdings")
    if not isinstance(holdings, list) or not holdings:
        raise ApiError("Send holdings: [{ticker, shares}, ...]", 400)

    known = set(price_model.known_tickers())
    cleaned = []
    for h in holdings:
        ticker = str(h.get("ticker", "")).upper().strip()
        if ticker not in known:
            raise ApiError(f"No price history for {ticker or '(blank)'}", 400)
        try:
            shares = float(h.get("shares", 0))
        except (TypeError, ValueError):
            raise ApiError(f"shares for {ticker} must be a number", 400)
        if shares <= 0:
            raise ApiError(f"shares for {ticker} must be greater than zero", 400)
        cleaned.append({"ticker": ticker, "shares": shares})

    pid = auth_service.portfolio_id()
    n = portfolio_model.replace_holdings(pid, cleaned)
    return jsonify(portfolio_id=pid, saved=n)