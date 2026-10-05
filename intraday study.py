#!/usr/bin/env python3
"""
intraday_study.py - how the frozen engines' trades behave inside each session.

    python intraday_study.py --root %CACHE_DAILY_ROOT%

Rules: INTRADAY_DECLARATION.json (fixed before any intraday data was examined). Second
pipeline: reads the frozen walk-forward picks, the daily cache and <root>\\intraday_3m\\;
writes only <root>\\research2\\intraday\\IS_YYYYMMDD_NNN\\. Descriptive: it changes nothing.

Every pick is bought on T+1 and judged against the BASELINE: buy at the 09:15 open,
sell at the 5th close (honest circuit exits), 35 bp. Each ENTRY rule keeps the 5th-close
exit; each EXIT rule keeps the open entry. A limit / breakout entry that does not fill
holds cash that trade (its contribution is 0). Per signal day the traded picks' paired
differences are averaged; intervals are 95% block bootstraps over signal days.

COVERAGE: core menus, the session path and the descriptors for D and the ensemble, each
for the traded top 3 and for ranks 4-10. THE CATALOGUE (listed in full below, before the
first run) runs the declared protocol on each engine's traded top 3: discovery (to
2024-12-31, Benjamini-Hochberg q = 0.10), then confirmation (2025 on, used once: same sign,
95% lower bound above zero). Only D's confirmed rules may become forward lanes. VWAP_DAY
and the ORACLE rows are benchmarks: they never enter the protocol. Entry rules keep the
original exit schedule (same calendar exit); see the declaration's entry_semantics.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import research_common as RC       # first: from a subfolder, this folder's copy must win
import stage_b_screen as SB        # noqa: E402
import stage_d_gate as SD          # noqa: E402
import stage_d_forensics as SF     # noqa: E402
import stage_e_execution as EX     # noqa: E402
import stage_e_paths as SP         # noqa: E402
import intraday_cache as IC        # noqa: E402
import intraday_features as IF     # noqa: E402

CODE_VERSION = "intraday_study v1.3"   # v1.3: only reconciled entry sessions; intraday exits only on reconciled sessions
#   # v1.2: 20-session volume from the daily cache (windowed intraday fetching)
#   # v1.1: D and ENS x top 3 / ranks 4-10, VWAP_DAY benchmark-only, entry gap, frozen candidates, NIFTY
DECL_RAW = (HERE / "INTRADAY_DECLARATION.json").read_bytes()
DECL = json.loads(DECL_RAW.decode("utf-8"))
CFG = DECL["config"]
COST = CFG["cost_bps"] / 1e4

ENTRY_CORE = ["OPEN", "VWAP_15", "VWAP_30", "VWAP_60", "VWAP_DAY", "CLOSE_T1", "LIMIT_PREV_VWAP", "LIMIT_PREV_VPOC", "ORB_HIGH_15"]
EXIT_CORE = ["CLOSE_5", "OPEN_5", "OPEN_6", "VWAP_15_6", "VWAP_DAY_5", "CLOSE_3", "CLOSE_7", "CLOSE_10"]
ORACLES = ["ORACLE_LOW", "ORACLE_HIGH"]
BENCHMARK_ONLY = {"OPEN", "ORACLE_LOW", "VWAP_DAY", "CLOSE_5", "ORACLE_HIGH"}     # never in the protocol
ENGINES, GROUPS = ("D", "ENS"), ("top3", "ranks4_10")
# ---- THE CATALOGUE, IN FULL (fixed before the first run; never extended after results) ----
CATALOGUE_ENTRY = ([f"VWAP_{k}" for k in (6, 9, 45, 90, 120)] + [f"TIME_{k}" for k in (3, 6, 9, 15, 30, 60, 120, 240)]
                   + [f"PULLBACK_{x}" for x in ("0.25", "0.5", "1", "1.5", "2", "3")]
                   + ["LIMIT_PREV_CLOSE", "ORB_HIGH_6", "ORB_HIGH_30", "GAPUP2_VWAP30_ELSE_OPEN", "GAPDN2_OPEN_ELSE_VWAP30"])
CATALOGUE_EXIT = [f"TIME5_{k}" for k in (15, 30, 60, 120, 240)] + ["VWAP_30_6", "VWAP_DAY_6", "CLOSE_4", "CLOSE_6", "OPEN_7"]


class PreconditionError(SystemExit):
    pass


def minutes(df: pd.DataFrame) -> np.ndarray:
    t = df["timestamp"]
    return ((t.dt.hour * 60 + t.dt.minute) - (9 * 60 + 15)).to_numpy(int)


# ----------------------------------------------------------------------
# entry and exit prices
# ----------------------------------------------------------------------
def limit_fill(B: pd.DataFrame, level: float) -> Tuple[float, bool]:
    """A buy limit resting from the open: the open if it is already at/below the level, else the level if traded."""
    if not (level > 0) or B.empty:
        return float("nan"), False
    if B["open"].iloc[0] <= level:
        return float(B["open"].iloc[0]), True
    return (float(level), True) if float(B["low"].min()) <= level else (float("nan"), False)


def orb_fill(B: pd.DataFrame, k: int) -> Tuple[float, bool]:
    m = minutes(B)
    first, rest = B[m < k], B[m >= k]
    if first.empty or rest.empty:
        return float("nan"), False
    top = float(first["high"].max())
    for o, h in zip(rest["open"].to_numpy(float), rest["high"].to_numpy(float)):
        if o > top:
            return o, True
        if h > top:
            return top, True
    return float("nan"), False


def entry_price(rule: str, B: pd.DataFrame, P: pd.DataFrame, prev_close: float) -> Tuple[float, bool]:
    """B: the T+1 session's 3-minute bars; P: session T's bars; prev_close: T's daily close."""
    if B.empty:
        return float("nan"), False
    m = minutes(B)
    o = float(B["open"].iloc[0])
    gap = o / prev_close - 1 if prev_close > 0 else 0.0
    if rule == "OPEN":
        return o, True
    if rule == "VWAP_DAY":
        return IF.vwap(B), True
    if rule == "CLOSE_T1":
        return float(B["close"].iloc[-1]), True
    if rule == "ORACLE_LOW":
        return float(B["low"].min()), True
    if rule.startswith("VWAP_"):
        k = int(rule.split("_")[1])
        return IF.vwap(B[m < k]), bool((m < k).any())
    if rule.startswith("TIME_"):
        k = int(rule.split("_")[1])
        part = B[m < k]
        return (float(part["close"].iloc[-1]), True) if len(part) else (float("nan"), False)
    if rule.startswith("PULLBACK_"):
        return limit_fill(B, o * (1 - float(rule.split("_")[1]) / 100))
    if rule == "LIMIT_PREV_VWAP":
        return limit_fill(B, IF.vwap(P))
    if rule == "LIMIT_PREV_VPOC":
        return limit_fill(B, IF.vpoc(P))
    if rule == "LIMIT_PREV_CLOSE":
        return limit_fill(B, prev_close)
    if rule.startswith("ORB_HIGH_"):
        return orb_fill(B, int(rule.split("_")[2]))
    if rule == "GAPUP2_VWAP30_ELSE_OPEN":
        return entry_price("VWAP_30", B, P, prev_close) if gap >= 0.02 else (o, True)
    if rule == "GAPDN2_OPEN_ELSE_VWAP30":
        return (o, True) if gap <= -0.02 else entry_price("VWAP_30", B, P, prev_close)
    raise ValueError(rule)


