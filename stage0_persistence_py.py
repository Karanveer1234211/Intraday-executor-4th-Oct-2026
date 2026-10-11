#!/usr/bin/env python3
"""
stage0_persistence.py - Stage 0 of the 10-stock behavioural engine (declaration: STAGE0_DECLARATION.json, fixed before
any run). One question: is there persistent STOCK-SPECIFIC intraday behaviour at all?

    python stage0_persistence.py --root %CACHE_DAILY_ROOT%

In plain words: 10 simple setups, long and short separately (20 setup-sides), each entered at the next bar's open after
its signal bar closes and closed at 15:03, net of costs. For every liquid stock, each setup-side's mean net return is
measured against the stock's own plain open-to-15:03 trade in the same direction (the 'excess'), once in H1
(2021-10-01..2023-05-31) and once in H2 (2023-06-01..2024-12-31). If stocks that were good at a setup in H1 are still
good at it in H2 - more than shuffled stock labels give, after a Holm correction for 20 setup-sides - AND the H1
top-decile stocks make money after costs in H2 (block-bootstrap interval above zero), the run PASSES and lists the
candidate stocks (2021-2024 only). Otherwise it reports 'no persistent stock-specific behaviour'. 2025 onward is never
used.

Reuses bigmove_study v1.1 (liquid universe, usable sessions, bar slots, VWAP, time exit, costs, block bootstrap, ETF
rules, ledger) and intraday_cache v1.7 (store, reconciliation). Writes only <root>\\research2\\stage0\\S0_<date>_<n>\\
and one line in <root>\\panel\\research_ledger.jsonl.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import platform
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
if str(HERE.parent) not in sys.path:
    sys.path.append(str(HERE.parent))     # bigmove_deploy (PYTHONPATH should already have it)

import bigmove_study as BM                # tested v1.1: universe, sessions, bar slots, VWAP, time exit, costs, bootstrap

CODE_VERSION = "stage0_persistence v1.0"
DECL_RAW = (HERE / "STAGE0_DECLARATION.json").read_bytes()
DECL = json.loads(DECL_RAW.decode("utf-8"))
CFG = DECL["config"]
NB, BAR = BM.NB, BM.BAR
X_BAR = int(CFG["exit_minute"]) // BAR          # 116: the 15:03 bar
E_LAST = int(CFG["entry_last_minute"]) // BAR   # 105: the 14:30 bar, last allowed entry
K_LAST = int(CFG["signal_last_bar"])            # 104
SETUPS = ["ORC", "ORF", "GAPC", "GAPF", "VWR", "FHM", "CMP", "PDB", "PDR", "VSF"]
SIDES = (("L", 1), ("S", -1))
SS = [f"{s}_{n}" for s in SETUPS for n, _ in SIDES]       # the 20 setup-sides, in declared order
SS_SIDE = {f"{s}_{n}": d for s in SETUPS for n, d in SIDES}
H1 = (pd.Timestamp(CFG["h1_start"]), pd.Timestamp(CFG["h1_end"]))
H2 = (pd.Timestamp(CFG["h2_start"]), pd.Timestamp(CFG["h2_end"]))
COST_BPS = BM.cash_cost_bps(float(CFG["notional_rs"]))
TRADE_COST = (COST_BPS + float(CFG["slip_entry_bps"]) + float(CFG["slip_time_bps"])) / 1e4   # 12.49 bp a trade


class PreconditionError(SystemExit):
    pass


def _log(msg: str) -> None:
    print(f"{dt.datetime.now():%H:%M:%S}  {msg}", flush=True)


def check_reuse() -> None:
    """The reused bigmove_study must apply exactly the rules this declaration states."""
    want = {"session_bars": NB, "bar_min": BAR, "min_bar_share": BM.CFG["min_bar_share"], "min_price": BM.CFG["min_price"],
            "min_value_cr": BM.CFG["min_value_cr"], "exit_minute": int(BM.CFG["exit_minute"])}
    bad = [k for k, v in want.items() if float(CFG[k]) != float(v)]
    if bad or abs(COST_BPS - float(CFG["cost_bps_expected"])) > 0.005:
        raise PreconditionError(f"bigmove_study's rules differ from STAGE0_DECLARATION ({bad or ''} cost {COST_BPS:.3f} bp): "
                                f"use bigmove_study v1.1 with BIGMOVE_DECLARATION.json")


# ----------------------------------------------------------------------
# one stock: signals, trades and the plain trade
# ----------------------------------------------------------------------
def _prev(F: pd.DataFrame, trow: np.ndarray, col: str) -> np.ndarray:
    """F[col] at the PREVIOUS daily row of each session (NaN when there is none)."""
    okr = trow >= 1
    return np.where(okr, F[col].to_numpy(float)[np.maximum(trow - 1, 0)], np.nan)


def slot_baseline(V: np.ndarray, use: np.ndarray) -> np.ndarray:
    """Per session and bar slot: mean volume of that slot over the previous `vsf_history` usable sessions (at least
    `vsf_min_history` present); today's session is never in its own baseline."""
    Vu = np.where(np.asarray(use, bool)[:, None], V, np.nan)
    return pd.DataFrame(Vu).shift(1).rolling(int(CFG["vsf_history"]), min_periods=int(CFG["vsf_min_history"])).mean().to_numpy(float)


