#!/usr/bin/env python3
"""
soul_intraday_study.py - Soul + intraday Soul: what state is each pick in, how did similar
moments behave before, and which targets fit which state.

    python soul_intraday_study.py --root %CACHE_DAILY_ROOT%

Rules: SOUL_INTRADAY_DECLARATION.json (exploration mode, fixed before the first run).
Second pipeline: reads intraday_v1's frozen candidate set, the daily cache and
<root>\\intraday_3m\\; writes only <root>\\research2\\soul_intraday\\SI_YYYYMMDD_NNN\\.
Descriptive: it changes nothing.

1. STATE of every stock-day: 10 daily dimensions, 3 transitions, 10 pick-day dimensions
   (4 from the daily bar, 6 from 3-minute bars) as same-day percentiles, plus readable
   labels: daily regime, intraday regime, intraday shape, regime transition, 3-day sequence.
2. MEMORY of every traded pick: the 50 most similar earlier pick-moments (all stocks), the
   stock's own 20 most similar earlier days, and its own 20 most similar earlier days with
   3-minute bars. Only moments 6+ sessions before the pick count (no look-ahead).
3. BEHAVIOUR by state, memory ACCURACY (incl. whether the intraday state adds anything), and
   TARGETS - normal, state-specific, stock-specific - with win rate, average profit and the
   paired difference against the 5th close.

Everything below main() uses numpy and pandas only; main() loads the data with the shipped
tools (stage_e_execution, data_quality, intraday_cache).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

CODE_VERSION = "soul_intraday_study v1.1"   # v1.1: horizon embargo (7th/10th close), thin-bar guard, universe counts, report wording
DECL_RAW = (HERE / "SOUL_INTRADAY_DECLARATION.json").read_bytes()
DECL = json.loads(DECL_RAW.decode("utf-8"))
CFG = DECL["config"]
COST = CFG["cost_bps"] / 1e4

D_COLS = ["mom5", "mom20", "mom60", "vol20", "vol_ratio", "dd60", "dist20", "volu_ratio", "ovn20", "rsi14"]
TRANS = ["mom20", "vol_ratio", "volu_ratio"]
I_DAILY = ["gap", "session_ret", "close_loc", "rel_volume"]
I_BARS = ["close_vs_vwap", "last_hour_share", "afternoon_ret", "ret_30", "low_minute", "high_minute"]
X_COLS = ["x_ret30", "x_mae", "x_mfe", "x_ret", "x_low_minute", "x_low_in_30"]          # a session's own behaviour
S1_COLS = ["s1_ret30", "s1_mae", "s1_mfe", "s1_ret", "s1_low_minute", "s1_low_in_30"]   # ... of the NEXT session
HORIZONS = ["CLOSE_3", "CLOSE_5", "OPEN_6", "CLOSE_7", "CLOSE_10"]
HORIZON_K = {"CLOSE_3": 3, "CLOSE_5": 5, "OPEN_6": 6, "CLOSE_7": 7, "CLOSE_10": 10}   # sessions after the moment until the exit is known
PCT_COLS = D_COLS + I_DAILY + I_BARS
SET_DAILY = ["p_" + c for c in D_COLS] + ["t_" + c for c in TRANS]
SET_DAY_PLUS = SET_DAILY + ["p_" + c for c in I_DAILY]
SET_FULL = SET_DAY_PLUS + ["p_" + c for c in I_BARS]
KEEP_RAW = ["gap", "close_loc", "low_minute", "atr14"]

TREND, VOLA = ["DOWN", "FLAT", "UP"], ["CALM", "NORMAL", "WILD"]
GAPS, CLOSES, LOWS = ["GAPDOWN", "FLAT", "GAPUP"], ["WEAK", "MID", "STRONG"], ["EARLY_LOW", "LATE_LOW"]
REGIMES = [f"{a}-{b}" for a in TREND for b in VOLA]
IREGIMES = [f"{a}-{b}" for a in GAPS for b in CLOSES]
SHAPES = [f"{a}-{b}" for a in LOWS for b in CLOSES]
SEQ = [f"{a}{b}{c}" for a in "WMS" for b in "WMS" for c in "WMS"]


class PreconditionError(SystemExit):
    pass


def _log(msg: str) -> None:
    print(f"{dt.datetime.now():%H:%M:%S}  {msg}", flush=True)


def _naive_days(s) -> pd.Series:
    t = pd.to_datetime(pd.Series(s).reset_index(drop=True))
    if getattr(t.dt, "tz", None) is not None:
        t = t.dt.tz_localize(None)
    return t.dt.normalize().astype("datetime64[ns]")


# ----------------------------------------------------------------------
# 1. states
# ----------------------------------------------------------------------
def rsi(c: pd.Series, n: int = 14) -> pd.Series:
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    with np.errstate(divide="ignore", invalid="ignore"):
        val = 100 - 100 / (1 + up / dn)
    return pd.Series(np.where(dn.isna(), np.nan, np.where(dn > 0, val, 100.0)), index=c.index)


def daily_frame(df: pd.DataFrame) -> pd.DataFrame:
    """One row per session: the daily state's raw dimensions, the pick-day dimensions the daily bar
    knows, ATR, and the outcomes of buying at the NEXT open (plain prices)."""
    d = df.copy()
    d["day"] = _naive_days(d["timestamp"]).to_numpy()
    d = d.sort_values("day").drop_duplicates("day", keep="last").reset_index(drop=True)
    o, h, l, c = (d[k].astype(float) for k in ("open", "high", "low", "close"))
    v = d["volume"].astype(float) if "volume" in d.columns else pd.Series(np.nan, index=d.index)
    r = np.log(c).diff()
    F = pd.DataFrame({"day": d["day"]})
    F["mom5"], F["mom20"], F["mom60"] = c / c.shift(5) - 1, c / c.shift(20) - 1, c / c.shift(60) - 1
    F["vol20"] = r.rolling(20).std()
    F["vol_ratio"] = r.rolling(5).std() / r.rolling(60).std()
    F["dd60"] = c / c.rolling(60).max() - 1
    F["dist20"] = c / c.rolling(20).mean() - 1
    F["volu_ratio"] = v.rolling(5).mean() / v.rolling(60).mean()
    F["ovn20"] = (o / c.shift(1) - 1).rolling(20).sum()
    F["rsi14"] = rsi(c, 14)
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    F["atr14"] = tr.rolling(14).mean() / c
    F["gap"] = o / c.shift(1) - 1
    F["session_ret"] = c / o - 1
    rng = h - l
    F["close_loc"] = np.where(rng > 0, (c - l) / rng.where(rng > 0, 1.0), 0.5)
    F["rel_volume"] = v / v.shift(1).rolling(20, min_periods=10).median()
    entry = o.shift(-1)
    F["mfe5"] = h.shift(-1).rolling(5).max().shift(-4) / entry - 1
    F["mae5"] = l.shift(-1).rolling(5).min().shift(-4) / entry - 1
    for k in (3, 5, 7, 10):
        F[f"CLOSE_{k}"] = c.shift(-k) / entry - 1 - COST
    F["OPEN_6"] = o.shift(-6) / entry - 1 - COST
    return F.replace([np.inf, -np.inf], np.nan)


def session_stats(X: Optional[pd.DataFrame]) -> pd.DataFrame:
    """Per session from 3-minute bars: the 6 bar-based pick-day dimensions and the session's own behaviour."""
    cols = ["day"] + I_BARS + X_COLS
    if X is None or len(X) == 0:
        return pd.DataFrame(columns=cols)
    t = pd.to_datetime(X["timestamp"])
    if getattr(t.dt, "tz", None) is not None:
        t = t.dt.tz_localize(None)
    F = pd.DataFrame({"day": t.dt.normalize().astype("datetime64[ns]").to_numpy(), "m": ((t.dt.hour * 60 + t.dt.minute) - 555).to_numpy(),
                      "o": X["open"].to_numpy(float), "h": X["high"].to_numpy(float), "l": X["low"].to_numpy(float),
                      "c": X["close"].to_numpy(float), "v": X["volume"].to_numpy(float)})
    F = F.sort_values(["day", "m"], kind="stable").reset_index(drop=True)
    F["tp"] = (F["h"] + F["l"] + F["c"]) / 3.0
    F["pv"] = F["tp"] * F["v"]
    g = F.groupby("day", sort=True)
    A = pd.DataFrame({"o1": g["o"].first(), "hi": g["h"].max(), "lo": g["l"].min(), "cN": g["c"].last(), "vol": g["v"].sum(),
                      "pv": g["pv"].sum(), "tpm": g["tp"].mean()})
    A["vwap"] = (A["pv"] / A["vol"].where(A["vol"] > 0)).fillna(A["tpm"])
    A["c30"] = F[F["m"] < 30].groupby("day")["c"].last()
    A["c240"] = F[F["m"] < 240].groupby("day")["c"].last()
    A["vlast"] = F[F["m"] >= 315].groupby("day")["v"].sum()
    A["low_minute"] = F.loc[g["l"].idxmin().to_numpy(), "m"].to_numpy().astype(float)
    A["high_minute"] = F.loc[g["h"].idxmax().to_numpy(), "m"].to_numpy().astype(float)
    S = pd.DataFrame(index=A.index)
    S["close_vs_vwap"] = A["cN"] / A["vwap"] - 1
    S["last_hour_share"] = (A["vlast"].fillna(0.0) / A["vol"]).where(A["vol"] > 0)
    S["afternoon_ret"] = A["cN"] / A["c240"] - 1
    S["ret_30"] = A["c30"] / A["o1"] - 1
    S["low_minute"], S["high_minute"] = A["low_minute"], A["high_minute"]
    S["x_ret30"] = S["ret_30"]
    S["x_mae"] = A["lo"] / A["o1"] - 1
    S["x_mfe"] = A["hi"] / A["o1"] - 1
    S["x_ret"] = A["cN"] / A["o1"] - 1
    S["x_low_minute"] = A["low_minute"]
    S["x_low_in_30"] = (A["low_minute"] < 30).astype(float)
    S.index.name = "day"
    return S.reset_index()[cols]