def session_frozen(S: pd.DataFrame) -> bool:
    return bool(len(S)) and bool(((S["open"] == S["high"]) & (S["high"] == S["low"]) & (S["low"] == S["close"])).all())


def next_unlocked_open(b: EX.Bars, j: int, search: int = 20) -> Tuple[float, int]:
    for k in range(j, min(j + search, len(b.c))):
        if not EX.lower_locked(b, k, "open"):
            return float(b.o[k]), k
    k = min(j + search, len(b.c)) - 1
    return float(b.c[k]), k


def exit_price(rule: str, b: EX.Bars, e: int, sessions: Dict[int, pd.DataFrame]) -> float:
    """b, e: daily bars and the entry session's index; sessions: 3-minute bars by session number (1 = entry)."""
    n = len(b.c)
    def daily_close(k):
        x, kind, raw, fl = EX.plan_exit(b, e, k, None)
        return float("nan") if fl["data_end"] else raw
    def intraday(s, fn):
        j = e + s - 1
        S = sessions.get(s, pd.DataFrame())
        if j >= n:
            return float("nan")
        if S.empty:
            return float("nan")
        if session_frozen(S) and EX.lower_locked(b, j, "close"):
            return next_unlocked_open(b, j + 1)[0]           # cannot sell on a frozen lower circuit
        return fn(S)
    if rule.startswith("CLOSE_"):
        return daily_close(int(rule.split("_")[1]))
    if rule.startswith("OPEN_"):
        j = e + int(rule.split("_")[1]) - 1
        return next_unlocked_open(b, j)[0] if j < n else float("nan")
    if rule == "ORACLE_HIGH":
        return float(b.h[e:e + 5].max()) if e + 5 <= n else float("nan")
    if rule in ("VWAP_15_6", "VWAP_30_6"):
        k = int(rule.split("_")[1])
        return intraday(6, lambda S: IF.vwap(S[minutes(S) < k]))
    if rule.startswith("VWAP_DAY_"):
        return intraday(int(rule.split("_")[2]), IF.vwap)
    if rule.startswith("TIME5_"):
        k = int(rule.split("_")[1])
        return intraday(5, lambda S: float(S[minutes(S) < k]["close"].iloc[-1]))
    raise ValueError(rule)