def box_stats(H: np.ndarray, L: np.ndarray, C: np.ndarray, pdc: np.ndarray, use: np.ndarray) -> Tuple[np.ndarray, ...]:
    """The 10:15-11:15 box per session: high, low, width (range / previous close; NaN with fewer than `box_min_bars` bars),
    and the `box_pct` quantile of the stock's own widths over its previous `box_history` usable sessions (today never counts)."""
    b0, b1 = int(CFG["box_first_bar"]), int(CFG["box_last_bar"])
    bh, bl = BM._rowmax(H[:, b0:b1 + 1]), BM._rowmin(L[:, b0:b1 + 1])
    with np.errstate(invalid="ignore", divide="ignore"):
        w = np.where(np.isfinite(C[:, b0:b1 + 1]).sum(1) >= int(CFG["box_min_bars"]), (bh - bl) / pdc, np.nan)
    hist = pd.Series(np.where(np.asarray(use, bool), w, np.nan)).shift(1)
    q = hist.rolling(int(CFG["box_history"]), min_periods=int(CFG["box_min_history"])).quantile(float(CFG["box_pct"])).to_numpy(float)
    return bh, bl, w, q


def _after(M: np.ndarray, k1: np.ndarray, hi: int) -> np.ndarray:
    """First column in (k1, hi] where M holds, per row; -1 when k1 is -1 or nothing holds."""
    return BM.first_true(M, np.where(k1 >= 0, k1 + 1, NB), hi)


def signals(cx: dict) -> Dict[str, np.ndarray]:
    """Signal bar per session for every setup-side (-1: no signal). Each uses bars up to and including its signal bar and
    daily values at the previous close only."""
    O, H, L, C, V = cx["open"], cx["high"], cx["low"], cx["close"], cx["volume"]
    O0, atr, pdh, pdl, gap = cx["O0"], cx["atr"], cx["pdh"], cx["pdl"], cx["gap"]
    D = len(O0)
    none = np.full(D, -1)
    at = lambda cond, k: np.where(cond & np.isfinite(C[:, k]), k, -1)
    r = int(CFG["or_bars"])
    orh, orl = BM._rowmax(H[:, :r]), BM._rowmin(L[:, :r])
    out = {}
    out["ORC_L"] = BM.first_true(C > orh[:, None], r, K_LAST)
    out["ORC_S"] = BM.first_true(C < orl[:, None], r, K_LAST)
    out["ORF_L"] = _after(C > orl[:, None], BM.first_true(C < orl[:, None], r, K_LAST - 1), K_LAST)
    out["ORF_S"] = _after(C < orh[:, None], BM.first_true(C > orh[:, None], r, K_LAST - 1), K_LAST)
    g, kg = float(CFG["gap_atr"]) * atr, int(CFG["gap_signal_bar"])
    up, dn = C[:, kg] > O0, C[:, kg] < O0
    out["GAPC_L"], out["GAPC_S"] = at((gap >= g) & up, kg), at((gap <= -g) & dn, kg)
    out["GAPF_L"], out["GAPF_S"] = at((gap <= -g) & up, kg), at((gap >= g) & dn, kg)
    with np.errstate(invalid="ignore", divide="ignore"):
        dev = C / cx["vwap"] - 1
    s, k0, k1 = float(CFG["vwap_atr"]) * atr[:, None], int(CFG["vwap_first_bar"]), int(CFG["vwap_last_bar"])
    out["VWR_L"], out["VWR_S"] = BM.first_true(dev <= -s, k0, k1), BM.first_true(dev >= s, k0, k1)
    kf = int(CFG["fhm_signal_bar"])
    with np.errstate(invalid="ignore", divide="ignore"):
        r1 = C[:, kf] / O0 - 1
    m = float(CFG["fhm_atr"]) * atr
    out["FHM_L"], out["FHM_S"] = at(r1 >= m, kf), at(r1 <= -m, kf)
    b1 = int(CFG["box_last_bar"])
    bh, bl = cx["box_high"], cx["box_low"]
    narrow = cx["box_w"] <= cx["box_q"]
    out["CMP_L"] = np.where(narrow, BM.first_true(C > bh[:, None], b1 + 1, K_LAST), -1)
    out["CMP_S"] = np.where(narrow, BM.first_true(C < bl[:, None], b1 + 1, K_LAST), -1)
    out["PDB_L"] = np.where(O0 < pdh, BM.first_true(C > pdh[:, None], 0, K_LAST), -1)
    out["PDB_S"] = np.where(O0 > pdl, BM.first_true(C < pdl[:, None], 0, K_LAST), -1)
    out["PDR_L"] = _after(C > pdl[:, None], BM.first_true(C < pdl[:, None], 0, K_LAST - 1), K_LAST)
    out["PDR_S"] = _after(C < pdh[:, None], BM.first_true(C > pdh[:, None], 0, K_LAST - 1), K_LAST)
    spike = V >= float(CFG["vsf_mult"]) * cx["vbase"]
    v0, v1 = int(CFG["vsf_first_bar"]), int(CFG["vsf_last_bar"])
    out["VSF_L"], out["VSF_S"] = BM.first_true(spike & (C > O), v0, v1), BM.first_true(spike & (C < O), v0, v1)
    return {k: np.where(cx["base"], out.get(k, none), -1) for k in SS}