def build_panel(daily: Dict[str, pd.DataFrame], intra_loader: Optional[Callable[[str], Optional[pd.DataFrame]]] = None,
                start: Optional[str] = None, log: Optional[Callable[[str], None]] = None) -> pd.DataFrame:
    """Every stock-day from `start`: raw dimensions, session-1 behaviour (from the next session's bars), outcomes.
    Bars are read one stock at a time (intra_loader) and dropped, so the full 3-minute history never sits in memory."""
    parts = []
    t0 = pd.Timestamp(start) if start else None
    for k, s in enumerate(sorted(daily)):
        F = daily_frame(daily[s])
        S = session_stats(intra_loader(s) if intra_loader else None)
        if len(S):
            S["day"] = pd.to_datetime(S["day"]).astype("datetime64[ns]")
            F = F.merge(S, on="day", how="left")
        else:
            for col in I_BARS + X_COLS:
                F[col] = np.nan
        for a, b in zip(X_COLS, S1_COLS):
            F[b] = F[a].shift(-1)
        F["has_bars"] = F["low_minute"].notna()
        F = F.drop(columns=X_COLS)
        F["symbol"] = s
        if t0 is not None:
            F = F[F["day"] >= t0]
        num = [c for c in F.columns if c not in ("day", "symbol", "has_bars")]
        F[num] = F[num].astype("float32")
        parts.append(F)
        if log and (k + 1) % 200 == 0:
            log(f"  states: {k + 1:,}/{len(daily):,} stocks")
    P = pd.concat(parts, ignore_index=True)
    P["symbol"] = P["symbol"].astype("category")
    return P