# ----------------------------------------------------------------------
# evaluating every pick
# ----------------------------------------------------------------------
def pick_outcomes(picks: pd.DataFrame, daily: Dict[str, EX.Bars], intra: Dict[str, pd.DataFrame], cal: np.ndarray,
                  entries: List[str], exits: List[str], ok_days: Optional[Dict[str, set]] = None,
                  counts: Optional[dict] = None) -> pd.DataFrame:
    pos = {d: i for i, d in enumerate(cal)}
    rows = []
    for _, p in picks.iterrows():
        T = np.datetime64(pd.Timestamp(p["signal_day"]), "ns")
        b, X = daily.get(p["symbol"]), intra.get(p["symbol"])
        i = pos.get(T)
        if b is None or X is None or i is None or i + 1 >= len(cal):
            continue
        e = b.index.get(cal[i + 1])
        if e is None or e < 1:
            continue
        days = X["timestamp"].dt.normalize()
        okd = ok_days.get(p["symbol"], set()) if ok_days is not None else None
        if okd is not None and pd.Timestamp(b.ts[e]).normalize() not in okd:
            if counts is not None:
                counts["entry_not_reconciled"] = counts.get("entry_not_reconciled", 0) + 1
            continue
        sess = {s: X[days == pd.Timestamp(b.ts[e + s - 1])] for s in range(1, 11) if e + s - 1 < len(b.c)}
        if okd is not None:
            for s_ in list(sess):
                if s_ > 1 and pd.Timestamp(b.ts[e + s_ - 1]).normalize() not in okd:
                    sess[s_] = sess[s_].iloc[0:0]                     # this session's intraday exits are left out
                    if counts is not None:
                        counts["exit_sessions_not_reconciled"] = counts.get("exit_sessions_not_reconciled", 0) + 1
        P = X[days == pd.Timestamp(b.ts[e - 1])]
        if sess.get(1, pd.DataFrame()).empty:
            continue
        rec = {"signal_day": p["signal_day"], "symbol": p["symbol"], "engine": p["engine"], "rank": p["rank"],
               "traded": bool(p["traded"])}
        base_exit = exit_price("CLOSE_5", b, e, sess)
        o = float(sess[1]["open"].iloc[0])
        rec["base"] = base_exit / o - 1 - COST if base_exit > 0 else np.nan
        for r in entries:
            px, filled = entry_price(r, sess[1], P, float(b.c[e - 1]))
            net = base_exit / px - 1 - COST if (filled and px > 0 and base_exit > 0) else np.nan
            rec[f"E:{r}"] = net
            rec[f"Efill:{r}"] = filled
        for r in exits:
            px = exit_price(r, b, e, sess)
            rec[f"X:{r}"] = px / o - 1 - COST if px > 0 else np.nan
        rows.append(rec)
    return pd.DataFrame(rows)


def group_mask(O: pd.DataFrame, grp: str) -> pd.Series:
    return O["traded"].astype(bool) if grp == "top3" else (~O["traded"].astype(bool)) & (O["rank"] <= CFG["top"])


def paired_daily(O: pd.DataFrame, col: str, is_entry: bool, grp: str = "top3") -> pd.Series:
    """Per signal day, the group's mean paired difference vs the baseline (unfilled entries hold cash: 0)."""
    t = O[group_mask(O, grp) & O["base"].notna()]
    if is_entry:
        contrib = t[col].where(t[f"Efill:{col[2:]}"].astype(bool), 0.0)
        diff = contrib - t["base"]
    else:
        diff = t[col] - t["base"]
    return diff.groupby(t["signal_day"]).mean().dropna().sort_index()

def boot(series: pd.Series, level: float = 0.95) -> dict:
    x = series.to_numpy(float)
    if len(x) < 20:
        return {"days": int(len(x)), "mean_bp": float("nan"), "lo_bp": float("nan"), "hi_bp": float("nan"), "p": float("nan")}
    b = SD.block_bootstrap(x, level, CFG["boot_B"], CFG["boot_block"], CFG["seed"])
    rng = np.random.default_rng(CFG["seed"])
    n, blk = len(x), CFG["boot_block"]
    means = np.empty(2000)
    for k in range(2000):
        st = rng.integers(0, n, size=int(np.ceil(n / blk)))
        means[k] = x[((st[:, None] + np.arange(blk)[None, :]) % n).ravel()[:n]].mean()
    centred = means - x.mean()
    p = float(min(1.0, 2 * min((centred >= abs(x.mean())).mean(), (centred <= -abs(x.mean())).mean()) + 1 / 2000))
    return {"days": int(n), "mean_bp": b["mean"] * 1e4, "lo_bp": b["lo"] * 1e4, "hi_bp": b["hi"] * 1e4, "p": p}