def stock_context(F: pd.DataFrame, days: np.ndarray, B: Dict[str, np.ndarray], liq_days: np.ndarray) -> dict:
    """A stock's sessions with what its signals need. 'base' = usable session, liquid at the previous close, a previous
    daily row with ATR > 0 and a close, inside H1 or H2, and an open within 20% of the previous close."""
    days = np.asarray(days, dtype="datetime64[ns]")
    D = len(days)
    rowmap = {pd.Timestamp(d): i for i, d in enumerate(F["day"])}
    trow = np.array([rowmap.get(pd.Timestamp(d), -1) for d in days], int)
    okr = trow >= 1
    use = BM.usable_sessions(B) if D else np.zeros(0, bool)
    liq = np.zeros(D, bool)
    liq[okr] = np.asarray(liq_days, bool)[trow[okr]]
    O, H, L, C, V = (np.asarray(B[k], float) for k in ("open", "high", "low", "close", "volume"))
    pdh, pdl, pdc, atr = (_prev(F, trow, c) for c in ("high", "low", "close", "atr14"))
    O0 = O[:, 0] if D else np.zeros(0)
    with np.errstate(invalid="ignore", divide="ignore"):
        gap = O0 / pdc - 1
    d = pd.DatetimeIndex(days)
    inwin = np.asarray(((d >= H1[0]) & (d <= H1[1])) | ((d >= H2[0]) & (d <= H2[1])))
    base = use & liq & okr & np.isfinite(atr) & (atr > 0) & np.isfinite(pdc) & (np.abs(gap) <= float(CFG["max_abs_gap"])) & inwin
    bh, bl, bw, bq = box_stats(H, L, C, pdc, use)
    return {"box_high": bh, "box_low": bl, "box_w": bw, "box_q": bq, "days": days, "base": base, "use": use, "liq": liq, "open": O, "high": H, "low": L, "close": C, "volume": V, "O0": O0,
            "pdh": pdh, "pdl": pdl, "pdc": pdc, "atr": atr, "gap": gap, "vwap": BM.session_vwap(H, L, C, V),
            "vbase": slot_baseline(V, use), "pxt": BM.time_exit_price(O, C)}


def stock_trades(F: pd.DataFrame, days: np.ndarray, B: Dict[str, np.ndarray], liq_days: np.ndarray,
                 stats: Optional[dict] = None) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """(trades, plain) for one stock. trades: one row per stock-day and setup-side that traded - day, ss (index into SS),
    signal bar, entry bar, entry price, gross and net return. plain: every base session - day, the plain long trade's
    gross return (open to the 15:03 exit; the short is its negative) and ATR. `stats` counts the basis-guard drops."""
    cx = stock_context(F, days, B, liq_days)
    if stats is not None:
        with np.errstate(invalid="ignore"):
            stats["basis_guard_days"] += int((cx["use"] & cx["liq"] & (np.abs(cx["gap"]) > float(CFG["max_abs_gap"]))).sum())
    D = len(cx["days"])
    if D == 0:
        return pd.DataFrame(columns=["day", "ss", "sig", "ent", "entry", "gross", "net"]), pd.DataFrame(columns=["day", "gross", "atr"])
    O, pxt, rows = cx["open"], cx["pxt"], np.arange(D)
    fin_o = np.isfinite(O)
    parts = []
    for j, (name, k) in enumerate(signals(cx).items()):
        e = BM.first_true(fin_o, np.where(k >= 0, k + 1, NB), E_LAST)
        entry = np.where(e >= 0, O[rows, np.maximum(e, 0)], np.nan)
        with np.errstate(invalid="ignore", divide="ignore"):
            g = SS_SIDE[name] * (pxt / entry - 1)
        ok = (e >= 0) & np.isfinite(g)
        if ok.any():
            parts.append(pd.DataFrame({"day": cx["days"][ok], "ss": np.int8(j), "sig": k[ok].astype(np.int16),
                                       "ent": e[ok].astype(np.int16), "entry": entry[ok], "gross": g[ok]}))
    T = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["day", "ss", "sig", "ent", "entry", "gross"])
    T["net"] = T["gross"].astype(float) - TRADE_COST
    with np.errstate(invalid="ignore", divide="ignore"):
        pg = pxt / cx["O0"] - 1
    okp = cx["base"] & np.isfinite(pg)
    P = pd.DataFrame({"day": cx["days"][okp], "gross": pg[okp], "atr": cx["atr"][okp]})
    return T, P


# ----------------------------------------------------------------------
# statistics
# ----------------------------------------------------------------------
def half_of(days) -> np.ndarray:
    d = pd.DatetimeIndex(days)
    return np.where((d >= H1[0]) & (d <= H1[1]), "H1", np.where((d >= H2[0]) & (d <= H2[1]), "H2", ""))


def per_stock(trades: pd.DataFrame, plain: pd.DataFrame) -> pd.DataFrame:
    """One row per stock, setup-side and half: trades, mean net (bp), win rate, the plain trade's mean net in the same
    direction over all the stock's base days in that half, and the excess (setup minus plain)."""
    T = trades.assign(half=half_of(trades["day"]), w=(trades["net"] > 0).astype(float))
    T = T[T["half"] != ""]
    g = T.groupby(["sym", "ss", "half"], observed=True)
    A = pd.DataFrame({"trades": g["net"].size(), "net_bp": g["net"].mean() * 1e4, "win": g["w"].mean()}).reset_index()
    P = plain.assign(half=half_of(plain["day"]))
    P = P[P["half"] != ""]
    gp = P.groupby(["sym", "half"], observed=True)
    PA = pd.DataFrame({"plain_days": gp["gross"].size(), "plain_gross": gp["gross"].mean(), "atr_mean": gp["atr"].mean()}).reset_index()
    A = A.merge(PA, on=["sym", "half"], how="left")
    side = np.array([SS_SIDE[SS[int(i)]] for i in A["ss"]])
    A["plain_net_bp"] = (side * A["plain_gross"] - TRADE_COST) * 1e4
    A["excess_bp"] = A["net_bp"] - A["plain_net_bp"]
    A["setup_side"] = [SS[int(i)] for i in A["ss"]]
    return A.drop(columns=["plain_gross"])


