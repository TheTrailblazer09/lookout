# """The sensitivity heatmap: what moves my stocks."""
# import numpy as np
# from flask import Blueprint, jsonify, request

# from app.models import fingerprint as fingerprint_model
# from app.models import portfolio as portfolio_model
# from app.services import auth as auth_service
# from config import get_config

# cfg = get_config()
# bp = Blueprint("insights", __name__)


# @bp.get("/sensitivity")
# @auth_service.optional_auth
# def sensitivity():
#     as_of = request.args.get("as_of") or cfg.default_as_of()
#     tickers = [t.strip().upper() for t in request.args.get("tickers", "").split(",") if t.strip()]
#     if not tickers:
#         tickers = portfolio_model.get_holdings(auth_service.portfolio_id())["ticker"].tolist()
#     if not tickers:
#         return jsonify(as_of=as_of, tickers=[], event_types=[], cells=[])

#     df = fingerprint_model.matrix(tickers, as_of)
#     if df.empty:
#         return jsonify(as_of=as_of, tickers=tickers, event_types=[], cells=[],
#                        message="No fingerprint yet. Run `flask build`.")
#     df = df.copy()
#     for col in ("typical_move", "baseline_move", "shrunk_move", "ci_low", "ci_high"):
#         df[col + "_pct"] = (df[col] * 100).round(2)
#     # ratio to baseline: 1.0 means an event day looks like an ordinary day
#     df["vs_baseline"] = (df["shrunk_move"] / df["baseline_move"]).round(2)
#     cells = df.replace({np.nan: None}).to_dict("records")
#     return jsonify(
#         as_of=as_of,
#         tickers=sorted(df["ticker"].unique().tolist()),
#         event_types=sorted(df["event_type"].unique().tolist()),
#         cells=[{k: c[k] for k in ("ticker", "event_type", "n", "shrunk_move_pct",
#                                   "baseline_move_pct", "ci_low_pct", "ci_high_pct",
#                                   "vs_baseline", "share_up", "reliable")} for c in cells],
#     )

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
    """
    Return the sensitivity matrix used by the
    "What Moves My Stocks" page.

    If tickers aren't explicitly supplied,
    use the logged-in user's saved portfolio.
    """

    as_of = (
        request.args.get("as_of")
        or cfg.default_as_of()
    )

    # Optional ability to explicitly request tickers:
    #
    # /sensitivity?tickers=AAPL,NVDA
    #
    # The frontend DOES NOT need to use this because
    # normally we want the current user's portfolio.
    tickers = [
        ticker.strip().upper()
        for ticker
        in request.args.get(
            "tickers",
            ""
        ).split(",")
        if ticker.strip()
    ]

    # No tickers supplied?
    #
    # Read the saved holdings belonging to the
    # authenticated portfolio.
    if not tickers:
        holdings = (
            portfolio_model.get_holdings(
                auth_service.portfolio_id()
            )
        )

        tickers = (
            holdings["ticker"]
            .tolist()
        )

    # User has no holdings.
    if not tickers:
        return jsonify(
            as_of=as_of,
            tickers=[],
            event_types=[],
            cells=[],
        )

    # Fingerprints are stored as snapshots.
    #
    # For example, if the selected date is Sep 26
    # but the most recent built fingerprint is Sep 24,
    # the matrix below will actually use Sep 24.
    #
    # Send that exact snapshot date to React so the
    # evidence panel uses the same historical cutoff.
    snapshot_as_of = (
        fingerprint_model.latest_as_of(
            as_of
        )
    )

    # Fetch all stock × event cells for
    # the current portfolio.
    df = fingerprint_model.matrix(
        tickers,
        as_of,
    )

    if df.empty:
        return jsonify(
            as_of=as_of,
            fingerprint_as_of=snapshot_as_of,
            tickers=tickers,
            event_types=[],
            cells=[],
            message=(
                "No fingerprint yet. "
                "Run `flask build`."
            ),
        )

    df = df.copy()

    # Backend stores returns as decimal values.
    #
    # Example:
    #     0.034 -> 3.4%
    #
    # Convert them for direct frontend display.
    for col in (
        "typical_move",
        "baseline_move",
        "shrunk_move",
        "ci_low",
        "ci_high",
    ):
        df[col + "_pct"] = (
            df[col] * 100
        ).round(2)

    # Ratio relative to normal stock movement.
    #
    # 1.0 means event movement is roughly the
    # same as an ordinary comparable period.
    #
    # 2.0 means approximately twice its normal move.
    df["vs_baseline"] = (
        df["shrunk_move"]
        / df["baseline_move"]
    ).round(2)

    # NaN isn't valid JSON.
    cells = (
        df.replace(
            {np.nan: None}
        )
        .to_dict("records")
    )

    return jsonify(
        as_of=as_of,

        # Actual snapshot used by fingerprint.matrix().
        fingerprint_as_of=snapshot_as_of,

        # IMPORTANT:
        #
        # Return the full saved portfolio rather than:
        #
        # sorted(df["ticker"].unique())
        #
        # because a holding with insufficient historical
        # evidence should still appear in the UI with "—"
        # cells rather than disappearing.
        tickers=tickers,

        event_types=sorted(
            df["event_type"]
            .unique()
            .tolist()
        ),

        cells=[
            {
                key: cell[key]
                for key in (
                    "ticker",
                    "event_type",
                    "n",
                    "shrunk_move_pct",
                    "baseline_move_pct",
                    "ci_low_pct",
                    "ci_high_pct",
                    "vs_baseline",
                    "share_up",
                    "reliable",
                )
            }
            for cell in cells
        ],
    )