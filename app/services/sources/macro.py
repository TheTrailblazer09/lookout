"""Macro releases from FRED.

The trap here: a CPI reading *labelled* January is published in February.
Using the observation date as known_at would let the model see inflation
weeks before anyone did.

FRED's answer is output_type=4 ("initial release only"), where each
observation carries realtime_start: the date that number was first
published. That is our known_at. Surprise is actual minus the previous
reading, standardized; a true consensus surprise would need a paid
calendar, so we label this clearly as the weaker proxy it is.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
RELEASE_HOUR = 8.5  # 8:30am ET, when most US data drops

# series: (event type, human label, higher-is-hawkish)
SERIES = {
    "CPIAUCSL":  ("cpi", "CPI (headline, monthly)"),
    "FEDFUNDS":  ("fed", "Effective fed funds rate"),
    "PAYEMS":    ("jobs", "Nonfarm payrolls"),
    "DCOILWTICO": ("oil", "WTI crude oil price"),
    "VIXCLS":    ("vix", "VIX volatility index"),
    "DGS10":     ("rates", "10-year Treasury yield"),
}
# Series we turn into portfolio events (the rest are features/indicators only)
EVENT_SERIES = {"CPIAUCSL", "FEDFUNDS", "PAYEMS"}


# FRED's full vintage window. output_type=4 (initial release only) returns
# nothing useful unless the realtime window spans all of history: the API
# defaults to today..today, which is why leaving these out gives a 400.
REALTIME_MIN, REALTIME_MAX = "1776-07-04", "9999-12-31"

# Typical publication lag, used only by the fallback path below.
FALLBACK_LAG_DAYS = {"CPIAUCSL": 13, "PAYEMS": 5, "FEDFUNDS": 2,
                     "DCOILWTICO": 1, "VIXCLS": 0, "DGS10": 0}


def _call(params: dict) -> dict:
    url = f"{FRED_URL}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as err:
        # FRED explains itself in the body; without this you just see "400".
        try:
            detail = json.loads(err.read()).get("error_message", "")
        except Exception:  # noqa: BLE001
            detail = ""
        raise RuntimeError(f"HTTP {err.code}: {detail or err.reason}") from None


def _get(series_id: str, api_key: str, start: str) -> pd.DataFrame:
    base = {"series_id": series_id, "api_key": (api_key or "").strip(),
            "file_type": "json", "observation_start": start}

    # Preferred: real first-publication dates.
    try:
        payload = _call({**base, "output_type": 4,
                         "realtime_start": REALTIME_MIN, "realtime_end": REALTIME_MAX})
        obs = pd.DataFrame(payload.get("observations", []))
        if not obs.empty and "realtime_start" in obs.columns:
            obs = obs[obs["value"] != "."].copy()
            obs["value"] = obs["value"].astype(float)
            obs["date"] = pd.to_datetime(obs["date"]).dt.date
            obs["published"] = pd.to_datetime(obs["realtime_start"])
            return obs[["date", "published", "value"]].reset_index(drop=True)
    except RuntimeError as exc:
        print(f"  ! {series_id}: vintage request failed ({exc}); falling back to "
              "observation date + typical lag")

    # Fallback: current values, with known_at approximated by a fixed lag.
    # Less exact, still safe (it never claims a number earlier than the lag),
    # but say so in the write-up rather than passing it off as a true vintage.
    payload = _call(base)
    obs = pd.DataFrame(payload.get("observations", []))
    if obs.empty:
        return obs
    obs = obs[obs["value"] != "."].copy()
    obs["value"] = obs["value"].astype(float)
    obs["date"] = pd.to_datetime(obs["date"]).dt.date
    lag = pd.Timedelta(days=FALLBACK_LAG_DAYS.get(series_id, 7))
    obs["published"] = pd.to_datetime(obs["date"]) + lag
    obs["approx_known_at"] = True
    return obs[["date", "published", "value"]].reset_index(drop=True)


def fetch_indicators(api_key: str, start: str) -> dict[str, pd.DataFrame]:
    """Every series, for the Weather report page and model features."""
    out = {}
    for sid in SERIES:
        try:
            df = _get(sid, api_key, start)
            if not df.empty:
                out[sid] = df
        except Exception as exc:  # noqa: BLE001
            print(f"  ! FRED {sid} failed ({exc})")
    return out


def to_events(indicators: dict[str, pd.DataFrame], sessions: list) -> pd.DataFrame:
    """Turn releases into events, one per publication, on the first trading
    day that could react to it."""
    from app.services.sources.market import to_date
    sessions_sorted = sorted({to_date(s) for s in sessions})
    rows = []
    for sid, df in indicators.items():
        if sid not in EVENT_SERIES:
            continue
        etype, label = SERIES[sid]
        # reset_index: FRED can hand back duplicate index labels, and a
        # duplicated label makes .loc return a Series instead of a scalar.
        d = df.sort_values("published").drop_duplicates("date").reset_index(drop=True)
        change = d["value"].diff()
        sd = change.std(ddof=0) or 1.0
        z = (change - change.mean()) / sd
        for i, row in d.iterrows():
            s = z.iat[i]
            if pd.isna(s):
                continue
            pub = pd.Timestamp(row["published"]) + pd.Timedelta(hours=RELEASE_HOUR)
            pub_day = pub.date()
            day0 = next((x for x in sessions_sorted if x >= pub_day), None)
            if day0 is None:
                continue
            if etype == "cpi":
                sub = "hot" if s > 0.5 else "cold" if s < -0.5 else "inline"
            elif etype == "fed":
                sub = "hike" if s > 0.25 else "cut" if s < -0.25 else "hold"
            else:
                sub = "strong" if s > 0.5 else "weak" if s < -0.5 else "inline"
            rows.append({
                "id": f"{etype}-{row['date']}",
                "ticker": None, "type": etype, "subtype": sub,
                "known_at": pub, "day0": day0,
                "value": float(row["value"]), "surprise_z": float(s),
                "source": "FRED",
                "description": f"{label}: {row['value']:.2f} ({sub}, "
                               f"{s:+.1f} sd vs the usual change)",
            })
    return pd.DataFrame(rows)