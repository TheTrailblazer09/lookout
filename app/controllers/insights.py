"""The sensitivity heatmap: what moves my stocks."""
import numpy as np
from flask import Blueprint, jsonify, request

from app.models import fingerprint as fingerprint_model
from app.models import portfolio as portfolio_model
from app.services import auth as auth_service
from config import get_config

cfg = get_config()
bp = Blueprint("insights", __name__)


@bp.get("/sensitivity")
@auth_service.optional_auth
def sensitivity():
    as_of = request.args.get("as_of") or cfg.default_as_of()
    tickers = [t.strip().upper() for t in request.args.get("tickers", "").split(",") if t.strip()]
    if not tickers:
        tickers = portfolio_model.get_holdings(auth_service.portfolio_id())["ticker"].tolist()
    if not tickers:
        return jsonify(as_of=as_of, tickers=[], event_types=[], cells=[])

    df = fingerprint_model.matrix(tickers, as_of)
    if df.empty:
        return jsonify(as_of=as_of, tickers=tickers, event_types=[], cells=[],
                       message="No fingerprint yet. Run `flask build`.")
    df = df.copy()
    for col in ("typical_move", "baseline_move", "shrunk_move", "ci_low", "ci_high"):
        df[col + "_pct"] = (df[col] * 100).round(2)
    # ratio to baseline: 1.0 means an event day looks like an ordinary day
    df["vs_baseline"] = (df["shrunk_move"] / df["baseline_move"]).round(2)
    cells = df.replace({np.nan: None}).to_dict("records")
    return jsonify(
        as_of=as_of,
        tickers=sorted(df["ticker"].unique().tolist()),
        event_types=sorted(df["event_type"].unique().tolist()),
        cells=[{k: c[k] for k in ("ticker", "event_type", "n", "shrunk_move_pct",
                                  "baseline_move_pct", "ci_low_pct", "ci_high_pct",
                                  "vs_baseline", "share_up", "reliable")} for c in cells],
    )