def bh(pvals: Dict[str, float], q: float) -> List[str]:
    items = sorted((p, k) for k, p in pvals.items() if np.isfinite(p))
    m, keep = len(items), 0
    for i, (p, k) in enumerate(items, 1):
        if p <= q * i / m:
            keep = i
    return [k for _, k in items[:keep]]


def protocol(O: pd.DataFrame, rules: List[Tuple[str, bool]]) -> pd.DataFrame:
    disc_end = pd.Timestamp(CFG["discovery_end"])
    conf_start = pd.Timestamp(CFG["confirmation_start"])
    rows, pv = [], {}
    for col, is_entry in rules:
        s = paired_daily(O, col, is_entry)
        d = boot(s[s.index <= disc_end])
        c = boot(s[s.index >= conf_start])
        rows.append({"rule": col, "kind": "entry" if is_entry else "exit", **{f"disc_{k}": v for k, v in d.items()},
                     **{f"conf_{k}": v for k, v in c.items()}})
        pv[col] = d["p"]
    R = pd.DataFrame(rows)
    surv = set(bh(pv, CFG["fdr_q"]))
    R["discovery_survivor"] = R["rule"].isin(surv)
    R["confirmed"] = R["discovery_survivor"] & (np.sign(R["disc_mean_bp"]) == np.sign(R["conf_mean_bp"])) & (R["conf_lo_bp"] > 0)
    R["verdict"] = np.where(R["confirmed"], "CONFIRMED -> forward lane", np.where(R["discovery_survivor"], "failed confirmation - discarded",
                                                                                  "failed discovery - discarded"))
    return R


# ----------------------------------------------------------------------
# path, findings, descriptors
# ----------------------------------------------------------------------
def tug_of_war(picks: pd.DataFrame, daily: Dict[str, EX.Bars], intra: Dict[str, pd.DataFrame], cal: np.ndarray) -> pd.DataFrame:
    """F2: per held session 1-5, the mean overnight gap and session return, and the session's return by time bucket."""
    pos = {d: i for i, d in enumerate(cal)}
    buckets = [(0, 15), (15, 60), (60, 240), (240, 315), (315, 375)]
    acc = []
    for _, p in picks.iterrows():
        b, X = daily.get(p["symbol"]), intra.get(p["symbol"])
        i = pos.get(np.datetime64(pd.Timestamp(p["signal_day"]), "ns"))
        if b is None or X is None or i is None or i + 1 >= len(cal):
            continue
        e = b.index.get(cal[i + 1])
        if e is None or e < 1:
            continue
        days = X["timestamp"].dt.normalize()
        for s in range(1, 6):
            j = e + s - 1
            if j >= len(b.c):
                break
            S = X[days == pd.Timestamp(b.ts[j])]
            if S.empty:
                continue
            m = minutes(S)
            o0 = float(S["open"].iloc[0])
            r = {"signal_day": p["signal_day"], "session": s, "gap": (b.o[j] / b.c[j - 1] - 1) if s > 1 else 0.0,
                 "entry_gap": (b.o[j] / b.c[j - 1] - 1) if s == 1 else np.nan,      # before entry: reported, not earned
                 "session_ret": float(S["close"].iloc[-1]) / o0 - 1}
            prev = o0
            for a, z in buckets:
                part = S[m < z]
                cl = float(part["close"].iloc[-1]) if len(part) else prev
                r[f"min_{a}_{z}"] = cl / prev - 1
                prev = cl
            acc.append(r)
    return pd.DataFrame(acc)


def bracket_intraday(b: EX.Bars, e: int, sess: Dict[int, pd.DataFrame], tp: float, sl: float) -> float:
    """F6: the declared 3 ATR / 2 ATR bracket with true 3-minute ordering (gaps fill at the bar open)."""
    P = float(sess[1]["open"].iloc[0])
    TP, SL = P * (1 + tp), P * (1 - sl)
    for s in range(1, 6):
        S = sess.get(s)
        if S is None or S.empty:
            return float("nan")
        for o, h, l in zip(S["open"].to_numpy(float), S["high"].to_numpy(float), S["low"].to_numpy(float)):
            if o >= TP:
                return o / P - 1 - COST
            if o <= SL:
                return o / P - 1 - COST
            hit_t, hit_s = h >= TP, l <= SL
            if hit_s and not hit_t:
                return -sl - COST
            if hit_t and not hit_s:
                return tp - COST
            if hit_t and hit_s:
                return -sl - COST                              # both inside one 3-minute bar: still conservative
    x, kind, raw, fl = EX.plan_exit(b, e, 5, None)
    return raw / P - 1 - COST


