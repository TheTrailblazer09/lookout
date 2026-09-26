"""Technical bot: notices when a stock's own price action is unusual.

The trap this bot has to avoid: judging today's crash with a yardstick that
today's crash already widened. If you measure a move against volatility
computed through today, a huge day inflates the denominator and the move
looks ordinary. Every threshold here uses volatility estimated through
YESTERDAY (an exponentially weighted estimate, shifted one day), so a big
move is scored against what "normal" looked like before it happened.

It emits four kinds of flag, each only when it clears a bar that an
ordinary week would not:
  move      - a daily move far outside this stock's own normal range
  volume    - trading volume far above its own recent typical level
  momentum  - RSI at an extreme (oversold or overbought)
  trend     - price crossing its 50-day average, which changes the story
              a chart tells even when no single day was dramatic
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.models import event as event_model
from app.models import price as price_model
from config import get_config

cfg = get_config()
SOURCE = "technical-bot"

MOVE_Z = 2.5        # how many "normal days" a move must be worth
VOLUME_Z = 2.5
RSI_LOW, RSI_HIGH = 30, 70


def _rsi(r: pd.Series, window: int = 14) -> pd.Series:
    up = r.clip(lower=0).ewm(alpha=1 / window, adjust=False).mean()
    down = (-r.clip(upper=0)).ewm(alpha=1 / window, adjust=False).mean()
    return 100 - 100 / (1 + up / down.replace(0, np.nan))


def detect(as_of: str, tickers: list[str] | None = None,
           lookback_days: int = 30) -> pd.DataFrame:
    """Scan the last `lookback_days` sessions and return technical events.

    Only days on or before as_of are read, so this is safe to run inside a
    replay.
    """
    tickers = tickers or price_model.known_tickers()
    tickers = [t for t in tickers if t != cfg.MARKET_TICKER]
    if not tickers:
        return pd.DataFrame()

    wide = price_model.wide(tickers, as_of)
    vol_df = price_model.history(tickers, as_of)
    if wide.empty:
        return pd.DataFrame()

    rets = np.log(wide / wide.shift(1))
    volumes = vol_df.pivot(index="date", columns="ticker", values="volume") \
        if not vol_df.empty else pd.DataFrame()
    recent = wide.index[-lookback_days:]
    rows: list[dict] = []

    for t in tickers:
        if t not in rets.columns:
            continue
        r = rets[t]
        # yesterday's yardstick: shift(1) is the whole point
        sd = r.ewm(alpha=0.06).std().shift(1)
        rsi = _rsi(r)
        ma50 = wide[t].rolling(50, min_periods=30).mean()
        above = wide[t] > ma50

        logvol = np.log(volumes[t].replace(0, np.nan)) if t in volumes.columns else None
        vol_z = ((logvol - logvol.rolling(60).mean()) / logvol.rolling(60).std()).shift(0) \
            if logvol is not None else None

        for day in recent:
            if day not in r.index or pd.isna(r[day]) or pd.isna(sd.get(day)) or sd[day] == 0:
                continue
            z = float(r[day] / sd[day])
            when = pd.Timestamp(day) + pd.Timedelta(hours=16)  # known at the close

            if abs(z) >= MOVE_Z:
                pct = float(np.expm1(r[day])) * 100
                rows.append(_event(t, "technical", "drop" if z < 0 else "jump", when, day, z,
                                   f"{t} moved {pct:+.1f}% in one day, about "
                                   f"{abs(z):.1f}x its normal daily swing"))

            if vol_z is not None and day in vol_z.index and not pd.isna(vol_z[day]) \
                    and vol_z[day] >= VOLUME_Z:
                rows.append(_event(t, "technical", "volume", when, day, float(vol_z[day]),
                                   f"{t} traded {vol_z[day]:.1f} standard deviations "
                                   "above its usual volume"))

            if day in rsi.index and not pd.isna(rsi[day]):
                val = float(rsi[day])
                if val <= RSI_LOW:
                    rows.append(_event(t, "technical", "oversold", when, day,
                                       (val - 50) / 20,
                                       f"{t} RSI at {val:.0f}: sold hard and fast"))
                elif val >= RSI_HIGH:
                    rows.append(_event(t, "technical", "overbought", when, day,
                                       (val - 50) / 20,
                                       f"{t} RSI at {val:.0f}: bought hard and fast"))

            prev = above.shift(1)
            if day in above.index and day in prev.index \
                    and not pd.isna(above[day]) and not pd.isna(prev[day]) \
                    and bool(above[day]) != bool(prev[day]):
                direction = "above" if above[day] else "below"
                rows.append(_event(t, "technical", f"cross_{direction}", when, day,
                                   1.0 if above[day] else -1.0,
                                   f"{t} closed {direction} its 50-day average "
                                   "for the first time in a while"))

    return pd.DataFrame(rows)


def _event(ticker, etype, subtype, known_at, day0, z, description) -> dict:
    return {
        "id": f"tech-{ticker}-{day0}-{subtype}",
        "ticker": ticker, "type": etype, "subtype": subtype,
        "known_at": known_at, "day0": day0,
        "value": float(z), "surprise_z": float(z),
        "source": SOURCE, "description": description,
    }


def run(as_of: str, tickers: list[str] | None = None, lookback_days: int = 30) -> int:
    df = detect(as_of, tickers, lookback_days)
    return event_model.upsert(df) if not df.empty else 0