def _ranks(x: np.ndarray) -> np.ndarray:
    return pd.Series(np.asarray(x, float)).rank(method="average").to_numpy(float)


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    rx, ry = _ranks(x), _ranks(y)
    rx, ry = rx - rx.mean(), ry - ry.mean()
    den = math.sqrt(float((rx ** 2).sum() * (ry ** 2).sum()))
    return float(rx @ ry / den) if den > 0 else float("nan")


def perm_pvalue(x: np.ndarray, y: np.ndarray, n_perm: int, rng) -> Tuple[float, float]:
    """Spearman rho of x vs y and its one-sided permutation p-value (y shuffled across stocks): (1 + #rho* >= rho) / (1 + n)."""
    rx, ry = _ranks(x), _ranks(y)
    rx, ry = rx - rx.mean(), ry - ry.mean()
    den = math.sqrt(float((rx ** 2).sum() * (ry ** 2).sum()))
    if den <= 0:
        return float("nan"), 1.0
    rho = float(rx @ ry / den)
    hits, done, n = 0, 0, len(ry)
    while done < n_perm:
        b = min(1000, n_perm - done)
        idx = np.argsort(rng.random((b, n)), axis=1)
        hits += int(((ry[idx] @ rx) / den >= rho - 1e-12).sum())
        done += b
    return rho, (1 + hits) / (1 + n_perm)


def holm(p: np.ndarray) -> np.ndarray:
    """Holm-adjusted p-values (family-wise), in the input order."""
    p = np.asarray(p, float)
    m = len(p)
    o = np.argsort(p, kind="stable")
    adj = np.maximum.accumulate(np.minimum(1.0, (m - np.arange(m)) * p[o]))
    out = np.empty(m)
    out[o] = adj
    return out


def boot_ci(x: np.ndarray) -> Tuple[float, float, float]:
    """Mean and 95% circular block-bootstrap interval (bigmove_study's resampler, this declaration's B, block and seed)."""
    x = np.asarray(x, float)
    if len(x) < int(CFG["boot_min_days"]):
        return (float(x.mean()) if len(x) else float("nan")), float("nan"), float("nan")
    idx = BM._block_idx(len(x), int(CFG["boot_B"]), int(CFG["boot_block"]), np.random.default_rng(int(CFG["seed"])))
    m, lo, hi, _ = BM.boot_stats(x, idx)
    return m, lo, hi