def findings(picks, daily, intra, cal, O=None) -> Dict[str, object]:
    F = {}
    tw = tug_of_war(picks, daily, intra, cal)
    if len(tw):
        conf = tw[pd.to_datetime(tw["signal_day"]) >= pd.Timestamp(CFG["confirmation_start"])]
        F["F2_tug_of_war"] = {"entry_gap_bp_not_earned": round(float(tw["entry_gap"].mean() * 1e4), 1),
                              "by_session": tw.groupby("session")[["gap", "session_ret"]].mean().mul(1e4).round(1).to_dict(),
                              "confirmation_by_session": conf.groupby("session")[["gap", "session_ret"]].mean().mul(1e4).round(1).to_dict() if len(conf) else {},
                              "where_in_session_bp": tw[[c for c in tw.columns if c.startswith("min_")]].mean().mul(1e4).round(1).to_dict()}
    pos = {d: i for i, d in enumerate(cal)}
    br, pl, slip = [], [], []
    for _, p in picks.iterrows():
        b, X = daily.get(p["symbol"]), intra.get(p["symbol"])
        i = pos.get(np.datetime64(pd.Timestamp(p["signal_day"]), "ns"))
        if b is None or X is None or i is None or i + 1 >= len(cal):
            continue
        e = b.index.get(cal[i + 1])
        if e is None or e < 15:
            continue
        days = X["timestamp"].dt.normalize()
        sess = {s: X[days == pd.Timestamp(b.ts[e + s - 1])] for s in range(1, 6) if e + s - 1 < len(b.c)}
        if sess.get(1, pd.DataFrame()).empty:
            continue
        atr = SP.atr_frac(b, e, 14)
        if np.isfinite(atr) and atr > 0 and len(sess) == 5:
            br.append(bracket_intraday(b, e, sess, 3 * atr, 2 * atr))
            x, kind, raw, fl = EX.plan_exit(b, e, 5, None)
            pl.append(raw / float(sess[1]["open"].iloc[0]) - 1 - COST)
        f = sess[1].iloc[0]
        slip.append({"price": float(f["open"]), "first_bar_vwap_vs_open_bp": (IF.vwap(sess[1].iloc[:1]) / float(f["open"]) - 1) * 1e4,
                     "first_bar_range_bp": (float(f["high"]) - float(f["low"])) / float(f["open"]) * 1e4})
    if br:
        F["F6_bracket_3min"] = {"trades": len(br), "bracket_net_bp": float(np.nanmean(br) * 1e4), "plain_exit_net_bp": float(np.nanmean(pl) * 1e4),
                                "bracket_still_loses": bool(np.nanmean(br) < np.nanmean(pl))}
    if slip:
        S = pd.DataFrame(slip)
        S["price_band"] = pd.cut(S["price"], [0, 20, 100, 500, 2000, 1e9], labels=["<20", "20-100", "100-500", "500-2000", ">2000"])
        F["F7_opening_execution_bp"] = S.groupby("price_band", observed=True)[["first_bar_vwap_vs_open_bp", "first_bar_range_bp"]].median().round(1).to_dict()
    return F


def descriptor_table(picks, daily, intra, cal, nifty: Optional[pd.DataFrame] = None,
                     dvol: Optional[Dict[str, pd.Series]] = None) -> pd.DataFrame:
    """Descriptors of the pick day T (known before entry) and of session 1 (after entry), with the baseline outcome."""
    pos = {d: i for i, d in enumerate(cal)}
    rows = []
    nd = nifty["timestamp"].dt.normalize() if nifty is not None and len(nifty) else None
    for _, p in picks.iterrows():
        b, X = daily.get(p["symbol"]), intra.get(p["symbol"])
        i = pos.get(np.datetime64(pd.Timestamp(p["signal_day"]), "ns"))
        if b is None or X is None or i is None or i + 1 >= len(cal):
            continue
        e = b.index.get(cal[i + 1])
        if e is None or e < 22:
            continue
        days = X["timestamp"].dt.normalize()
        vols = X.groupby(days)["volume"].sum()
        x, kind, raw, fl = EX.plan_exit(b, e, 5, None)
        for tag, j in (("T", e - 1), ("S1", e)):
            D = X[days == pd.Timestamp(b.ts[j])]
            if D.empty:
                continue
            src = dvol.get(p["symbol"]) if dvol else None          # the daily cache's volume: available for every session
            src = src if src is not None else vols
            pv = src[src.index < pd.Timestamp(b.ts[j])].tail(20).to_numpy(float)
            nday = nifty[nd == pd.Timestamp(b.ts[j])] if nd is not None else None
            dsc = IF.descriptors(D, float(b.c[j - 1]), pv, nday)
            rows.append({"signal_day": p["signal_day"], "symbol": p["symbol"], "engine": p["engine"], "when": tag,
                         "base": raw / float(b.o[e]) - 1 - COST, **dsc})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------
