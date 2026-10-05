#!/usr/bin/env python3
"""
intraday_features.py - the declared intraday descriptors of one stock-day.

Inputs: that day's 3-minute bars (125, 09:15-15:27), the previous close, the previous
20 sessions' total volumes, optionally NIFTY 50's bars for the same day. Nothing from
later days is used. Groups (INTRADAY_DECLARATION.json "descriptors"):

  opening   gap, ret_15, ret_30, range_15, open_vol_share_15
  trend     session_ret, close_vs_vwap, vwap_crossings, close_location, afternoon_ret, slope
  volume    rel_volume_20, vol_accel, last_hour_share, close_vs_vpoc
  path      mfe_open, mae_open, minute_of_high, minute_of_low, recovery_from_low, reversals_15
  relative  vs_nifty (session return minus NIFTY 50's)
  circuit   near_lower_band, near_upper_band (closest approach to an NSE band, as a fraction),
            frozen_bars (bars with open = high = low = close)
VWAP uses the typical price (high + low + close) / 3. VPOC is the typical price of the
15-minute bar with the most volume.
"""

from __future__ import annotations

from typing import Dict, Optional, Sequence

import numpy as np
import pandas as pd

CODE_VERSION = "intraday_features v1"
BANDS = (0.02, 0.05, 0.10, 0.20)
DESCRIPTORS = ["gap", "ret_15", "ret_30", "range_15", "open_vol_share_15", "session_ret", "close_vs_vwap",
               "vwap_crossings", "close_location", "afternoon_ret", "slope", "rel_volume_20", "vol_accel",
               "last_hour_share", "close_vs_vpoc", "mfe_open", "mae_open", "minute_of_high", "minute_of_low",
               "recovery_from_low", "reversals_15", "vs_nifty", "near_lower_band", "near_upper_band", "frozen_bars"]


def typical(df: pd.DataFrame) -> np.ndarray:
    return ((df["high"] + df["low"] + df["close"]) / 3.0).to_numpy(float)


def vwap(df: pd.DataFrame) -> float:
    if df.empty:
        return float("nan")
    v = df["volume"].to_numpy(float)
    tp = typical(df)
    return float((tp * v).sum() / v.sum()) if v.sum() > 0 else float(tp.mean())


def vpoc(df3: pd.DataFrame) -> float:
    """Typical price of the 15-minute bar (five 3-minute bars from 09:15) with the most volume."""
    if df3.empty:
        return float("nan")
    k = np.arange(len(df3)) // 5
    g = df3.assign(k=k).groupby("k")
    b = pd.DataFrame({"high": g["high"].max(), "low": g["low"].min(), "close": g["close"].last(), "volume": g["volume"].sum()})
    return float(typical(b.loc[[b["volume"].idxmax()]])[0])


def _minutes(df: pd.DataFrame) -> np.ndarray:
    t = df["timestamp"]
    return ((t.dt.hour * 60 + t.dt.minute) - (9 * 60 + 15)).to_numpy(int)


def descriptors(day: pd.DataFrame, prev_close: float, prev_volumes: Sequence[float],
                nifty_day: Optional[pd.DataFrame] = None) -> Dict[str, float]:
    d = day.sort_values("timestamp").reset_index(drop=True)
    out = {k: float("nan") for k in DESCRIPTORS}
    if d.empty or not (prev_close > 0):
        return out
    o, c = float(d["open"].iloc[0]), float(d["close"].iloc[-1])
    hi, lo = float(d["high"].max()), float(d["low"].min())
    vol = d["volume"].to_numpy(float)
    V = vol.sum()
    m = _minutes(d)
    f15, f30 = d[m < 15], d[m < 30]
    out.update({"gap": o / prev_close - 1, "session_ret": c / o - 1, "mfe_open": hi / o - 1, "mae_open": lo / o - 1,
                "close_location": (c - lo) / (hi - lo) if hi > lo else 0.5,
                "minute_of_high": float(m[int(d["high"].to_numpy().argmax())]),
                "minute_of_low": float(m[int(d["low"].to_numpy().argmin())]),
                "recovery_from_low": (c - lo) / (o - lo) if o > lo else float("nan"),
                "frozen_bars": float(((d["open"] == d["high"]) & (d["high"] == d["low"]) & (d["low"] == d["close"])).sum())})
    if len(f15):
        out["ret_15"] = float(f15["close"].iloc[-1]) / o - 1
        out["range_15"] = (float(f15["high"].max()) - float(f15["low"].min())) / o
        out["open_vol_share_15"] = float(f15["volume"].sum()) / V if V > 0 else float("nan")
    if len(f30):
        out["ret_30"] = float(f30["close"].iloc[-1]) / o - 1
    vw = vwap(d)
    out["close_vs_vwap"] = c / vw - 1 if vw > 0 else float("nan")
    cv = np.cumsum(typical(d) * vol)
    cs = np.cumsum(vol)
    run = np.where(cs > 0, cv / np.where(cs > 0, cs, 1), typical(d))
    side = np.sign(d["close"].to_numpy(float) - run)
    side = side[side != 0]
    out["vwap_crossings"] = float((np.diff(side) != 0).sum()) if len(side) > 1 else 0.0
    aft = d[m >= 240]                                                  # 13:15 onwards
    pre = d[m < 240]
    if len(aft) and len(pre):
        out["afternoon_ret"] = c / float(pre["close"].iloc[-1]) - 1
    lp = np.log(d["close"].to_numpy(float))
    if len(lp) > 2:
        out["slope"] = float(np.polyfit(np.arange(len(lp)), lp, 1)[0] * len(lp))
    pv = np.asarray([v for v in prev_volumes if np.isfinite(v) and v > 0], float)
    out["rel_volume_20"] = V / float(np.median(pv)) if len(pv) >= 10 and V > 0 else float("nan")
    half = len(vol) // 2
    out["vol_accel"] = vol[half:].sum() / vol[:half].sum() if vol[:half].sum() > 0 else float("nan")
    out["last_hour_share"] = float(vol[m >= 315].sum()) / V if V > 0 else float("nan")   # 14:30 onwards
    vp = vpoc(d)
    out["close_vs_vpoc"] = c / vp - 1 if vp > 0 else float("nan")
    c15 = d.assign(k=np.arange(len(d)) // 5).groupby("k")["close"].last().to_numpy(float)
    dirs = np.sign(np.diff(c15))
    dirs = dirs[dirs != 0]
    out["reversals_15"] = float((np.diff(dirs) != 0).sum()) if len(dirs) > 1 else 0.0
    if nifty_day is not None and len(nifty_day):
        n = nifty_day.sort_values("timestamp")
        out["vs_nifty"] = (c / o - 1) - (float(n["close"].iloc[-1]) / float(n["open"].iloc[0]) - 1)
    out["near_lower_band"] = min(abs(lo / prev_close - (1 - b)) for b in BANDS)
    out["near_upper_band"] = min(abs(hi / prev_close - (1 + b)) for b in BANDS)
    return out
