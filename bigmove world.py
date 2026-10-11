"""
tests/bigmove_world.py - a synthetic NSE-like market for testing bigmove_study: daily bars from `start`, 3-minute bars
(125 a session) from `bar_start`, NIFTY daily and 3-minute bars, and switches that PLANT one effect at a time:

  p_cat       stocks in play: a catalyst day has heavy opening volume, a first bar in its direction and a drift that persists
  cat_mode    "both" (both directions persist) or "short_only" (up catalysts reverse after the first bar)
  state       a state-driven big day: after the 20-day distance falls below -8%, the next session trends (random way),
              with ordinary volume - only the similar-day memory can see it coming
  interact    move potential x participation: a stock is LOADED when its 20-day distance is below `state_thresh`
              (a loaded day ranges wider and trades `loaded_volume` x volume, but has no direction of its own); a
              catalyst only keeps going on a LOADED day - the payoff needs both (the RV x MFE hypothesis, H2)
  nifty_trend / beta   NIFTY trends on half the days (direction in its first bar); stocks follow with beta
  open_kick   every stock-day's first bar gets +/- open_kick (random sign): the stock's own opening no longer shows
              a shared direction, so only NIFTY's or the sector's opening can (the gate worlds)
  n_sectors / sector_trend   stocks belong to sectors; on half the days a sector trends together (kick + drift);
              sector_mode "against_nifty": sectors trend only on NIFTY's trend days, the OTHER way (market and sector
              disagree)
  idio_trend  each stock trends alone on half its days (same kick and drift): a market with trend days that NIFTY
              and the sector know nothing about (the null for the gates)
Everything else is a random walk. Each bar's high and low are those of a continuous path (Brownian bridge), so a stop
order filled at its level is a fair fill: on a driftless walk the breakout earns nothing before costs.

RANDOM STREAMS: every mechanism draws from its own stream (spawned from `seed`) and draws the same amount whether it
is switched on or not. Switching one effect on therefore leaves every other random number unchanged: the same seed
with and without catalysts gives identical returns and volumes on every stock-day without a catalyst (up to the price
LEVEL, which a catalyst day carries forward). Truth flags are returned for checking.
"""

from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

NB = 125
OFF = pd.to_timedelta(555 + 3 * np.arange(NB), unit="m")
USHAPE = np.r_[np.linspace(1.8, 0.8, 40), np.full(45, 0.7), np.linspace(0.8, 1.4, 40)]
USHAPE = USHAPE / USHAPE.mean()
STREAMS = ("nifty", "nifty_trend", "base", "catalyst", "state", "open_kick", "sector", "idio", "bars", "nifty_bars")
MAX_SECTORS = 16


def _bars(o: float, rets: np.ndarray, s_bar, u1: np.ndarray, u2: np.ndarray):
    """Bars of a continuous price path: each bar's high and low are the exact maximum and minimum of a Brownian bridge
    (log price, per-bar sd s_bar) between its open and close, drawn from the uniforms u1, u2 in (0, 1]."""
    lc = np.log(o) + np.cumsum(rets)
    lo_ = np.r_[np.log(o), lc[:-1]]
    s2 = np.broadcast_to(np.asarray(s_bar, float) ** 2, (NB,))
    hx = (lo_ + lc + np.sqrt((lc - lo_) ** 2 - 2 * s2 * np.log(u1))) / 2
    lx = (lo_ + lc - np.sqrt((lc - lo_) ** 2 - 2 * s2 * np.log(u2))) / 2
    return np.exp(lo_), np.exp(hx), np.exp(lx), np.exp(lc)