# the run
# ----------------------------------------------------------------------
def frozen_picks(root: Path, daily: Dict[str, EX.Bars], cal: np.ndarray) -> pd.DataFrame:
    import freeze_engines as FZ
    pp = root / "panel_oc" / "panel.parquet"
    man = FZ.verify_frozen(pp)
    extra = RC.load_symbol_list(root / RC.UNIVERSE_EXCLUDE_FILE)
    pos = {d: i for i, d in enumerate(cal)}
    parts = []
    for eng in ("D", "ENS"):
        pr = pd.read_parquet(pp.parent / "stage_d" / man["engines"][eng]["run"] / "preds.parquet")
        pr = pr[pr["target"].astype(str) == man["target"]].copy()
        pr["symbol"] = pr["symbol"].astype(str)
        pr["timestamp"] = SB._naive(pr["timestamp"])
        pr = pr[~pr["symbol"].map(lambda s: RC.is_etf_symbol(s, extra))]
        pr = pr.sort_values(["timestamp", "score", "symbol"], ascending=[True, False, True])
        top = pr.groupby("timestamp").head(CFG["top"]).copy()
        top["rank"] = top.groupby("timestamp").cumcount() + 1
        top["engine"] = eng
        parts.append(top.rename(columns={"timestamp": "signal_day"})[["signal_day", "symbol", "engine", "rank"]])
    P = pd.concat(parts, ignore_index=True)
    traded = []
    for (d, eng), g in P.groupby(["signal_day", "engine"]):
        i = pos.get(np.datetime64(pd.Timestamp(d), "ns"))
        n = 0
        for _, r in g.sort_values("rank").iterrows():
            b = daily.get(r["symbol"])
            ok = False
            if b is not None and i is not None and i + 1 < len(cal):
                e = b.index.get(cal[i + 1])
                if e is not None and e >= 1:
                    tk = SF.tick_size(np.array([b.ts[e]]), np.array([b.c[e - 1]]))[0]
                    ok = not (SF.band_up(b.o[e], b.c[e - 1], tk) and b.o[e] >= b.h[e] * (1 - 1e-9))
            traded.append(bool(ok and n < CFG["traded"]))
            n += int(ok)
    P = P.sort_values(["signal_day", "engine", "rank"]).reset_index(drop=True)
    P["traded"] = traded
    return P


def frozen_candidates(root: Path, daily: Dict[str, EX.Bars], cal: np.ndarray, rebuild_reason: Optional[str] = None):
    """The candidate set, built ONCE from the frozen predictions and saved with its fingerprint and exclusion list."""
    d = root / "research2" / "intraday"
    fp, meta = d / "frozen_candidates.parquet", d / "frozen_candidates.json"
    if fp.exists() and not rebuild_reason:
        m = json.loads(meta.read_text(encoding="utf-8"))
        if hashlib.sha256(fp.read_bytes()).hexdigest()[:16] != m["sha"]:
            raise PreconditionError("frozen_candidates.parquet changed since it was built - restore it, or rebuild with a reason")
        P = pd.read_parquet(fp)
        P["signal_day"] = pd.to_datetime(P["signal_day"])
        return P, m["sha"]
    if fp.exists():
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        fp.replace(d / f"frozen_candidates_{stamp}.parquet")
        meta.replace(d / f"frozen_candidates_{stamp}.json")
    P = frozen_picks(root, daily, cal)
    d.mkdir(parents=True, exist_ok=True)
    P.to_parquet(fp, index=False)
    excl = root / RC.UNIVERSE_EXCLUDE_FILE
    m = {"sha": hashlib.sha256(fp.read_bytes()).hexdigest()[:16], "built_at": dt.datetime.now().isoformat(), "tool": CODE_VERSION,
         "exclusion_file_sha": hashlib.sha256(excl.read_bytes()).hexdigest()[:16] if excl.exists() else None,
         "rows": int(len(P)), "rebuild_reason": rebuild_reason}
    meta.write_text(json.dumps(m, indent=2), encoding="utf-8")
    return P, m["sha"]