def persistence(ps: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    """One row per setup-side: the persistence test, the H1 top decile's H2 money test, and the verdict."""
    nmin, rows = int(CFG["min_trades_per_half"]), []
    T2 = trades[half_of(trades["day"]) == "H2"]
    for j, name in enumerate(SS):
        X = ps[ps["ss"] == j]
        w = X.pivot_table(index="sym", columns="half", values=["excess_bp", "trades", "atr_mean"], observed=True)
        n1 = w["trades"]["H1"] if ("trades", "H1") in w.columns else pd.Series(dtype=float)
        n2 = w["trades"]["H2"] if ("trades", "H2") in w.columns else pd.Series(dtype=float)
        both = w[(n1.reindex(w.index) >= nmin) & (n2.reindex(w.index) >= nmin)] if len(w) else w
        r = {"setup_side": name, "eligible_stocks": int(len(both)), "rho": np.nan, "perm_p": 1.0, "rho_with_atr": np.nan}
        if len(both) >= int(CFG["min_stocks"]):
            x, y = both["excess_bp"]["H1"].to_numpy(float), both["excess_bp"]["H2"].to_numpy(float)
            r["rho"], r["perm_p"] = perm_pvalue(x, y, int(CFG["permutations"]), np.random.default_rng([int(CFG["seed"]), j]))
            r["rho_with_atr"] = spearman(x, both["atr_mean"]["H1"].to_numpy(float))
        h1 = X[(X["half"] == "H1") & (X["trades"] >= nmin)].sort_values(["excess_bp", "sym"], ascending=[False, True], kind="stable")
        r["h1_stocks"] = int(len(h1))
        top = list(h1["sym"].head(int(math.ceil(float(CFG["top_share"]) * len(h1))))) if len(h1) >= int(CFG["min_stocks"]) else []
        r["top_decile"] = len(top)
        tt = T2[(T2["ss"] == j) & T2["sym"].isin(top)]
        dly = tt.groupby("day")["net"].mean().sort_index().to_numpy(float)
        m, lo, hi = boot_ci(dly) if len(top) else (np.nan, np.nan, np.nan)
        r.update({"top_h2_trades": int(len(tt)), "top_h2_days": int(len(dly)),
                  "top_h2_net_bp_trade": float(tt["net"].mean() * 1e4) if len(tt) else np.nan,
                  "top_h2_win": float((tt["net"] > 0).mean()) if len(tt) else np.nan,
                  "top_h2_daily_bp": m * 1e4, "top_h2_lo_bp": lo * 1e4, "top_h2_hi_bp": hi * 1e4,
                  "top_stocks": " ".join(map(str, top))})
        rows.append(r)
    R = pd.DataFrame(rows)
    R["holm_p"] = holm(R["perm_p"].to_numpy(float))
    R["leg1_persistent"] = R["holm_p"] <= float(CFG["alpha"])
    R["leg2_h2_positive"] = R["top_h2_lo_bp"] > 0
    R["passes"] = R["leg1_persistent"] & R["leg2_h2_positive"]
    return R


def pooled(ps: pd.DataFrame) -> pd.DataFrame:
    """All stocks pooled, per setup-side and half: trades, win rate and net bp per trade (context, not a rule)."""
    w = ps.assign(sum_net=ps["net_bp"] * ps["trades"], sum_win=ps["win"] * ps["trades"])
    g = w.groupby(["setup_side", "half"], observed=True)[["trades", "sum_net", "sum_win"]].sum().reset_index()
    g["net_bp_trade"] = g["sum_net"] / g["trades"]
    g["win"] = g["sum_win"] / g["trades"]
    g["order"] = g["setup_side"].map({s: i for i, s in enumerate(SS)})
    return g.sort_values(["order", "half"]).drop(columns=["sum_net", "sum_win", "order"]).reset_index(drop=True)


def plain_persistence(plain: pd.DataFrame) -> Tuple[float, int]:
    """Spearman of each stock's H1 vs H2 mean plain long return (stocks with >= 30 base days in each half)."""
    P = plain.assign(half=half_of(plain["day"]))
    g = P[P["half"] != ""].groupby(["sym", "half"], observed=True)["gross"].agg(["mean", "size"]).unstack("half")
    if not len(g) or ("size", "H1") not in g.columns or ("size", "H2") not in g.columns:
        return float("nan"), 0
    g = g[(g[("size", "H1")] >= int(CFG["min_trades_per_half"])) & (g[("size", "H2")] >= int(CFG["min_trades_per_half"]))]
    return (spearman(g[("mean", "H1")].to_numpy(float), g[("mean", "H2")].to_numpy(float)) if len(g) >= 3 else float("nan")), int(len(g))


def shortlist(R: pd.DataFrame, ps: pd.DataFrame, trades: pd.DataFrame, plain: pd.DataFrame) -> pd.DataFrame:
    """For each PASSING setup-side: stocks with >= 30 trades in each half, ranked by their excess over 2021-10-01..2024-12-31
    (all trades pooled, minus the same-direction plain trade over all their base days); the top `shortlist_n`."""
    out = []
    nmin = int(CFG["min_trades_per_half"])
    win = half_of(trades["day"]) != ""
    pw = plain[half_of(plain["day"]) != ""]
    pm = pw.groupby("sym", observed=True)["gross"].mean()
    for name in R.loc[R["passes"], "setup_side"]:
        j, sd = SS.index(name), SS_SIDE[name]
        X = ps[ps["ss"] == j].pivot_table(index="sym", columns="half", values=["trades", "excess_bp", "net_bp"], observed=True)
        if ("trades", "H1") not in X.columns or ("trades", "H2") not in X.columns:
            continue
        X = X[(X[("trades", "H1")] >= nmin) & (X[("trades", "H2")] >= nmin)]
        tt = trades[win & (trades["ss"] == j) & trades["sym"].isin(X.index)]
        g = tt.groupby("sym", observed=True)["net"].agg(["size", "mean"])
        S = pd.DataFrame({"setup_side": name, "symbol": g.index.astype(str), "trades": g["size"].to_numpy(int),
                          "net_bp": g["mean"].to_numpy(float) * 1e4,
                          "plain_net_bp": (sd * pm.reindex(g.index).to_numpy(float) - TRADE_COST) * 1e4})
        S["excess_bp"] = S["net_bp"] - S["plain_net_bp"]
        for c, h in (("excess_bp", "H1"), ("excess_bp", "H2"), ("net_bp", "H1"), ("net_bp", "H2")):
            S[f"{h}_{c}"] = X[(c, h)].reindex(g.index).to_numpy(float)
        out.append(S.sort_values(["excess_bp", "symbol"], ascending=[False, True]).head(int(CFG["shortlist_n"])))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


# ----------------------------------------------------------------------
# report
# ----------------------------------------------------------------------
def _f(x, d=1) -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"{x:+.{d}f}"


def _pct(x) -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:.0f}%"


def _p(x) -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"{x:.4f}"