def make_world(n: int = 48, seed: int = 0, start: str = "2023-06-01", bar_start: str = "2024-07-01", end: str = "2025-03-31",
               p_cat: float = 0.0, cat_mode: str = "both", cat_drift: float = 0.025, cat_vol: float = 6.0,
               state: bool = False, state_drift: float = 0.035, nifty_trend: bool = False, beta: float = 0.0,
               sigma: float = 0.018, open_kick: float = 0.0, idio_trend: bool = False, n_sectors: int = 0,
               sector_trend: bool = False, sector_mode: str = "independent", trend_kick: float = 0.003,
               trend_drift: float = 0.012, interact: bool = False, state_thresh: float = -0.08, loaded_vol: float = 2.0,
               loaded_volume: float = 1.6) -> Dict[str, object]:
    if n_sectors > MAX_SECTORS:
        raise ValueError(f"at most {MAX_SECTORS} sectors")
    R = {k: np.random.default_rng(c) for k, c in zip(STREAMS, np.random.SeedSequence(seed).spawn(len(STREAMS)))}
    days = pd.bdate_range(start, end)
    T = len(days)
    bstart = pd.Timestamp(bar_start)
    # NIFTY: noise, gaps and trend days from their own streams (the trend draws happen whether or not it is on)
    n_ret = R["nifty"].normal(0, 0.009 / np.sqrt(NB), (T, NB))
    n_gap = R["nifty"].normal(0, 0.002, T)
    t_on, t_dir = R["nifty_trend"].random(T) < 0.5, R["nifty_trend"].choice([-1, 1], T)
    n_dir = np.where(t_on & nifty_trend, t_dir, 0)
    n_ret[:, 0] += n_dir * trend_kick
    n_ret[:, 1:] += (n_dir * trend_drift / (NB - 1))[:, None]
    nu = 1.0 - R["nifty_bars"].random((T, 2, NB))
    n_daily, n_bars = [], []
    pc = 20000.0
    for d in range(T):
        o = pc * np.exp(n_gap[d])
        op, h, l, c = _bars(o, n_ret[d], 0.009 / np.sqrt(NB), nu[d, 0], nu[d, 1])
        n_daily.append((days[d], op[0], h.max(), l.min(), c[-1]))
        if days[d] >= bstart:
            n_bars.append(pd.DataFrame({"timestamp": days[d] + OFF, "open": op, "high": h, "low": l, "close": c, "volume": 0.0}))
        pc = c[-1]
    nifty_daily = pd.DataFrame(n_daily, columns=["timestamp", "open", "high", "low", "close"])
    nifty_bars = pd.concat(n_bars, ignore_index=True)
    # sectors: trend days and directions for MAX_SECTORS sectors, always drawn
    s_on, s_dir = R["sector"].random((MAX_SECTORS, T)) < 0.5, R["sector"].choice([-1, 1], (MAX_SECTORS, T))
    if n_sectors and sector_trend and sector_mode == "against_nifty":
        sec_dir = np.tile(-n_dir, (MAX_SECTORS, 1))
    elif n_sectors and sector_trend:
        sec_dir = np.where(s_on, s_dir, 0)
    else:
        sec_dir = np.zeros((MAX_SECTORS, T), int)
    daily, intra, truth, sector_of = {}, {}, [], {}
    for s in range(n):
        sym = f"S{s:03d}"
        if n_sectors:
            sector_of[sym] = f"SEC{s % n_sectors}"
        # every stream draws its full block for this stock, used or not
        p = float(R["base"].uniform(300, 2000))
        vol0 = float(R["base"].uniform(4e5, 1.2e6))
        gap = R["base"].normal(0, 0.003, T)
        noise = R["base"].normal(0, 1.0, (T, NB))
        vnoise = R["base"].lognormal(0, 0.3, (T, NB))
        c_on, c_dir = R["catalyst"].random(T), R["catalyst"].choice([-1, 1], T)
        st_dir = R["state"].choice([-1, 1], T)
        k_sgn = R["open_kick"].choice([-1, 1], T)
        i_on, i_dir = R["idio"].random(T) < 0.5, R["idio"].choice([-1, 1], T)
        uu = 1.0 - R["bars"].random((T, 2, NB))
        closes, rows, bars = [], [], []
        for d in range(T):
            o = p * np.exp(gap[d])
            loaded = bool(interact and len(closes) >= 20 and closes[-1] / np.mean(closes[-20:]) - 1 < state_thresh)
            sb = sigma / np.sqrt(NB) * (loaded_vol if loaded else 1.0)
            rets = noise[d] * sb + beta * n_ret[d]
            vols = vol0 / NB * USHAPE * vnoise[d]
            cat = 0
            if p_cat > 0 and c_on[d] < p_cat:
                cat = int(c_dir[d])
                persist = 1 if (cat_mode == "both" or cat < 0) else -1
                rets[0] += cat * 0.004
                if not interact or loaded:
                    rets[1:] += persist * cat * cat_drift / (NB - 1)
                vols[0] *= cat_vol
                vols[1:] *= 2.0
            elif loaded:
                vols *= loaded_volume
            st = 0
            if state and len(closes) >= 20 and closes[-1] / np.mean(closes[-20:]) - 1 < -0.08:
                st = int(st_dir[d])
                rets[0] += st * 0.004
                rets[1:] += st * state_drift / (NB - 1)
            if interact and loaded:
                st = 1
            if open_kick > 0:
                rets[0] += k_sgn[d] * open_kick
            sd_ = int(sec_dir[s % n_sectors, d]) if n_sectors else 0
            if sd_:
                rets[0] += sd_ * trend_kick
                rets[1:] += sd_ * trend_drift / (NB - 1)
            idd = int(i_dir[d]) if (idio_trend and i_on[d]) else 0
            if idd:
                rets[0] += idd * trend_kick
                rets[1:] += idd * trend_drift / (NB - 1)
            s_bar = np.sqrt(sb ** 2 + (beta * 0.009 / np.sqrt(NB)) ** 2)
            op, h, l, c = _bars(o, rets, s_bar, uu[d, 0], uu[d, 1])
            rows.append((days[d], op[0], h.max(), l.min(), c[-1], vols.sum()))
            if days[d] >= bstart:
                bars.append(pd.DataFrame({"timestamp": days[d] + OFF, "open": op, "high": h, "low": l, "close": c, "volume": vols}))
                truth.append((days[d], sym, cat, st, sd_, idd))
            closes.append(c[-1])
            p = c[-1]
        daily[sym] = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        intra[sym] = pd.concat(bars, ignore_index=True)
    truth = pd.DataFrame(truth, columns=["day", "symbol", "catalyst", "state", "sector_dir", "idio_dir"])
    return {"daily": daily, "intra": intra, "nifty_daily": nifty_daily, "nifty_bars": nifty_bars, "truth": truth, "nifty_dir": n_dir,
            "days": days, "sector_of": sector_of}