def write_report(out: Path, R: pd.DataFrame, core: pd.DataFrame, F: dict, Dsc: pd.DataFrame, sha: str, n: dict) -> None:
    L = ["# Intraday study of the frozen picks", "", f"{CODE_VERSION} | declaration {sha} | {n['days']:,} signal days | 3-minute bars "
         f"| candidates {n['cand_sha']}", "",
         "**Descriptive.** Baseline = buy at the 09:15 open, sell at the 5th close (honest exits), 35 bp; entry rules keep the same "
         "calendar exit. Differences are per signal day with 95% intervals. Rows marked BENCHMARK and the oracles are never rules.", ""]
    for eng in ENGINES:
        for grp in GROUPS:
            c = core[(core["engine"] == eng) & (core["group"] == grp)]
            if c.empty:
                continue
            L += [f"## Core menus - {eng}, {'traded top 3' if grp == 'top3' else 'ranks 4-10 (not traded)'}", "",
                  "| rule | vs baseline bp [95%] | fill rate |", "|---|---|---|"]
            for _, r in c.iterrows():
                tag = " (BENCHMARK)" if r["benchmark"] else ""
                L.append(f"| {r['rule']}{tag} | {r['mean_bp']:+.1f} [{r['lo_bp']:+.1f}, {r['hi_bp']:+.1f}] | {r['fill']:.0%} |")
            L.append("")
    for eng in ENGINES:
        Re = R[R["engine"] == eng]
        if Re.empty:
            continue
        L += [f"## Catalogue protocol - {eng} traded top 3 ({len(Re)} rules, BH q = {CFG['fdr_q']}){' - forward lanes come only from D' if eng == 'ENS' else ''}", "",
              "| rule | discovery bp [95%] | p | confirmation bp [95%] | verdict |", "|---|---|---|---|---|"]
        for _, r in Re.sort_values(["confirmed", "discovery_survivor", "disc_p"], ascending=[False, False, True]).iterrows():
            v = r["verdict"] if not (r["confirmed"] and eng == "ENS") else "confirmed (ensemble - reported, not a forward lane)"
            L.append(f"| {r['rule']} | {r['disc_mean_bp']:+.1f} [{r['disc_lo_bp']:+.1f}, {r['disc_hi_bp']:+.1f}] | {r['disc_p']:.3f} | "
                     f"{r['conf_mean_bp']:+.1f} [{r['conf_lo_bp']:+.1f}, {r['conf_hi_bp']:+.1f}] | {v} |")
        L.append("")
    L += ["## Findings register (F2, F6, F7 here; F1, F3, F4, F5 in the next step)", "", "```", json.dumps(F, indent=1, default=str), "```", ""]
    if len(Dsc):
        conf = pd.to_datetime(Dsc["signal_day"]) >= pd.Timestamp(CFG["confirmation_start"])
        L += ["## Descriptors vs the 5-session outcome (rank correlation by window; a sign flip means noise)", "",
              "| engine | group | descriptor | when | discovery | confirmation |", "|---|---|---|---|---|---|"]
        for (eng, grp, w), g in Dsc.groupby(["engine", "group", "when"]):
            cf = conf[g.index]
            for dname in IF.DESCRIPTORS:
                a, b_ = g[~cf], g[cf]
                ca = a[dname].corr(a["base"], method="spearman") if a[dname].notna().sum() > 30 else np.nan
                cb = b_[dname].corr(b_["base"], method="spearman") if b_[dname].notna().sum() > 30 else np.nan
                if np.isfinite(ca) or np.isfinite(cb):
                    L.append(f"| {eng} | {grp} | {dname} | {'pick day' if w == 'T' else 'session 1'} | {ca:+.3f} | {cb:+.3f} |")
    L += ["", "Nothing here changes the engines or the paper test; a confirmed D rule becomes its own forward lane.", ""]
    (out / "intraday_report.md").write_text("\n".join(L), encoding="utf-8")