def write_report(out: Path, R: pd.DataFrame, PL: pd.DataFrame, SL: pd.DataFrame, info: dict) -> None:
    passed = R[R["passes"]]
    L = ["# Stage 0 - persistent stock-specific intraday behaviour", "",
         f"{CODE_VERSION} | declaration {info['declaration']} | {info['at']} | costs {COST_BPS:.2f} bp round trip at Rs "
         f"{CFG['notional_rs']:,.0f} + slippage {CFG['slip_entry_bps']:.0f} bp entry, {CFG['slip_time_bps']:.0f} bp time exit "
         f"= {TRADE_COST * 1e4:.2f} bp a trade", ""]
    if info["rerun"]:
        L += [f"**RERUN** #{len(info['rerun']) + 1} of this declaration (earlier: {', '.join(info['rerun'])}): H1 and H2 were already "
              f"seen, so this run is NOT fresh evidence.", ""]
    if len(passed):
        L += [f"## VERDICT: PASS - persistent stock-specific behaviour in {', '.join(passed['setup_side'])}", "",
              "At least one setup-side passed the Holm-corrected permutation test AND its H1 top-decile stocks were positive "
              "after costs in H2. The shortlist below (2021-2024 only) is the candidate pool for the 10. This is in-sample: "
              "2025 onward is untouched and is the confirmation for a later stage.", ""]
    else:
        L += ["## VERDICT: no persistent stock-specific behaviour", "",
              f"No setup-side passed both legs (Holm-corrected permutation p <= {CFG['alpha']} AND the H1 top decile's H2 "
              f"interval above zero). Persistent on leg 1 alone: {', '.join(R.loc[R['leg1_persistent'], 'setup_side']) or 'none'}. "
              "Stop here.", ""]
    L += ["## Persistence per setup-side", "",
          "Excess = a stock's mean net per trade minus its own plain open-to-15:03 trade in the same direction (same half). "
          "rho = Spearman of H1 vs H2 excess across stocks with >= 30 trades in each half; p = one-sided permutation (stock "
          "labels shuffled, 10,000 times); Holm over 20 setup-sides. Top decile = best 10% of stocks by H1 excess; their H2 "
          "net (after costs) per trade-day with a 95% block-bootstrap interval. rho vs ATR: how much the H1 excess just tracks "
          "volatility.", "",
          "| setup-side | stocks | rho | perm p | Holm p | top-decile stocks | H2 trades | H2 win | H2 net bp/trade | H2 bp/trade-day [95%] | rho vs ATR | pass |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in R.iterrows():
        L.append(f"| {r['setup_side']} | {r['eligible_stocks']} | {_f(r['rho'], 3)} | {_p(r['perm_p'])} | {_p(r['holm_p'])} | "
                 f"{r['top_decile']} | {r['top_h2_trades']:,} | {_pct(r['top_h2_win'])} | "
                 f"{_f(r['top_h2_net_bp_trade'])} | {_f(r['top_h2_daily_bp'])} [{_f(r['top_h2_lo_bp'])}, {_f(r['top_h2_hi_bp'])}] | "
                 f"{_f(r['rho_with_atr'], 2)} | {'PASS' if r['passes'] else ('leg 1 only' if r['leg1_persistent'] else ('leg 2 only' if r['leg2_h2_positive'] else '-'))} |")
    L += ["", "## All stocks pooled (context, not a rule)", "", "| setup-side | H1 trades | H1 win | H1 net bp/trade | H2 trades | H2 win | H2 net bp/trade |",
          "|---|---|---|---|---|---|---|"]
    for name in SS:
        a = PL[(PL["setup_side"] == name) & (PL["half"] == "H1")]
        b = PL[(PL["setup_side"] == name) & (PL["half"] == "H2")]
        cell = lambda Z: (f"{int(Z['trades'].iloc[0]):,} | {Z['win'].iloc[0] * 100:.0f}% | {_f(Z['net_bp_trade'].iloc[0])}" if len(Z) else "0 | n/a | n/a")
        L.append(f"| {name} | {cell(a)} | {cell(b)} |")
    pr, pn = info["plain_rho"], info["plain_n"]
    cov = info["coverage"]
    L += ["", "## Context", "",
          f"- Plain open-to-15:03 long trade, H1 vs H2 per-stock Spearman: {_f(pr, 3)} over {pn} stocks (how much intraday drift "
          f"persists on its own; the excess removes it).",
          f"- Stocks with usable sessions: {cov['stocks_with_trades']:,} of {cov['liquid_stocks']:,} liquid equity stocks "
          f"({cov['liquid_no_bars']:,} liquid stock(s) without a 3-minute file).",
          f"- Liquid stock-days with a usable session (after reconciliation and the 80% rule): H1 {cov['usable_share_H1'] * 100:.1f}% of "
          f"{cov['liquid_days_H1']:,}; H2 {cov['usable_share_H2'] * 100:.1f}% of {cov['liquid_days_H2']:,}.",
          f"- Data checks in H1-H2: {cov['hygiene']['sessions_with_bars']:,} sessions with bars, {cov['hygiene']['failed_reconciliation']:,} "
          f"failed reconciliation, {cov['hygiene']['not_usable']:,} without a first bar or under 80% of bars, "
          f"{cov['hygiene']['unreadable_files']:,} unreadable files, {cov['hygiene']['basis_guard_days']:,} stock-days dropped by the 20% gap guard.",
          f"- Nothing after {CFG['h2_end']} was read into any number.", ""]
    if len(SL):
        L += ["## Shortlist (2021-10-01 to 2024-12-31 only)", "",
              "Top stocks per passing setup-side by pooled excess over both halves (>= 30 trades in each half).", "",
              "| setup-side | symbol | trades | net bp/trade | excess bp | H1 excess | H2 excess | H1 net | H2 net |", "|---|---|---|---|---|---|---|---|---|"]
        for _, r in SL.iterrows():
            L.append(f"| {r['setup_side']} | {r['symbol']} | {r['trades']} | {_f(r['net_bp'])} | {_f(r['excess_bp'])} | {_f(r['H1_excess_bp'])} | "
                     f"{_f(r['H2_excess_bp'])} | {_f(r['H1_net_bp'])} | {_f(r['H2_net_bp'])} |")
        L.append("")
    L += ["## Caveats", ""] + [f"- {x}" for x in DECL["limitations_stated_in_report"]] + [""]
    (out / "report.md").write_text("\n".join(L), encoding="utf-8")


# ----------------------------------------------------------------------
# the run
# ----------------------------------------------------------------------
def previous_runs(root: Path) -> List[str]:
    f = root / "panel" / "research_ledger.jsonl"
    out = []
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("family") == DECL["family_id"]:
                out.append(str(rec.get("run")))
    return out


def _sha_path(p) -> Optional[str]:
    try:
        return hashlib.sha256(Path(p).read_bytes()).hexdigest()[:16]
    except Exception:
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Stage 0: persistent stock-specific intraday behaviour (H1 vs H2, 20 setup-sides)")
    ap.add_argument("--root", required=True)
    a = ap.parse_args(argv)
    root = Path(a.root)
    if not root.is_dir():
        raise PreconditionError(f"--root {root} is not a folder - run 'call env_daily.bat' and pass --root %CACHE_DAILY_ROOT%")
    check_reuse()
    sha = hashlib.sha256(DECL_RAW).hexdigest()[:16]
    import data_quality as dq
    import intraday_cache as IC
    _, etf_set, _ = BM.read_lists(root)
    syms = BM.equity_symbols(root, dq, etf_set)
    if not syms:
        raise PreconditionError("no equity daily files found - check CACHE_DAILY_ROOT")
    prev = previous_runs(root)
    _log(f"{CODE_VERSION} (declaration {sha}): {len(syms):,} equity symbols; {len(SS)} setup-sides; H1 {CFG['h1_start']}..{CFG['h1_end']}, "
         f"H2 {CFG['h2_start']}..{CFG['h2_end']}; nothing after {CFG['h2_end']} is used")
    if prev:
        _log(f"  WARNING: RERUN #{len(prev) + 1} of {DECL['family_id']} (earlier: {', '.join(prev)}) - not fresh evidence")
    tol_p, tol_v = IC.DECL["reconcile_price_tol"], IC.DECL["reconcile_volume_tol"]
    end_ts = H2[1] + pd.Timedelta(days=1)
    hyg = {"sessions_with_bars": 0, "failed_reconciliation": 0, "not_usable": 0, "unreadable_files": 0, "basis_guard_days": 0}
    cov = {"liquid_stocks": 0, "liquid_no_bars": 0, "stocks_with_trades": 0, "liquid_days_H1": 0, "liquid_days_H2": 0, "usable_H1": 0, "usable_H2": 0}
    T_all, P_all = [], []
    for i, s in enumerate(syms):
        try:
            daily = pd.read_parquet(Path(dq._paths(root, s)[0]), columns=["timestamp", "open", "high", "low", "close", "volume"])
        except Exception:
            continue
        daily = daily[(BM.SI._naive_days(daily["timestamp"]) < end_ts).to_numpy()].reset_index(drop=True)   # the cutoff, first
        if len(daily) < 2:
            continue
        F = BM.daily_features(daily)
        liq_days = BM.liquid_ok(F)
        hl = half_of(F["day"])
        lq = liq_days & (hl != "")
        if not lq.any():
            continue
        cov["liquid_stocks"] += 1
        n1, n2 = int((lq & (hl == "H1")).sum()), int((lq & (hl == "H2")).sum())
        cov["liquid_days_H1"] += n1
        cov["liquid_days_H2"] += n2
        f = IC.store(root) / f"{s}_{IC.BAR_MIN}m.parquet"
        if not f.exists():
            cov["liquid_no_bars"] += 1
            continue
        try:
            X = pd.read_parquet(f)
            X = X.assign(timestamp=BM.ist_naive(X["timestamp"]).to_numpy())
            X = X[(X["timestamp"] < end_ts) & (X["timestamp"] >= H1[0])].reset_index(drop=True)              # the cutoff, first
            J = IC.reconcile_symbol(X, daily, tol_p, tol_v) if len(X) else pd.DataFrame()
        except Exception as e:                                       # one unreadable file must not stop the study
            hyg["unreadable_files"] += 1
            _log(f"  WARNING {s}: 3-minute file not usable ({type(e).__name__}: {e}) - skipped")
            continue
        if not len(J):
            continue
        jd = BM.ist_naive(pd.to_datetime(J["day"])).dt.normalize()
        okc = J["ok"].eq(True).to_numpy()
        hyg["sessions_with_bars"] += int(len(J))
        hyg["failed_reconciliation"] += int((~okc).sum())
        X = X[X["timestamp"].dt.normalize().isin(pd.DatetimeIndex(jd[okc]))]
        days, B = BM.bar_matrix(X)
        if not len(days):
            continue
        cx_use = BM.usable_sessions(B)
        hyg["not_usable"] += int((~cx_use).sum())
        uday = pd.DatetimeIndex(days[cx_use])
        dl = pd.DatetimeIndex(F.loc[lq, "day"])
        hit = dl.isin(uday)
        hd = half_of(dl)
        cov["usable_H1"] += int((hit & (hd == "H1")).sum())
        cov["usable_H2"] += int((hit & (hd == "H2")).sum())
        T, P = stock_trades(F, days, B, liq_days, hyg)
        if len(P):
            cov["stocks_with_trades"] += 1
            T_all.append(T.assign(sym=s))
            P_all.append(P.assign(sym=s))
        if (i + 1) % 100 == 0:
            _log(f"  {i + 1:,}/{len(syms):,} symbols")
    if not P_all:
        raise PreconditionError("no usable liquid stock-days in H1/H2 - check the 3-minute data")
    trades = pd.concat(T_all, ignore_index=True)
    plain = pd.concat(P_all, ignore_index=True)
    trades["sym"], plain["sym"] = trades["sym"].astype("category"), plain["sym"].astype("category")
    cov["usable_share_H1"] = cov["usable_H1"] / cov["liquid_days_H1"] if cov["liquid_days_H1"] else float("nan")
    cov["usable_share_H2"] = cov["usable_H2"] / cov["liquid_days_H2"] if cov["liquid_days_H2"] else float("nan")
    cov["hygiene"] = hyg
    _log(f"  {len(trades):,} trades over {cov['stocks_with_trades']:,} stocks; usable share H1 {cov['usable_share_H1'] * 100:.1f}%, "
         f"H2 {cov['usable_share_H2'] * 100:.1f}%")
    out, R, SL = run_and_write(root, trades, plain, sha, cov, prev)
    passed = list(R.loc[R["passes"], "setup_side"])
    led = BM.write_ledger(root, {"kind": "screen", "tool": CODE_VERSION, "family": DECL["family_id"], "declaration": sha, "run": out.name,
                                 "trials": len(SS), "periods": {"H1": [CFG["h1_start"], CFG["h1_end"]], "H2": [CFG["h2_start"], CFG["h2_end"]]},
                                 "post_2024_used": False, "fresh": not prev, "previous_runs": prev,
                                 "verdict": "PASS" if passed else "no persistent stock-specific behaviour", "passing": passed,
                                 "leg1_only": list(R.loc[R["leg1_persistent"] & ~R["passes"], "setup_side"]),
                                 "shortlist": SL[["setup_side", "symbol"]].to_dict("records") if len(SL) else []})
    _log(f"VERDICT: {'PASS - ' + ', '.join(passed) if passed else 'no persistent stock-specific behaviour'}")
    print(f"  report: {out / 'report.md'}")
    print(f"  research ledger: {led}")
    return 0


def run_and_write(root: Path, trades: pd.DataFrame, plain: pd.DataFrame, sha: str, cov: dict, prev: List[str]):
    """Statistics and outputs (everything after the per-stock pass) - one folder under <root>\\research2\\stage0\\."""
    ps = per_stock(trades, plain)
    R = persistence(ps, trades)
    PL = pooled(ps)
    SL = shortlist(R, ps, trades, plain)
    pr, pn = plain_persistence(plain)
    base = root / "research2" / "stage0"
    base.mkdir(parents=True, exist_ok=True)
    day = dt.date.today().strftime("%Y%m%d")
    k = 1
    while (base / f"S0_{day}_{k:03d}").exists():
        k += 1
    out = base / f"S0_{day}_{k:03d}"
    out.mkdir()
    info = {"declaration": sha, "at": f"{dt.datetime.now():%Y-%m-%d %H:%M}", "rerun": prev, "plain_rho": pr, "plain_n": pn, "coverage": cov}
    write_report(out, R, PL, SL, info)
    R.to_csv(out / "persistence.csv", index=False)
    ps.rename(columns={"sym": "symbol"})[["setup_side", "symbol", "half", "trades", "net_bp", "win", "plain_days", "plain_net_bp", "excess_bp",
                                           "atr_mean"]].to_csv(out / "per_stock.csv", index=False)
    PL.to_csv(out / "pooled.csv", index=False)
    if len(SL):
        SL.to_csv(out / "shortlist.csv", index=False)
    passed = list(R.loc[R["passes"], "setup_side"])
    summ = {"tool": CODE_VERSION, "declaration": sha, "verdict": "PASS" if passed else "no persistent stock-specific behaviour",
            "passing": passed, "rerun_of": prev, "cost_bps_per_trade": TRADE_COST * 1e4, "coverage": cov,
            "plain_persistence": {"rho": pr, "stocks": pn}, "persistence": json.loads(R.to_json(orient="records"))}
    (out / "summary.json").write_text(json.dumps(summ, indent=2, default=str), encoding="utf-8")
    h = hashlib.sha256()
    h.update(pd.util.hash_pandas_object(trades[["day", "ss", "sig", "ent", "entry", "gross"]], index=False).to_numpy().tobytes())
    h.update(pd.util.hash_pandas_object(trades["sym"].astype(str), index=False).to_numpy().tobytes())
    try:
        import pyarrow
        pa_v = pyarrow.__version__
    except Exception:
        pa_v = None
    prov = {"tool": CODE_VERSION, "declaration": sha, "data_fingerprint": h.hexdigest()[:16],
            "code_sha256_16": {"stage0_persistence.py": _sha_path(Path(__file__)), "bigmove_study.py": _sha_path(BM.__file__)},
            "python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__, "pyarrow": pa_v,
            "platform": platform.platform(), "seed": CFG["seed"], "permutations": CFG["permutations"]}
    BM.seal_outputs(out, prov)
    return out, R, SL


if __name__ == "__main__":
    sys.exit(main())