def _codes3(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    out = np.where(x < lo, 0, np.where(x > hi, 2, 1)).astype(np.int16)
    return np.where(np.isnan(x), -1, out).astype(np.int16)


def add_states(P: pd.DataFrame, calendar: Optional[np.ndarray] = None) -> pd.DataFrame:
    """Same-day percentiles, 5-session transitions and label codes (-1 = not available)."""
    R = P.groupby("day", sort=False, observed=True)[PCT_COLS].rank(pct=True)
    for c in PCT_COLS:
        P["p_" + c] = R[c].astype("float32")
    del R
    P = P.sort_values(["symbol", "day"], kind="stable").reset_index(drop=True)
    g = P.groupby("symbol", sort=False, observed=True)
    for c in TRANS:
        P["t_" + c] = (P["p_" + c] - g["p_" + c].shift(5)).astype("float32")
    tr, vo = _codes3(P["p_mom20"].to_numpy(float), 1 / 3, 2 / 3), _codes3(P["p_vol20"].to_numpy(float), 1 / 3, 2 / 3)
    P["regime"] = np.where((tr < 0) | (vo < 0), -1, tr * 3 + vo).astype(np.int16)
    gp = _codes3(P["gap"].to_numpy(float), -CFG["gap_flat"], CFG["gap_flat"])
    cl = _codes3(P["close_loc"].to_numpy(float), 1 / 3, 2 / 3)
    P["iregime"] = np.where((gp < 0) | (cl < 0), -1, gp * 3 + cl).astype(np.int16)
    lm = P["low_minute"].to_numpy(float)
    lw = np.where(np.isnan(lm), -1, np.where(lm < CFG["early_low_minute"], 0, 1))
    P["shape"] = np.where((lw < 0) | (cl < 0), -1, lw * 3 + cl).astype(np.int16)
    P["cl"] = cl
    g = P.groupby("symbol", sort=False, observed=True)
    prev = g["regime"].shift(5).fillna(-1).to_numpy(int)
    reg = P["regime"].to_numpy(int)
    P["transition"] = np.where((prev < 0) | (reg < 0), -1, prev * 9 + reg).astype(np.int16)
    c2, c1 = g["cl"].shift(2).fillna(-1).to_numpy(int), g["cl"].shift(1).fillna(-1).to_numpy(int)
    c0 = cl.astype(int)
    P["seq3"] = np.where((c2 < 0) | (c1 < 0) | (c0 < 0), -1, c2 * 9 + c1 * 3 + c0).astype(np.int16)
    cal = np.sort(P["day"].unique()) if calendar is None else calendar
    P["pos"] = np.searchsorted(cal, P["day"].to_numpy()).astype(np.int32)
    drop = [c for c in PCT_COLS if c not in KEEP_RAW and c in P.columns] + ["cl"]
    return P.drop(columns=drop)                          # raw values are no longer needed: keeps memory down


def label(kind: str, code: int) -> str:
    if code < 0:
        return "NA"
    if kind == "regime":
        return REGIMES[code]
    if kind == "iregime":
        return IREGIMES[code]
    if kind == "shape":
        return SHAPES[code]
    if kind == "seq3":
        return SEQ[code]
    if kind == "transition":
        a, b = divmod(int(code), 9)
        return f"{REGIMES[a]} > {REGIMES[b]}"
    raise ValueError(kind)


def stability(P: pd.DataFrame) -> pd.DataFrame:
    """Share of sessions whose daily regime is unchanged the next session, overall and per regime."""
    nxt = P.groupby("symbol", sort=False, observed=True)["regime"].shift(-1)
    ok = (P["regime"] >= 0) & nxt.notna() & (nxt >= 0)
    same = (P["regime"] == nxt) & ok
    rows = [{"state": "ALL", "days": int(ok.sum()), "same_next_day": float(same[ok].mean()) if ok.any() else np.nan}]
    for code in range(9):
        m = ok & (P["regime"] == code)
        if m.any():
            rows.append({"state": REGIMES[code], "days": int(m.sum()), "same_next_day": float(same[m].mean())})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------
# 2. memory
# ----------------------------------------------------------------------
def nan_dist(q: np.ndarray, C: np.ndarray) -> np.ndarray:
    """Squared distance skipping missing dimensions, rescaled to all dimensions; inf when fewer than half
    of the query's available dimensions are shared."""
    diff = C - q
    ok = ~np.isnan(diff)
    cnt = ok.sum(1)
    need = max(1, int(np.ceil(0.5 * np.isfinite(q).sum())))
    d2 = np.where(ok, diff * diff, 0.0).sum(1) * (len(q) / np.maximum(cnt, 1))
    d2[cnt < need] = np.inf
    return d2


def knn(Q: np.ndarray, qpos: np.ndarray, C: np.ndarray, cpos: np.ndarray, k: int, lag: int) -> List[np.ndarray]:
    """For each query, the indices (into C) of its k nearest rows among those at least `lag` sessions earlier."""
    order = np.argsort(cpos, kind="stable")
    Cs, ps = C[order], cpos[order]
    out = []
    for i in range(len(Q)):
        n = int(np.searchsorted(ps, qpos[i] - lag, side="right"))
        if n == 0 or not np.isfinite(Q[i]).any():
            out.append(np.empty(0, int))
            continue
        d2 = nan_dist(Q[i], Cs[:n])
        fin = np.flatnonzero(np.isfinite(d2))
        if len(fin) == 0:
            out.append(np.empty(0, int))
            continue
        if len(fin) > k:
            fin = fin[np.argpartition(d2[fin], k - 1)[:k]]
        out.append(order[fin[np.argsort(d2[fin], kind="stable")]])
    return out


def summarise(nb: np.ndarray, M: pd.DataFrame, minimum: int = 1, qpos: Optional[int] = None) -> dict:
    """What followed a set of moments (rows of M): mean 5-session net, MFE percentiles, chance of +5%,
    the mean net at each horizon and the best one, and the next session's intraday behaviour.
    HORIZON EMBARGO: a moment's exit at horizon h counts only if it was already known on the pick day
    (moment position + sessions to the exit <= the pick's position) - the 6-session lag covers the 5-session
    outcome, not the 7th and 10th closes."""
    out = {"n": int(len(nb))}
    if len(nb) < minimum:
        return out
    S = M.iloc[nb]
    mfe = S["mfe5"].to_numpy(float)
    mfe = mfe[np.isfinite(mfe)]
    out["net5"] = float(np.nanmean(S["CLOSE_5"].to_numpy(float)))
    if len(mfe):
        out.update({"mfe_q30": float(np.quantile(mfe, 0.3)), "mfe_q50": float(np.quantile(mfe, 0.5)),
                    "mfe_q70": float(np.quantile(mfe, 0.7)), "p5": float((mfe >= 0.05).mean())})
    npos = S["pos"].to_numpy()
    hm = []
    for h in HORIZONS:
        v = S[h].to_numpy(float)
        if qpos is not None:
            v = np.where(npos + HORIZON_K[h] <= qpos, v, np.nan)
        hm.append(float(np.nanmean(v)) if np.isfinite(v).sum() >= max(1, len(S) // 2) else np.nan)
    for h, v in zip(HORIZONS, hm):
        out["h_" + h] = float(v)
    if np.isfinite(hm).any():
        out["h_best"] = int(np.nanargmax(hm))
    for c in ("s1_mae", "s1_ret30", "s1_low_in_30"):
        v = S[c].to_numpy(float)
        if np.isfinite(v).any():
            out[c] = float(np.nanmean(v))
    v = S["s1_low_minute"].to_numpy(float)
    if np.isfinite(v).any():
        out["s1_low_minute"] = float(np.nanmedian(v))
    out["n_s1"] = int(S["s1_mae"].notna().sum())
    return out


def regime_quantile(qcode: np.ndarray, qpos: np.ndarray, pcode: np.ndarray, ppos: np.ndarray, pval: np.ndarray,
                    lag: int, minimum: int, q: float = 0.5) -> np.ndarray:
    """For each query: the q-quantile of pval among earlier pool moments (lag) with the same label code."""
    out = np.full(len(qcode), np.nan)
    for code in np.unique(qcode[qcode >= 0]):
        m = (pcode == code) & np.isfinite(pval)
        o = np.argsort(ppos[m], kind="stable")
        ps, vs = ppos[m][o], pval[m][o]
        for i in np.flatnonzero(qcode == code):
            n = int(np.searchsorted(ps, qpos[i] - lag, side="right"))
            if n >= minimum:
                out[i] = float(np.quantile(vs[:n], q))
    return out


MEM_KEYS = ["n", "net5", "mfe_q30", "mfe_q50", "mfe_q70", "p5", "h_best"] + ["h_" + h for h in HORIZONS] + \
           ["s1_mae", "s1_ret30", "s1_low_in_30", "s1_low_minute", "n_s1"]


def memories(P: pd.DataFrame, pool_rows: np.ndarray, query_rows: np.ndarray, log=None) -> Tuple[pd.DataFrame, dict]:
    """Cross (full / daily-only / daily+) and own (daily / intraday) memories for each query row of P.
    Returns the summaries and, for checking, the positions of every neighbour used."""
    lag, kc, ko = CFG["lag_sessions"], CFG["k_cross"], CFG["k_own"]
    pool = P.iloc[pool_rows].reset_index(drop=True)
    Q = P.iloc[query_rows].reset_index(drop=True)
    qpos, ppos = Q["pos"].to_numpy(), pool["pos"].to_numpy()
    out = pd.DataFrame({"row": query_rows})
    info = {"query_pos": qpos}
    for tag, cols in (("cm", SET_FULL), ("cmd", SET_DAILY), ("cmp", SET_DAY_PLUS)):
        nbs = knn(Q[cols].to_numpy(float), qpos, pool[cols].to_numpy(float), ppos, kc, lag)
        S = pd.DataFrame([summarise(nb, pool, CFG["min_cross"], int(qp)) for nb, qp in zip(nbs, qpos)]).reindex(columns=MEM_KEYS)
        out = out.join(S.add_prefix(tag + "_"))
        info[tag] = [ppos[nb] for nb in nbs]
        if log:
            log(f"  cross memory ({tag}) done")
    groups = P.groupby(P["symbol"].astype(str), sort=False).indices
    sym = Q["symbol"].astype(str).to_numpy()
    own, owni = [None] * len(Q), [None] * len(Q)
    info["own"], info["own_intraday"] = [None] * len(Q), [None] * len(Q)
    c5, hb, s1 = P["CLOSE_5"].to_numpy(float), P["has_bars"].to_numpy(bool), P["s1_mae"].to_numpy(float)
    for s_ in np.unique(sym):
        rows = groups[s_]
        hist = P.iloc[rows[np.isfinite(c5[rows])]].reset_index(drop=True)
        histi = P.iloc[rows[hb[rows] & np.isfinite(s1[rows])]].reset_index(drop=True)
        qi = np.flatnonzero(sym == s_)
        hp, hip = hist["pos"].to_numpy(), histi["pos"].to_numpy()
        nb1 = knn(Q.loc[qi, SET_DAILY].to_numpy(float), qpos[qi], hist[SET_DAILY].to_numpy(float), hp, ko, lag)
        nb2 = knn(Q.loc[qi, SET_FULL].to_numpy(float), qpos[qi], histi[SET_FULL].to_numpy(float), hip, ko, lag)
        for j, a, b in zip(qi, nb1, nb2):
            own[j], owni[j] = summarise(a, hist, 1, int(qpos[j])), summarise(b, histi, 1, int(qpos[j]))
            info["own"][j], info["own_intraday"][j] = hp[a], hip[b]
    out = out.join(pd.DataFrame(own).reindex(columns=MEM_KEYS).add_prefix("om_"))
    out = out.join(pd.DataFrame(owni).reindex(columns=MEM_KEYS).add_prefix("oi_"))
    pm = pool["mfe5"].to_numpy(float)
    out["rq50"] = regime_quantile(Q["regime"].to_numpy(), qpos, pool["regime"].to_numpy(), ppos, pm, lag, CFG["min_regime"])
    out["iq50"] = regime_quantile(Q["iregime"].to_numpy(), qpos, pool["iregime"].to_numpy(), ppos, pm, lag, CFG["min_regime"])
    if log:
        log("  own memories and regime targets done")
    return out, info


# ----------------------------------------------------------------------
# 3. picks, targets and rules
# ----------------------------------------------------------------------
class SymBars:
    def __init__(self, df: pd.DataFrame):
        d = df.copy()
        d["day"] = _naive_days(d["timestamp"]).to_numpy()
        d = d.sort_values("day").drop_duplicates("day", keep="last").reset_index(drop=True)
        self.days = pd.DatetimeIndex(d["day"])
        self.o, self.h, self.l, self.c = (d[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        self.idx = {t: i for i, t in enumerate(self.days)}


def plain_exits(sb: SymBars, e: int) -> Dict[str, float]:
    n = len(sb.c)
    out = {f"CLOSE_{k}": (sb.c[e + k - 1] if e + k - 1 < n else np.nan) for k in (3, 5, 7, 10)}
    out["OPEN_6"] = sb.o[e + 5] if e + 5 < n else np.nan
    return out


def target_fills(O: np.ndarray, H: np.ndarray, entry: np.ndarray, x: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Sell at entry * (1 + x) the first session the high reaches it - at the open when a later session opens
    above it. Returns (fill price, hit). Missing targets never fill."""
    x = np.where(np.isfinite(x), np.maximum(x, CFG["target_floor"]), np.nan)
    tp = entry * (1 + x)
    px, hit = np.full(len(entry), np.nan), np.zeros(len(entry), bool)
    with np.errstate(invalid="ignore"):
        for s in range(O.shape[1]):
            if s > 0:
                m = ~hit & (O[:, s] >= tp)
                px[m], hit[m] = O[m, s], True
            m = ~hit & (H[:, s] >= tp)
            px[m], hit[m] = tp[m], True
    return px, hit


TARGETS = ["T2", "T5", "T10", "T3ATR", "SQ30", "SQ50", "SQ70", "RQ50", "IQ50", "OQ30", "OQ50", "OQ70", "OQ50S"]
FAMILY = {"T2": "normal", "T5": "normal", "T10": "normal", "T3ATR": "normal", "SQ30": "state", "SQ50": "state", "SQ70": "state",
          "RQ50": "state", "IQ50": "state", "OQ30": "stock", "OQ50": "stock", "OQ70": "stock", "OQ50S": "stock"}
OTHER = ["SH", "OH", "VETO_CROSS_NEG", "VETO_OWN_NEG", "VETO_BOTH_NEG", "OPEN_6", "CLOSE_3", "CLOSE_7", "CLOSE_10"]
RULES = [f"{t}|{fb}" for t in TARGETS for fb in ("C5", "O6")] + OTHER


def target_levels(T: pd.DataFrame) -> Dict[str, np.ndarray]:
    w = T["om_n"].to_numpy(float) / (T["om_n"].to_numpy(float) + CFG["shrink_k"])
    oq, sq = T["om_mfe_q50"].to_numpy(float), T["cm_mfe_q50"].to_numpy(float)
    shr = np.where(np.isfinite(oq) & np.isfinite(sq), w * oq + (1 - w) * sq, np.where(np.isfinite(oq), oq, np.nan))
    n = len(T)
    return {"T2": np.full(n, 0.02), "T5": np.full(n, 0.05), "T10": np.full(n, 0.10), "T3ATR": 3 * T["atr14"].to_numpy(float),
            "SQ30": T["cm_mfe_q30"].to_numpy(float), "SQ50": sq, "SQ70": T["cm_mfe_q70"].to_numpy(float),
            "RQ50": T["rq50"].to_numpy(float), "IQ50": T["iq50"].to_numpy(float),
            "OQ30": T["om_mfe_q30"].to_numpy(float), "OQ50": oq, "OQ70": T["om_mfe_q70"].to_numpy(float), "OQ50S": shr}


def evaluate(T: pd.DataFrame) -> pd.DataFrame:
    """Per traded pick: net, taken and hit for every rule (T has entry, O1..O5, H1..H5, exit prices, memories)."""
    O = T[[f"O{s}" for s in range(1, 6)]].to_numpy(float)
    H = T[[f"H{s}" for s in range(1, 6)]].to_numpy(float)
    entry = T["entry"].to_numpy(float)
    px = {h: T["px_" + h].to_numpy(float) for h in HORIZONS}
    net = {h: px[h] / entry - 1 - COST for h in HORIZONS}
    cols = {"base": net["CLOSE_5"]}
    lv = target_levels(T)
    for t in TARGETS:
        fill, hit = target_fills(O, H, entry, lv[t])
        for fb, fbh in (("C5", "CLOSE_5"), ("O6", "OPEN_6")):
            r = f"{t}|{fb}"
            cols[f"net:{r}"] = np.where(hit, fill / entry - 1 - COST, net[fbh])
            cols[f"take:{r}"] = np.ones(len(T), bool)
            cols[f"hit:{r}"] = np.where(np.isfinite(lv[t]), hit.astype(float), np.nan)
    for r, key in (("SH", "cm_h_best"), ("OH", "om_h_best")):
        hb = T[key].to_numpy(float) if key in T else np.full(len(T), np.nan)
        stack = np.vstack([net[h] for h in HORIZONS])
        choice = np.where(np.isfinite(hb), hb, HORIZONS.index("CLOSE_5")).astype(int)
        cols[f"net:{r}"] = stack[choice, np.arange(len(T))]
        cols[f"take:{r}"] = np.ones(len(T), bool)
        cols[f"hit:{r}"] = np.full(len(T), np.nan)
    cneg = np.nan_to_num(T["cm_net5"].to_numpy(float), nan=1.0) < 0
    oneg = np.nan_to_num(T["om_net5"].to_numpy(float), nan=1.0) < 0
    for r, skip in (("VETO_CROSS_NEG", cneg), ("VETO_OWN_NEG", oneg), ("VETO_BOTH_NEG", cneg & oneg)):
        cols[f"net:{r}"] = net["CLOSE_5"]
        cols[f"take:{r}"] = ~skip
        cols[f"hit:{r}"] = np.full(len(T), np.nan)
    for h in ("OPEN_6", "CLOSE_3", "CLOSE_7", "CLOSE_10"):
        cols[f"net:{h}"], cols[f"take:{h}"], cols[f"hit:{h}"] = net[h], np.ones(len(T), bool), np.full(len(T), np.nan)
    return pd.concat([T.reset_index(drop=True), pd.DataFrame(cols)], axis=1)


# ----------------------------------------------------------------------
# statistics
# ----------------------------------------------------------------------
def _block_idx(n: int, B: int, block: int, rng) -> np.ndarray:
    nb = int(np.ceil(n / block))
    st = rng.integers(0, n, size=(B, nb))
    return ((st[:, :, None] + np.arange(block)[None, None, :]).reshape(B, -1)[:, :n]) % n


def boot_mean(x: np.ndarray) -> Tuple[float, float, float]:
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 20:
        return (float(x.mean()) if len(x) else np.nan), np.nan, np.nan
    means = x[_block_idx(len(x), CFG["boot_B"], CFG["boot_block"], np.random.default_rng(CFG["seed"]))].mean(1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(x.mean()), float(lo), float(hi)


def _ranks(v: np.ndarray) -> np.ndarray:
    return pd.Series(v).rank(method="average").to_numpy(float)


def boot_spearman(days: np.ndarray, pairs: List[Tuple[np.ndarray, np.ndarray]]) -> List[Tuple[float, float, float, int]]:
    """Spearman correlation of each (prediction, outcome) pair - and, for a third array, the paired difference
    of two predictions - with day-block bootstrap intervals (ranks of the full sample, resampled by day)."""
    res = []
    for pr in pairs:
        a, b = np.asarray(pr[0], float), np.asarray(pr[1], float)
        c = np.asarray(pr[2], float) if len(pr) > 2 else None
        ok = np.isfinite(a) & np.isfinite(b) & (np.isfinite(c) if c is not None else True)
        if ok.sum() < 30:
            res.append((np.nan, np.nan, np.nan, int(ok.sum())))
            continue
        d = days[ok]
        ra, rb = _ranks(a[ok]), _ranks(b[ok])
        rc = _ranks(c[ok]) if c is not None else None
        def corr(i, x, y):
            x, y = x[i] - x[i].mean(), y[i] - y[i].mean()
            den = np.sqrt((x * x).sum() * (y * y).sum())
            return float((x * y).sum() / den) if den > 0 else np.nan
        stat = lambda i: corr(i, ra, rb) - (corr(i, rc, rb) if rc is not None else 0.0)
        allidx = np.arange(len(ra))
        point = stat(allidx)
        ud, inv = np.unique(d, return_inverse=True)
        order = np.argsort(inv, kind="stable")
        cnt = np.bincount(inv, minlength=len(ud))
        off = np.r_[0, np.cumsum(cnt)[:-1]]
        rng = np.random.default_rng(CFG["seed"])
        reps = []
        for ch in _block_idx(len(ud), CFG["boot_B_rank"], CFG["boot_block"], rng):
            lens = cnt[ch]
            base = np.repeat(off[ch] - np.r_[0, np.cumsum(lens)[:-1]], lens)
            reps.append(stat(order[base + np.arange(lens.sum())]))
        lo, hi = np.nanpercentile(reps, [2.5, 97.5])
        res.append((point, float(lo), float(hi), int(ok.sum())))
    return res


def windows(days: pd.Series) -> Dict[str, np.ndarray]:
    d = pd.to_datetime(days)
    return {"whole": np.ones(len(d), bool), "disc": (d <= pd.Timestamp(CFG["discovery_end"])).to_numpy(),
            "conf": (d >= pd.Timestamp(CFG["confirmation_start"])).to_numpy()}


def rule_table(E: pd.DataFrame, engine: str) -> pd.DataFrame:
    rows = []
    W = windows(E["signal_day"])
    for r in RULES:
        net, take, hit, base = E[f"net:{r}"], E[f"take:{r}"].astype(bool), E[f"hit:{r}"], E["base"]
        contrib = net.where(take, 0.0)
        ok = base.notna() & contrib.notna()
        rec = {"engine": engine, "rule": r, "family": FAMILY.get(r.split("|")[0], "other"),
               "fallback": r.split("|")[1] if "|" in r else "", "trades": int(ok.sum()),
               "taken_pct": float(take[ok].mean()) if ok.any() else np.nan,
               "hit_pct": float(hit[ok & take].mean()) if hit[ok & take].notna().any() else np.nan,
               "profitable_pct": float((net[ok & take] > 0).mean()) if (ok & take).any() else np.nan,
               "mean_net_bp": float(net[ok & take].mean() * 1e4) if (ok & take).any() else np.nan,
               "base_net_bp": float(base[ok].mean() * 1e4) if ok.any() else np.nan}
        for wn, wm in W.items():
            m = ok & wm
            daily = (contrib - base)[m].groupby(E.loc[m, "signal_day"]).mean().sort_index()
            mean, lo, hi = boot_mean(daily.to_numpy())
            rec.update({f"{wn}_bp": mean * 1e4, f"{wn}_lo": lo * 1e4, f"{wn}_hi": hi * 1e4, f"{wn}_days": int(len(daily))})
        promising = (rec["disc_lo"] > 0) and (rec["conf_bp"] > 0)
        watch = rec["whole_lo"] > 0
        rec["verdict"] = ("PROMISING" if promising else "WATCH" if watch else "-") if engine == "D" else \
                         ("promising (reported)" if promising else "watch (reported)" if watch else "-")
        rec["shadow_candidate"] = bool(promising and engine == "D")
        rows.append(rec)
    return pd.DataFrame(rows)


def behaviour(E: pd.DataFrame, kind: str, outcome: str = "base", min_n: int = 20, top: Optional[int] = None) -> pd.DataFrame:
    """What happened after each state: profit, MFE / MAE, target reach, OPEN_6 vs CLOSE_5, and session 1 intraday.
    Transitions list regime CHANGES only (an unchanged regime is the daily-regime table)."""
    W = windows(E["signal_day"])
    rows = []
    for code, g in E.groupby(kind):
        if code < 0 or len(g) < min_n or (kind == "transition" and code // 9 == code % 9):
            continue
        b = g[outcome].astype(float)
        idx = g.index
        sd = b.std()
        rows.append({"state": label(kind, int(code)), "n": int(b.notna().sum()), "profitable_pct": float((b > 0).mean()),
                     "mean_bp": float(b.mean() * 1e4), "ci_bp": float(1.96 * sd / np.sqrt(max(b.notna().sum(), 1)) * 1e4),
                     "disc_bp": float(b[W["disc"][E.index.get_indexer(idx)]].mean() * 1e4),
                     "conf_bp": float(b[W["conf"][E.index.get_indexer(idx)]].mean() * 1e4),
                     "mfe_med_pct": _med(g["mfe5"]) * 100, "mae_med_pct": _med(g["mae5"]) * 100,
                     "hit2_pct": float((g["mfe5"] >= 0.02).mean() * 100), "hit5_pct": float((g["mfe5"] >= 0.05).mean() * 100),
                     "hit10_pct": float((g["mfe5"] >= 0.10).mean() * 100),
                     "open6_vs_close5_bp": float((g["OPEN_6"] - g["CLOSE_5"]).mean() * 1e4),
                     "n_bars": int(g["s1_mae"].notna().sum()), "s1_ret30_bp": _mean(g["s1_ret30"]) * 1e4,
                     "s1_mae_med_pct": _med(g["s1_mae"]) * 100, "s1_low_in_30_pct": _mean(g["s1_low_in_30"]) * 100,
                     "s1_low_minute_med": _med(g["s1_low_minute"])})
    R = pd.DataFrame(rows)
    if len(R):
        R = R.sort_values("n", ascending=False)
        if top:
            R = R.head(top)
    return R.reset_index(drop=True)


def _med(x) -> float:
    v = np.asarray(x, float)
    v = v[np.isfinite(v)]
    return float(np.median(v)) if len(v) else np.nan


def _mean(x) -> float:
    v = np.asarray(x, float)
    v = v[np.isfinite(v)]
    return float(v.mean()) if len(v) else np.nan


def separation(B: pd.DataFrame) -> float:
    """Rank agreement of the states' mean outcome between the discovery and confirmation windows."""
    if len(B) < 4:
        return np.nan
    x, y = B["disc_bp"].to_numpy(float), B["conf_bp"].to_numpy(float)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 4:
        return np.nan
    return float(pd.Series(x[ok]).rank().corr(pd.Series(y[ok]).rank()))


ACC_PAIRS = [("cross memory: mean 5-session net -> 5-session net", "cm_net5", "base"),
             ("own daily memory (the stock's own similar days): mean 5-session net -> 5-session net", "om_net5", "base"),
             ("cross memory: median MFE -> MFE", "cm_mfe_q50", "mfe5"),
             ("own daily memory: median MFE -> MFE", "om_mfe_q50", "mfe5"),
             ("cross memory: chance of +5% -> reached +5%", "cm_p5", "hit5"),
             ("cross memory: session-1 dip -> session-1 dip", "cm_s1_mae", "s1_mae"),
             ("own intraday memory (what this stock did the session AFTER days like T): entry-session dip -> entry-session dip", "oi_s1_mae", "s1_mae"),
             ("cross memory: first-30-min return -> first-30-min return", "cm_s1_ret30", "s1_ret30"),
             ("own intraday memory (the session AFTER days like T): first-30-min return -> first-30-min return", "oi_s1_ret30", "s1_ret30"),
             ("cross memory: low in first 30 min -> low in first 30 min", "cm_s1_low_in_30", "s1_low_in_30")]
ADD_PAIRS = [("5-session net: full minus daily-only", "cm_net5", "cmd_net5", "base"),
             ("5-session net: full minus daily + daily-bar pick day", "cm_net5", "cmp_net5", "base"),
             ("MFE: full minus daily-only", "cm_mfe_q50", "cmd_mfe_q50", "mfe5"),
             ("session-1 dip: full minus daily-only", "cm_s1_mae", "cmd_s1_mae", "s1_mae"),
             ("session-1 dip: full minus daily + daily-bar pick day", "cm_s1_mae", "cmp_s1_mae", "s1_mae"),
             ("first-30-min return: full minus daily-only", "cm_s1_ret30", "cmd_s1_ret30", "s1_ret30")]


def accuracy(E: pd.DataFrame, engine: str) -> pd.DataFrame:
    rows = []
    W = windows(E["signal_day"])
    days = pd.to_datetime(E["signal_day"]).to_numpy()
    col = lambda c: E[c].to_numpy(float) if c in E else np.full(len(E), np.nan)
    for name, p, y in ACC_PAIRS:
        for wn, wm in W.items():
            (r, lo, hi, n), = boot_spearman(days[wm], [(col(p)[wm], col(y)[wm])])
            rows.append({"engine": engine, "test": "accuracy", "what": name, "window": wn, "spearman": r, "lo": lo, "hi": hi, "picks": n})
    tb = E["has_bars_T"].to_numpy(bool) if "has_bars_T" in E else np.ones(len(E), bool)
    for name, a, b, y in ADD_PAIRS:
        for wn, wm in W.items():
            m = wm & tb
            (r, lo, hi, n), = boot_spearman(days[m], [(col(a)[m], col(y)[m], col(b)[m])])
            rows.append({"engine": engine, "test": "intraday adds", "what": name, "window": wn, "spearman": r, "lo": lo, "hi": hi, "picks": n})
    return pd.DataFrame(rows)


def calibration(E: pd.DataFrame, engine: str) -> pd.DataFrame:
    nominal = {"SQ30": 0.7, "SQ50": 0.5, "SQ70": 0.3, "RQ50": 0.5, "IQ50": 0.5, "OQ30": 0.7, "OQ50": 0.5, "OQ70": 0.3, "OQ50S": 0.5}
    W = windows(E["signal_day"])
    rows = []
    for t, nom in nominal.items():
        h = E[f"hit:{t}|C5"]
        rec = {"engine": engine, "target": t, "nominal_hit_pct": nom * 100, "picks_with_target": int(h.notna().sum())}
        for wn, wm in W.items():
            v = h[wm]
            rec[f"{wn}_hit_pct"] = float(v.mean() * 100) if v.notna().any() else np.nan
        rows.append(rec)
    return pd.DataFrame(rows)


def by_regime_targets(E: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for code, g in E.groupby("regime"):
        if code < 0 or len(g) < 20:
            continue
        rec = {"state": label("regime", int(code)), "n": len(g), "close5_bp": float(g["base"].mean() * 1e4)}
        for t in ("T2", "T5", "T10", "SQ50", "OQ50"):
            rec[f"{t}_hit_pct"] = float(g[f"hit:{t}|C5"].mean() * 100) if g[f"hit:{t}|C5"].notna().any() else np.nan
            rec[f"{t}_bp"] = float(g[f"net:{t}|C5"].mean() * 1e4)
        rows.append(rec)
    return pd.DataFrame(rows).sort_values("n", ascending=False).reset_index(drop=True) if rows else pd.DataFrame()


def stock_table(E: pd.DataFrame) -> pd.DataFrame:
    g = E.groupby("symbol", observed=True)
    S = pd.DataFrame({"picks": g.size(), "close5_bp": g["base"].mean() * 1e4, "own_target_pct": g["om_mfe_q50"].mean() * 100,
                      "own_target_hit_pct": g["hit:OQ50|C5"].mean() * 100, "own_target_bp": g["net:OQ50|C5"].mean() * 1e4,
                      "t5_hit_pct": g["hit:T5|C5"].mean() * 100, "mfe_med_pct": g["mfe5"].median() * 100,
                      "s1_mae_med_pct": g["s1_mae"].median() * 100})
    S["own_target_vs_close5_bp"] = S["own_target_bp"] - S["close5_bp"]
    return S.sort_values("picks", ascending=False).reset_index()


# ----------------------------------------------------------------------
# the run
# ----------------------------------------------------------------------
def pick_table(cands: pd.DataFrame, P: pd.DataFrame, bars: Dict[str, SymBars], calendar: np.ndarray,
               exits_fn: Optional[Callable[[str, pd.Timestamp], Optional[Dict[str, float]]]] = None) -> Tuple[pd.DataFrame, dict]:
    """One row per traded pick (engine, day, symbol): its state row in P, the entry session's prices and exits."""
    key = pd.DataFrame({"symbol": P["symbol"].astype(str).to_numpy(), "day": P["day"].to_numpy(), "row": np.arange(len(P))})
    C = cands[cands["traded"].astype(bool)].copy()
    C["symbol"] = C["symbol"].astype(str)
    C = C.merge(key, left_on=["symbol", "signal_day"], right_on=["symbol", "day"], how="inner")
    cal_pos = {pd.Timestamp(t): i for i, t in enumerate(pd.DatetimeIndex(calendar))}
    rows, counts = [], {"no_state_row": int(cands["traded"].astype(bool).sum() - len(C)), "no_next_session": 0,
                        "incomplete": 0, "plain_exit_fallback": 0}
    for _, p in C.iterrows():
        sb = bars.get(p["symbol"])
        T = pd.Timestamp(p["signal_day"])
        i = sb.idx.get(T) if sb is not None else None
        ci = cal_pos.get(T)
        if i is None or ci is None or ci + 1 >= len(calendar) or i + 1 >= len(sb.c) or sb.days[i + 1] != pd.Timestamp(calendar[ci + 1]):
            counts["no_next_session"] += 1
            continue
        e = i + 1
        if e + 4 >= len(sb.c):
            counts["incomplete"] += 1
            continue
        ex = exits_fn(p["symbol"], sb.days[e]) if exits_fn else None
        if ex is None:
            ex = plain_exits(sb, e)
            counts["plain_exit_fallback"] += int(exits_fn is not None)
        if not np.isfinite(ex.get("CLOSE_5", np.nan)):
            counts["incomplete"] += 1
            continue
        rec = {"engine": p["engine"], "signal_day": T, "symbol": p["symbol"], "rank": int(p["rank"]), "row": int(p["row"]),
               "entry": sb.o[e], "mfe5": sb.h[e:e + 5].max() / sb.o[e] - 1, "mae5": sb.l[e:e + 5].min() / sb.o[e] - 1}
        for s in range(5):
            rec[f"O{s + 1}"], rec[f"H{s + 1}"] = sb.o[e + s], sb.h[e + s]
        for h in HORIZONS:
            rec["px_" + h] = ex.get(h, np.nan)
        rows.append(rec)
    return pd.DataFrame(rows), counts


def run(cands: pd.DataFrame, daily: Dict[str, pd.DataFrame], intra_loader=None, exits_fn=None, log=None,
        allow_partial_bars: bool = False) -> dict:
    log = log or (lambda m: None)
    cands = cands.copy()
    cands["signal_day"] = _naive_days(cands["signal_day"]).to_numpy()
    log(f"states for {len(daily):,} stocks")
    P = build_panel(daily, intra_loader, CFG["state_start"], log)
    calendar = np.sort(P["day"].unique())
    P = add_states(P, calendar)
    first_bar = P.loc[P["has_bars"], "day"].min() if P["has_bars"].any() else None
    era = (P["day"] >= first_bar).to_numpy() if first_bar is not None else np.zeros(len(P), bool)
    bar_cov = float(P.loc[era, "has_bars"].mean()) if era.any() else 0.0
    if bar_cov < CFG["min_bar_coverage"] and not allow_partial_bars:
        raise PreconditionError(f"only {bar_cov:.0%} of stock-days since {first_bar.date() if first_bar is not None else '-'} have reconciled "
                                f"3-minute bars (needs {CFG['min_bar_coverage']:.0%}): finish the full-history download "
                                f"(intraday_cache.py update --full-history), or run with --allow-partial-bars to accept thin intraday states")
    first_pick = pd.Timestamp(cands["signal_day"].min())
    per_day = P[P["day"] >= first_pick].groupby("day").size()
    bars_day = P[era].groupby("day")["has_bars"].sum() if era.any() else pd.Series(dtype=float)
    stab = stability(P)
    bars = {s: SymBars(df) for s, df in daily.items()}
    T, counts = pick_table(cands, P, bars, calendar, exits_fn)
    if T.empty:
        raise PreconditionError("no traded pick has a state row and a complete outcome - check the candidates and the daily cache")
    key = pd.DataFrame({"symbol": P["symbol"].astype(str).to_numpy(), "day": P["day"].to_numpy(), "row": np.arange(len(P))})
    allc = cands.assign(symbol=cands["symbol"].astype(str)).merge(key, left_on=["symbol", "signal_day"], right_on=["symbol", "day"], how="inner")
    pool_rows = np.unique(allc["row"].to_numpy())
    pool_rows = pool_rows[np.isfinite(P["CLOSE_5"].to_numpy(float)[pool_rows])]
    q_rows = np.unique(T["row"].to_numpy())
    log(f"memories for {len(q_rows):,} pick-moments (pool {len(pool_rows):,} earlier pick-moments)")
    Mem, info = memories(P, pool_rows, q_rows, log)
    state_cols = ["regime", "iregime", "shape", "transition", "seq3", "atr14", "has_bars"] + S1_COLS
    T = T.merge(P[state_cols].iloc[T["row"].to_numpy()].reset_index(drop=True).rename(columns={"has_bars": "has_bars_T"}),
                left_index=True, right_index=True)
    T = T.merge(Mem, on="row", how="left")
    T["hit5"] = (T["mfe5"] >= 0.05).astype(float)
    E = evaluate(T)
    E["OPEN_6"] = E["px_OPEN_6"] / E["entry"] - 1 - COST
    E["CLOSE_5"] = E["base"]
    log(f"rules, behaviour and accuracy for {len(E):,} traded picks")
    out = {"picks": E, "counts": counts, "stability": stab, "P_rows": len(P), "pool": len(pool_rows), "neighbours": info}
    out["rules"] = pd.concat([rule_table(E[E["engine"] == eng].reset_index(drop=True), eng) for eng in ("D", "ENS")
                              if (E["engine"] == eng).any()], ignore_index=True)
    ED = E[E["engine"] == "D"].reset_index(drop=True)
    out["behaviour"] = {k: behaviour(ED, k, top=(15 if k in ("transition", "seq3") else None)) for k in ("regime", "iregime", "shape", "transition", "seq3")}
    out["separation"] = {k: separation(v) for k, v in out["behaviour"].items()}
    mom = P.iloc[pool_rows].rename(columns={"day": "signal_day"}).assign(base=lambda x: x["CLOSE_5"])
    out["behaviour_moments"] = {k: behaviour(mom.reset_index(drop=True), k) for k in ("regime", "iregime")}
    out["accuracy"] = pd.concat([accuracy(E[E["engine"] == eng].reset_index(drop=True), eng) for eng in ("D", "ENS")
                                 if (E["engine"] == eng).any()], ignore_index=True)
    out["calibration"] = pd.concat([calibration(E[E["engine"] == eng].reset_index(drop=True), eng) for eng in ("D", "ENS")
                                    if (E["engine"] == eng).any()], ignore_index=True)
    out["by_regime"] = by_regime_targets(ED)
    out["stocks"] = stock_table(ED)
    out["coverage"] = {"stock_days": int(len(P)), "stock_days_with_bars": int(P["has_bars"].sum()),
                       "traded_picks": int(len(E)), "D_picks": int(len(ED)), "picks_with_bars_T": int(E["has_bars_T"].sum()),
                       "picks_with_bars_S1": int(E["s1_mae"].notna().sum()), "pool": int(len(pool_rows)),
                       "cross_memory_ok": int(E["cm_n"].ge(CFG["min_cross"]).sum()), "own_memory_median_n": float(E["om_n"].median()),
                       "own_intraday_median_n": float(E["oi_n"].median()) if "oi_n" in E else 0.0,
                       "universe_stocks": int(P["symbol"].nunique()), "stocks_per_day_median": float(per_day.median()) if len(per_day) else 0.0,
                       "stocks_per_day_min": int(per_day.min()) if len(per_day) else 0,
                       "bar_stocks_per_day_median": float(bars_day.median()) if len(bars_day) else 0.0,
                       "bar_coverage": bar_cov, "first_bar_day": str(first_bar.date()) if first_bar is not None else None, **counts}
    return out


# ----------------------------------------------------------------------
# report
# ----------------------------------------------------------------------
def _f(m, lo, hi) -> str:
    return "n/a" if not np.isfinite(m) else f"{m:+.1f} [{lo:+.1f}, {hi:+.1f}]" if np.isfinite(lo) else f"{m:+.1f}"


def _p(x, d=1) -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"{x:.{d}f}"


def write_report(out_dir: Path, res: dict, sha: str, cand_sha: str) -> None:
    cv = res["coverage"]
    L = ["# Soul + intraday Soul", "",
         f"{CODE_VERSION} | declaration {sha} | candidates {cand_sha} | exploration mode", "",
         "**How to read this.** Every pick is bought at the next open; the baseline sells at the 5th close (honest circuit "
         "exits, 35 bp). bp = basis points per trade (100 bp = 1%). Intervals are 95%.", "",
         "**Sections 1-7 are EXPLORATORY**: descriptions, correlations, hit rates and rankings, with no false-discovery control. "
         "Nothing in them is validated. Section 8 lists PROMISING rules (discovery lower bound above zero AND confirmation mean "
         "above zero, D only): candidates for a forward shadow lane - still not validated; only the forward test decides.", "",
         "**Timing.** Every state is day T's completed state (its close and its 3-minute bars). Every memory is chosen on that "
         "state and reports what FOLLOWED the similar moments - the next session(s) - never day T itself. A similar moment counts "
         "only if it lies 6+ sessions before the pick; its 7th / 10th close counts only if that close was already known on day T.", "",
         "## Coverage", "",
         f"- stock-days with a state: {cv['stock_days']:,} (with 3-minute bars: {cv['stock_days_with_bars']:,})",
         f"- traded picks: {cv['traded_picks']:,} (D: {cv['D_picks']:,}); pick day with 3-minute bars: {cv['picks_with_bars_T']:,}; "
         f"entry session with bars: {cv['picks_with_bars_S1']:,}",
         f"- cross-memory pool: {cv['pool']:,} earlier pick-moments; picks with a full cross memory: {cv['cross_memory_ok']:,}; "
         f"median own-memory size {cv['own_memory_median_n']:.0f} (daily), {cv['own_intraday_median_n']:.0f} (intraday)",
         f"- percentile universe: the {cv['universe_stocks']:,} stocks in the frozen candidate set (every stock frozen D or the ensemble "
         f"ever had in its top 10); per signal day {cv['stocks_per_day_median']:.0f} stocks (minimum {cv['stocks_per_day_min']}). The 3-minute "
         f"dimensions rank among stocks with reconciled bars that day: median {cv['bar_stocks_per_day_median']:.0f} since {cv['first_bar_day']} "
         f"({cv['bar_coverage'] * 100:.1f}% of stock-days). Note: the universe is defined by picks made up to 2026, so it is not point-in-time; "
         f"it only sets the scale of the percentiles, the same for every pick.",
         f"- dropped: no state row {cv['no_state_row']}, no next session {cv['no_next_session']}, incomplete {cv['incomplete']}, "
         f"plain-exit fallback {cv['plain_exit_fallback']}", ""]
    st = res["stability"]
    L += ["## 1. State identification (EXPLORATORY)", "",
          f"Daily regime stability (same regime the next session): {_p(st.iloc[0]['same_next_day'] * 100)}% of {int(st.iloc[0]['days']):,} stock-days.", "",
          "| daily regime | stock-days | same next session |", "|---|---|---|"]
    for _, r in st.iloc[1:].iterrows():
        L.append(f"| {r['state']} | {int(r['days']):,} | {r['same_next_day'] * 100:.1f}% |")
    L += ["", "Separation - do the states' average outcomes keep their order from the discovery to the confirmation window "
          "(rank agreement, +1 = same order, 0 = none):", ""]
    for k, v in res["separation"].items():
        L.append(f"- {k}: {_p(v, 2)}")
    names = {"regime": "daily regime", "iregime": "intraday regime (gap x close)", "shape": "intraday shape (3-minute bars)",
             "transition": "regime changes (5 sessions ago > today, the 15 most common)", "seq3": "3-day close sequence (top 15)"}
    L += ["", "## 2. Behaviour by state - frozen D's traded picks (EXPLORATORY)", "",
          "profit = 5th-close net; MFE / MAE = best / worst point over 5 sessions; hit = reached +2/+5/+10%; "
          "s1 = the entry session's intraday path (3-minute bars)."]
    for k, B in res["behaviour"].items():
        if B.empty:
            continue
        L += ["", f"### {names[k]}", "",
              "| state | n | profitable | mean bp [~95%] | disc / conf bp | MFE med | MAE med | hit +2/+5/+10 | OPEN_6 - CLOSE_5 | s1 first 30 min | s1 dip med | s1 low in 30 min | s1 low minute |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for _, r in B.iterrows():
            L.append(f"| {r['state']} | {r['n']} | {r['profitable_pct'] * 100:.0f}% | {r['mean_bp']:+.1f} [±{r['ci_bp']:.1f}] | "
                     f"{_p(r['disc_bp'])} / {_p(r['conf_bp'])} | {r['mfe_med_pct']:+.2f}% | {r['mae_med_pct']:+.2f}% | "
                     f"{r['hit2_pct']:.0f} / {r['hit5_pct']:.0f} / {r['hit10_pct']:.0f}% | {r['open6_vs_close5_bp']:+.1f} | "
                     f"{_p(r['s1_ret30_bp'])} bp | {_p(r['s1_mae_med_pct'], 2)}% | {_p(r['s1_low_in_30_pct'], 0)}% | {_p(r['s1_low_minute_med'], 0)} |")
    A = res["accuracy"]
    L += ["", "## 3. Does the Soul know anything? Memory accuracy (EXPLORATORY)", "",
          "Spearman correlation between what similar earlier moments did and what this pick then did (0 = no information).", "",
          "| engine | memory -> outcome | whole | discovery | confirmation | picks |", "|---|---|---|---|---|---|"]
    for (eng, test, what), g in A.groupby(["engine", "test", "what"], sort=False):
        w = {r["window"]: r for _, r in g.iterrows()}
        cell = lambda x: _f(x["spearman"], x["lo"], x["hi"]) if np.isfinite(x["spearman"]) else "n/a"
        if test == "accuracy":
            L.append(f"| {eng} | {what} | {cell(w['whole'])} | {cell(w['disc'])} | {cell(w['conf'])} | {int(w['whole']['picks']):,} |")
    L += ["", "**Does the intraday state help?** Difference in Spearman, full memory minus a memory without the 3-minute "
          "dimensions, on picks whose day T has bars (above 0 = the intraday state adds information).", "",
          "| engine | comparison | whole | discovery | confirmation | picks |", "|---|---|---|---|---|---|"]
    for (eng, test, what), g in A.groupby(["engine", "test", "what"], sort=False):
        if test != "intraday adds":
            continue
        w = {r["window"]: r for _, r in g.iterrows()}
        cell = lambda x: _f(x["spearman"], x["lo"], x["hi"]) if np.isfinite(x["spearman"]) else "n/a"
        L.append(f"| {eng} | {what} | {cell(w['whole'])} | {cell(w['disc'])} | {cell(w['conf'])} | {int(w['whole']['picks']):,} |")
    R = res["rules"]
    L += ["", "## 4. Targets - win rates and profit, D's traded top 3 (EXPLORATORY)", "",
          "win = target reached within 5 sessions; profitable = net above 0; vs 5th close = paired difference per signal day "
          "(bp a trade). C5 / O6 = the exit when the target is not reached: the 5th close / the 6th open.", ""]
    fam_names = {"normal": "Normal targets", "state": "State-specific targets", "stock": "Stock-specific targets"}
    for fam in ("normal", "state", "stock"):
        L += [f"### {fam_names[fam]}", "", "| rule | win | profitable | mean net bp | vs 5th close: whole | discovery | confirmation | verdict |",
              "|---|---|---|---|---|---|---|---|"]
        for _, r in R[(R["engine"] == "D") & (R["family"] == fam)].iterrows():
            L.append(f"| {r['rule']} | {_p(r['hit_pct'] * 100, 0)}% | {r['profitable_pct'] * 100:.0f}% | {r['mean_net_bp']:+.1f} | "
                     f"{_f(r['whole_bp'], r['whole_lo'], r['whole_hi'])} | {_f(r['disc_bp'], r['disc_lo'], r['disc_hi'])} | "
                     f"{_f(r['conf_bp'], r['conf_lo'], r['conf_hi'])} | {r['verdict']} |")
        L.append("")
    b0 = R[(R["engine"] == "D") & (R["rule"] == "T2|C5")]
    if len(b0):
        L.append(f"Baseline (5th close) on these picks: {b0.iloc[0]['base_net_bp']:+.1f} bp a trade.")
    C = res["calibration"]
    L += ["", "### Are the state and stock targets calibrated?", "",
          "A 30th-percentile target should be reached about 70% of the time, a median one about 50%, a 70th-percentile one about 30%.", "",
          "| engine | target | expected | whole | discovery | confirmation | picks with a target |", "|---|---|---|---|---|---|---|"]
    for _, r in C.iterrows():
        L.append(f"| {r['engine']} | {r['target']} | {r['nominal_hit_pct']:.0f}% | {_p(r['whole_hit_pct'], 0)}% | {_p(r['disc_hit_pct'], 0)}% | "
                 f"{_p(r['conf_hit_pct'], 0)}% | {r['picks_with_target']:,} |")
    BR = res["by_regime"]
    if len(BR):
        L += ["", "### Targets by daily regime (D)", "",
              "| state | n | 5th close bp | +2%: win / bp | +5%: win / bp | +10%: win / bp | state median: win / bp | stock median: win / bp |",
              "|---|---|---|---|---|---|---|---|"]
        for _, r in BR.iterrows():
            cell = lambda t: f"{_p(r[t + '_hit_pct'], 0)}% / {r[t + '_bp']:+.1f}"
            L.append(f"| {r['state']} | {r['n']} | {r['close5_bp']:+.1f} | {cell('T2')} | {cell('T5')} | {cell('T10')} | {cell('SQ50')} | {cell('OQ50')} |")
    L += ["", "## 5. Other rules, D (EXPLORATORY)", "", "| rule | taken | mean net bp | vs 5th close: whole | discovery | confirmation | verdict |",
          "|---|---|---|---|---|---|---|"]
    for _, r in R[(R["engine"] == "D") & (R["family"] == "other")].iterrows():
        L.append(f"| {r['rule']} | {r['taken_pct'] * 100:.0f}% | {r['mean_net_bp']:+.1f} | {_f(r['whole_bp'], r['whole_lo'], r['whole_hi'])} | "
                 f"{_f(r['disc_bp'], r['disc_lo'], r['disc_hi'])} | {_f(r['conf_bp'], r['conf_lo'], r['conf_hi'])} | {r['verdict']} |")
    RE = R[R["engine"] == "ENS"]
    if len(RE):
        L += ["", "## 6. The ensemble (reported)", "", f"Rules promising for the ensemble too: "
              f"{', '.join(RE.loc[RE['verdict'].str.startswith('promising'), 'rule']) or 'none'}.", ""]
    S = res["stocks"]
    L += ["## 7. Stocks most often picked, D (EXPLORATORY)", "", "| stock | picks | 5th close bp | own target | own target win | own target vs 5th close | +5% win | MFE med | s1 dip med |",
          "|---|---|---|---|---|---|---|---|---|"]
    for _, r in S.head(20).iterrows():
        L.append(f"| {r['symbol']} | {int(r['picks'])} | {r['close5_bp']:+.1f} | {_p(r['own_target_pct'], 2)}% | {_p(r['own_target_hit_pct'], 0)}% | "
                 f"{_p(r['own_target_vs_close5_bp'])} | {_p(r['t5_hit_pct'], 0)}% | {_p(r['mfe_med_pct'], 2)}% | {_p(r['s1_mae_med_pct'], 2)}% |")
    sc = R[R["shadow_candidate"]]
    L += ["", "## 8. Shadow-lane candidates (PROMISING - not validated; the forward test decides)", "",
          ("- " + "\n- ".join(f"{r['rule']}: {_f(r['whole_bp'], r['whole_lo'], r['whole_hi'])} bp vs the 5th close "
                              f"(confirmation {r['conf_bp']:+.1f})" for _, r in sc.iterrows())) if len(sc) else "None.", "",
          "Exploration only: nothing here changes the engines or the paper test.", ""]
    (out_dir / "soul_intraday_report.md").write_text("\n".join(L), encoding="utf-8")


def save(res: dict, out_dir: Path, sha: str, cand_sha: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=False)
    res["rules"].to_csv(out_dir / "rules.csv", index=False)
    res["accuracy"].to_csv(out_dir / "accuracy.csv", index=False)
    res["calibration"].to_csv(out_dir / "calibration.csv", index=False)
    res["stocks"].to_csv(out_dir / "stocks.csv", index=False)
    res["stability"].to_csv(out_dir / "stability.csv", index=False)
    if len(res["by_regime"]):
        res["by_regime"].to_csv(out_dir / "targets_by_regime.csv", index=False)
    for k, B in res["behaviour"].items():
        B.to_csv(out_dir / f"behaviour_{k}.csv", index=False)
    for k, B in res["behaviour_moments"].items():
        B.to_csv(out_dir / f"behaviour_all_moments_{k}.csv", index=False)
    E = res["picks"].copy()
    for k in ("regime", "iregime", "shape", "transition", "seq3"):
        E[k + "_label"] = [label(k, int(c)) for c in E[k]]
    E.to_parquet(out_dir / "picks.parquet", index=False)
    write_report(out_dir, res, sha, cand_sha)
    (out_dir / "summary.json").write_text(json.dumps({"tool": CODE_VERSION, "declaration": sha, "candidates": cand_sha,
                                                      "coverage": res["coverage"],
                                                      "shadow_candidates": res["rules"].loc[res["rules"]["shadow_candidate"], "rule"].tolist()},
                                                     indent=2, default=str), encoding="utf-8")


def honest_exits_factory(EX, bars) -> Callable[[str, pd.Timestamp], Optional[Dict[str, float]]]:
    """Honest exits with the shipped execution model: CLOSE_k through EX.plan_exit, OPEN_6 at the first open that is not
    locked at the lower circuit (the same calls intraday_study v1.4 makes)."""
    maps = {}

    def fn(sym: str, entry_day) -> Optional[Dict[str, float]]:
        b = bars.get(sym)
        if b is None:
            return None
        mp = maps.get(sym)
        if mp is None:
            mp = maps[sym] = {pd.Timestamp(t).normalize(): i for i, t in enumerate(b.ts)}
        e = mp.get(pd.Timestamp(entry_day).normalize())
        if e is None or e < 1:
            return None
        n, out = len(b.c), {}
        for k in (3, 5, 7, 10):
            if e + k - 1 >= n:
                out[f"CLOSE_{k}"] = np.nan
                continue
            x, kind, raw, fl = EX.plan_exit(b, e, k, None)
            out[f"CLOSE_{k}"] = np.nan if fl.get("data_end") else float(raw)
        j, px = e + 5, np.nan
        if j < n:
            stop = min(j + 20, n)
            for q in range(j, stop):
                if not EX.lower_locked(b, q, "open"):
                    px = float(b.o[q])
                    break
            else:
                px = float(b.c[stop - 1])
        out["OPEN_6"] = px
        return out

    return fn


def frozen_candidates(root: Path) -> Tuple[pd.DataFrame, str]:
    d = root / "research2" / "intraday"
    fp, meta = d / "frozen_candidates.parquet", d / "frozen_candidates.json"
    if not fp.exists() or not meta.exists():
        raise PreconditionError(f"no frozen candidate set in {d} - run intraday_study.py first")
    m = json.loads(meta.read_text(encoding="utf-8"))
    sha = hashlib.sha256(fp.read_bytes()).hexdigest()[:16]
    if sha != m.get("sha"):
        raise PreconditionError("frozen_candidates.parquet changed since it was built - restore it (intraday_study.py --rebuild-candidates needs a reason)")
    C = pd.read_parquet(fp)
    C["signal_day"] = _naive_days(C["signal_day"]).to_numpy()
    return C, sha


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Soul + intraday Soul (exploration)")
    ap.add_argument("--root", required=True)
    ap.add_argument("--allow-partial-bars", action="store_true",
                    help="run even when under half of the stock-days since the first 3-minute day have bars (thin intraday states)")
    a = ap.parse_args(argv)
    root = Path(a.root)
    sha = hashlib.sha256(DECL_RAW).hexdigest()[:16]
    cands, cand_sha = frozen_candidates(root)
    import stage_e_execution as EX
    import intraday_cache as IC
    from data_quality import _paths
    syms = sorted(cands["symbol"].astype(str).unique())
    daily = {}
    for s in syms:
        fp, _ = _paths(root, s)
        if Path(fp).exists():
            daily[s] = pd.read_parquet(fp, columns=["timestamp", "open", "high", "low", "close", "volume"])
    if not daily:
        raise PreconditionError("no daily files for the candidate stocks - check CACHE_DAILY_ROOT")
    _log(f"{CODE_VERSION}: {len(daily):,} stocks with daily data; loading the execution model")
    exbars = EX.load_bars(root, sorted(daily))
    store = IC.store(root)
    tol_p, tol_v = IC.DECL["reconcile_price_tol"], IC.DECL["reconcile_volume_tol"]
    seen = {"files": 0, "days": 0, "ok_days": 0}

    def loader(sym: str) -> Optional[pd.DataFrame]:
        f = store / f"{sym}_{IC.BAR_MIN}m.parquet"
        if not f.exists():
            return None
        X = pd.read_parquet(f)
        J = IC.reconcile_symbol(X, daily[sym], tol_p, tol_v)
        if not len(J):
            return None
        ok = set(pd.to_datetime(J.loc[J["ok"], "day"]).dt.normalize())
        seen["files"] += 1
        seen["days"] += len(J)
        seen["ok_days"] += len(ok)
        return X[X["timestamp"].dt.normalize().isin(list(ok))]

    res = run(cands, daily, loader, honest_exits_factory(EX, exbars), _log, a.allow_partial_bars)
    res["coverage"].update({"intraday_files": seen["files"], "intraday_days": seen["days"], "intraday_days_reconciled": seen["ok_days"]})
    day = dt.date.today().strftime("%Y%m%d")
    base = root / "research2" / "soul_intraday"
    k = 1
    while (base / f"SI_{day}_{k:03d}").exists():
        k += 1
    out = base / f"SI_{day}_{k:03d}"
    save(res, out, sha, cand_sha)
    R = res["rules"]
    RD = R[R["engine"] == "D"]
    _log(f"{CODE_VERSION}: {res['coverage']['D_picks']:,} D picks; {int((RD['verdict'] == 'PROMISING').sum())} PROMISING, "
         f"{int((RD['verdict'] == 'WATCH').sum())} WATCH of {len(RD)} rules")
    print(f"  report: {out / 'soul_intraday_report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