def run(picks: pd.DataFrame, daily: Dict[str, EX.Bars], intra: Dict[str, pd.DataFrame], cal: np.ndarray,
        nifty: Optional[pd.DataFrame] = None, dvol: Optional[Dict[str, pd.Series]] = None,
        ok_days: Optional[Dict[str, set]] = None) -> dict:
    entries = sorted(set(ENTRY_CORE + CATALOGUE_ENTRY + ["ORACLE_LOW"]))
    exits = sorted(set(EXIT_CORE + CATALOGUE_EXIT + ["ORACLE_HIGH"]))
    counts = {}
    O = pick_outcomes(picks, daily, intra, cal, entries, exits, ok_days, counts)
    if O.empty:
        raise PreconditionError("no pick has intraday bars for its entry session - import or update the 3-minute cache")
    rules = [(f"E:{r}", True) for r in entries if r not in BENCHMARK_ONLY] + \
            [(f"X:{r}", False) for r in exits if r not in BENCHMARK_ONLY]
    core, prot, F, Dsc = [], [], {}, []
    for eng in ENGINES:
        OE = O[O["engine"] == eng]
        if OE.empty:
            continue
        for grp in GROUPS:
            t = OE[group_mask(OE, grp)]
            if t.empty:
                continue
            for r in ENTRY_CORE + ["ORACLE_LOW"]:
                core.append({"engine": eng, "group": grp, "rule": f"entry {r}", "fill": float(t[f"Efill:{r}"].mean()),
                             "benchmark": r in BENCHMARK_ONLY, **boot(paired_daily(OE, f"E:{r}", True, grp))})
            for r in EXIT_CORE + ["ORACLE_HIGH"]:
                core.append({"engine": eng, "group": grp, "rule": f"exit {r}", "fill": 1.0,
                             "benchmark": r in BENCHMARK_ONLY, **boot(paired_daily(OE, f"X:{r}", False, grp))})
            pk = picks[(picks["engine"] == eng) & group_mask(picks, grp)]
            F[f"{eng}_{grp}"] = findings(pk, daily, intra, cal)
            dt_ = descriptor_table(pk, daily, intra, cal, nifty, dvol)
            if len(dt_):
                Dsc.append(dt_.assign(group=grp))
        R = protocol(OE, rules).assign(engine=eng)
        R["forward_lane"] = R["confirmed"] & (eng == "D")
        prot.append(R)
    F["reconciliation_exclusions"] = counts
    return {"outcomes": O, "core": pd.DataFrame(core), "protocol": pd.concat(prot, ignore_index=True), "findings": F,
            "descriptors": pd.concat(Dsc, ignore_index=True) if Dsc else pd.DataFrame()}

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Intraday study of the frozen picks")
    ap.add_argument("--root", required=True)
    ap.add_argument("--rebuild-candidates", default=None, metavar="REASON",
                    help="rebuild the frozen candidate set (only with a stated reason; the old set is kept beside it)")
    a = ap.parse_args(argv)
    root = Path(a.root)
    sha = hashlib.sha256(DECL_RAW).hexdigest()[:16]
    files = sorted(IC.store(root).glob(f"*_{IC.BAR_MIN}m.parquet"))
    if not files:
        raise PreconditionError(f"no 3-minute data in {IC.store(root)} - run intraday_cache.py import / update first")
    syms = [f.name[: -len(f"_{IC.BAR_MIN}m.parquet")] for f in files]
    daily = EX.load_bars(root, syms)
    intra = {s: pd.read_parquet(f) for s, f in zip(syms, files)}
    cal = np.unique(np.concatenate([b.ts for b in daily.values()]))
    picks, cand_sha = frozen_candidates(root, daily, cal, a.rebuild_candidates)
    first = min(x["timestamp"].min() for x in intra.values())
    picks = picks[pd.to_datetime(picks["signal_day"]) >= pd.Timestamp(first)]
    nifty = intra.pop("NIFTY 50", None)
    from data_quality import _paths
    dvol, ok_days = {}, {}
    for s_ in intra:
        fp_, _ = _paths(root, s_)
        if Path(fp_).exists():
            v = pd.read_parquet(fp_, columns=["timestamp", "open", "high", "low", "close", "volume"])
            v["timestamp"] = SB._naive(v["timestamp"])
            dvol[s_] = v.assign(timestamp=v["timestamp"].dt.normalize()).set_index("timestamp")["volume"].astype(float)
            J = IC.reconcile_symbol(intra[s_], v, CFG["reconcile_price_tol"], CFG["reconcile_volume_tol"])
            ok_days[s_] = set(pd.to_datetime(J.loc[J["ok"], "day"]).dt.normalize()) if len(J) else set()
    res = run(picks, daily, intra, cal, nifty, dvol, ok_days)
    day = dt.date.today().strftime("%Y%m%d")
    out_root = root / "research2" / "intraday"
    k = 1
    while (out_root / f"IS_{day}_{k:03d}").exists():
        k += 1
    out = out_root / f"IS_{day}_{k:03d}"
    out.mkdir(parents=True)
    res["outcomes"].to_csv(out / "picks.csv", index=False)
    res["protocol"].to_csv(out / "catalogue.csv", index=False)
    res["core"].to_csv(out / "core.csv", index=False)
    res["descriptors"].to_csv(out / "descriptors.csv", index=False)
    n = {"days": int(res["outcomes"]["signal_day"].nunique()), "cand_sha": cand_sha}
    write_report(out, res["protocol"], res["core"], res["findings"], res["descriptors"], sha, n)
    Rp = res["protocol"]
    print(f"{CODE_VERSION}: {n['days']:,} signal days; D: {int(Rp[(Rp['engine'] == 'D')]['discovery_survivor'].sum())} discovery "
          f"survivors, {int(Rp['forward_lane'].sum())} confirmed (forward lanes); ENS: {int(Rp[(Rp['engine'] == 'ENS')]['confirmed'].sum())} confirmed (reported)")
    print(f"  report: {out / 'intraday_report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
