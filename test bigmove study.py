#!/usr/bin/env python3
"""
tests/test_bigmove_study.py - bigmove_study v1.1. Prints VERIFIED on success.

 1. By hand: costs (the research's worked examples to the rupee), net returns by exit kind and slippage multiplier,
    bar slots, usable sessions, breakout fills (trigger, gap-through entry, same-bar stop, gap-through stop, time exit
    with a missing bar, short mirror, no trigger, entry window), VWAP trail, breakeven, gate arming (decided at the
    previous bar's close only), relative volume, the move memory (nearest days and their next-session range), sector
    peers without the stock itself, beta, the verdict rules (incl. beating the plain book and surviving the search),
    DSR, BH, Reality Check and max-t p-values (by hand in plain loops). Audit flags (same-bar stop, missing bar inside
    the trade, triggered without an exit price). FILL FAIRNESS: on 200,000 sessions of a continuous driftless price
    path, no stop / exit combination earns a positive mean before costs (a fill that peeks inside the bar would). GATE
    WIRING through stock_rows: each gate (NIFTY, sector, RS, NIFTY + RS) fills exactly one bar after its condition first
    holds at a bar close, long and short.
 1b. Statistics by simulation: block-bootstrap coverage and one-sided p on autocorrelated fat-tailed series; Reality
    Check false alarms; deflated Sharpe on noise and its power; SELECTION - the best of 36 rankings that add nothing,
    judged on its own excess vs against the search (max-t), and the power to find a real ranking.
 1c. The synthetic world: reproducible from its seed; switching one mechanism leaves every other random number alone.
 2. PLANTED worlds (bars of a continuous path; selection uses top 3 / 6):
      stocks in play          -> RV books CHAMPION both sides; the blind MFE book does not beat the plain book;
                                 flipping the sign of every confirmation outcome leaves every selection unchanged
      state-driven moves      -> the MFE book beats the RV book; RVxMFE beats RV
      payoff needs both       -> RVxMFE beats RV and MFE, both sides, both windows (H2 planted)
      (Not tested: two effects on DIFFERENT stock-days. The product is an AND; there it may beat one score or neither,
      depending on the effect sizes and N - the first suite asserted it beats both, and that was wrong.)
      short-only catalysts    -> BIGMOVE-S wins, BIGMOVE-L does not
      NIFTY trend days        -> the NIFTY gate adds (the stocks' own opening hides the direction); a ranked cell's
                                 variants must also beat the same variant on matched PLAIN
      NIFTY vs sectors        -> sectors trend against NIFTY: the sector gate adds, the NIFTY gate hurts
      sector trend days       -> the sector gate adds; the NIFTY gate does not
      stock-only trend days   -> neither gate adds (null for the gates)
    NULL worlds: nothing earns PROMISING or CHAMPION and no RVxMFE comparison adds, with costs; with zero costs no
    CHAMPION and the Reality Check stays quiet. Thin counter-trend days: full PLAIN would credit a random ranking with
    skill; the matched book does not.
 3. LOOK-AHEAD, 12 decision days x 2 opening ranges: changing the day's daily bar (alternately shrunk to one price and
    blown up), its bars after the opening range and every later day leaves the day's RV, direction, memory, ATR and
    beta unchanged, while its outcomes do change (the perturbation is not empty); changing only later days leaves
    every earlier row identical, outcomes included. Planted leaks (memory using the day's own range; beta using the
    day's own return) are caught.
 4. main() end to end with stand-in modules: coverage report and missing_liquid.txt; refusal below 90% coverage;
    --allow-partial-universe run writes every output; NIFTY 3-minute file under its spaced name; sector files used
    (the sector gate runs); an ETF found by its INF ISIN is excluded; the trade file has one set of stop-free columns;
    the whole-session data checks are counted; provenance in summary.json and a hash of every output; universe by month.
 4b. Zone-aware (Asia/Kolkata) files end to end; an unreadable file is skipped and counted; a second run of the same
    declaration is stamped RERUN.
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
import types
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import bigmove_study as BM              # noqa: E402
import bigmove_world as WW               # noqa: E402

FAILS = []
BM.CFG["top_n"] = [3, 6]                # small test worlds: selection must be selective


def check(cond, msg):
    print(("  ok  " if cond else "  FAIL") + f"  {msg}")
    if not cond:
        FAILS.append(msg)


def same(a, b) -> bool:
    a, b = np.asarray(a, float), np.asarray(b, float)
    return a.shape == b.shape and bool(np.all((np.isnan(a) & np.isnan(b)) | (np.abs(a - b) <= 1e-9 * np.maximum(1.0, np.abs(a)))))


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def day_bars(o, h, l, c, v=None):
    """One session's matrices (1 x 125) from per-bar lists (missing bars as NaN)."""
    B = {k: np.asarray(x, float)[None, :] for k, x in (("open", o), ("high", h), ("low", l), ("close", c))}
    B["volume"] = (np.full((1, BM.NB), 1000.0) if v is None else np.asarray(v, float)[None, :])
    return B


def flat_day(p=100.0):
    o = np.full(BM.NB, p)
    return o.copy(), o.copy() + 0.05, o.copy() - 0.05, o.copy()


def run_world(w):
    """The study's passes on a synthetic world (sector paths when the world has sectors), as main() runs them."""
    cands, cal, sleeve = build_world(w)
    return BM.run_books(cands, cal, sleeve)


def build_world(w):
    """Candidates, calendar and NIFTY sleeve of a synthetic world (passes 0 and 1)."""
    nd = w["nifty_daily"].copy()
    nd["day"] = BM.SI._naive_days(nd["timestamp"]).to_numpy()
    nifty = BM.nifty_context(w["nifty_bars"])
    sec = w.get("sector_of") or {}
    t0 = w["intra"]["S000"]["timestamp"].min().normalize()
    cal = np.array(sorted(set(pd.DatetimeIndex(w["days"][w["days"] >= t0]))), dtype="datetime64[ns]")
    feats = {s: BM.daily_features(D) for s, D in w["daily"].items()}
    bars = {s: BM.bar_matrix(w["intra"][s]) for s in w["daily"]}
    sp = None
    if sec:
        sp = BM.SectorPaths(cal, list(sec.values()))
        for s in feats:
            if s in sec:
                sp.add(sec[s], *BM.sector_sessions(feats[s], *bars[s], BM.liquid_ok(feats[s])))
    parts = {1: [], 2: []}
    for s, F in feats.items():
        days, B = bars[s]
        for r, df in BM.stock_rows(s, F, days, B, BM.liquid_ok(F), nifty, BM.beta_series(F, nd), sec.get(s), sp).items():
            parts[r].append(df)
    cands = {r: BM.add_scores(pd.concat(v, ignore_index=True)) for r, v in parts.items() if v}
    return cands, cal, BM.nifty_sleeve(w["nifty_bars"], nd, cal)


def pick(res, side, label):
    S = res["selected"]
    return S[(S["side"] == side) & (S["pick"] == label)].iloc[0]


def pooled(res, side, vs):
    C = res["comparison"]
    return C[(C["side"] == side) & (C["vs"] == vs) & (C["or_bars"] == "pooled")].iloc[0]


def gate(res, side, variant):
    V = res["variants"]
    return V[(V["side"] == side) & (V["variant"] == variant)].iloc[0]


# ----------------------------------------------------------------------
# 1. by hand
# ----------------------------------------------------------------------
def by_hand():
    print("1. by hand")
    rs = lambda n, f: f(n) * n / 1e4
    check(abs(rs(1e6, BM.cash_cost_bps) - 402.01) < 0.01 and abs(rs(1e5, BM.cash_cost_bps) - 82.68) < 0.01
          and abs(rs(16.25e5, BM.fut_cost_bps) - 966.22) < 0.01,
          f"costs: cash Rs 10 lakh {rs(1e6, BM.cash_cost_bps):.2f}, Rs 1 lakh {rs(1e5, BM.cash_cost_bps):.2f}, NIFTY lot {rs(16.25e5, BM.fut_cost_bps):.2f} "
          f"(the research's worked examples: 402, 83, 966)")
    n = BM.net_return(np.array([0.01, 0.01, 0.01, np.nan]), np.array([BM.KIND_STOP, BM.KIND_TIME, BM.KIND_TRAIL, BM.KIND_NONE]), 2.0)
    want = [0.01 - (2 * (5 + 5) + BM.COST_BPS) / 1e4, 0.01 - (2 * (5 + 3) + BM.COST_BPS) / 1e4, 0.01 - (2 * (5 + 3) + BM.COST_BPS) / 1e4, 0.0]
    check(same(n, want), "net return: stop exits pay 5+5 bp slippage, time and trail 5+3, x multiplier, plus costs; no trade = 0")

    ts = pd.to_datetime(["2025-01-02 09:15", "2025-01-02 09:18", "2025-01-02 15:27", "2025-01-02 15:30", "2025-01-03 09:21"])
    X = pd.DataFrame({"timestamp": ts, "open": [1, 2, 3, 4, 5.0], "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0})
    days, B = BM.bar_matrix(X)
    check(len(days) == 2 and B["open"][0, 0] == 1 and B["open"][0, 1] == 2 and B["open"][0, 124] == 3 and B["open"][1, 2] == 5
          and np.isnan(B["open"][1, 0]) and np.isfinite(B["open"]).sum() == 4,
          "bar slots: 09:15 -> 0, 09:18 -> 1, 15:27 -> 124; 15:30 dropped; one matrix row per session")
    check(not BM.usable_sessions(B).any(), "a session without its first bar, or with under 80% of bars, is not usable")

    M = np.array([[False, True, True], [False, False, False], [True, False, True]])
    check(list(BM.first_true(M, 0, 2)) == [1, -1, 0] and list(BM.first_true(M, np.array([2, 0, 1]), 2)) == [2, -1, 2],
          "first_true: the first True column inside [lo, hi] per row")

    o, h, l, c = flat_day()
    o[0], h[0], l[0], c[0] = 100.0, 101.0, 99.5, 100.8          # opening bar up: long candidate, level 101, range stop 99.5
    o[3], h[3], l[3], c[3] = 100.9, 101.5, 100.85, 101.4        # breaks out in bar 3
    o[4:], h[4:], l[4:], c[4:] = 102.0, 102.2, 101.8, 102.0
    o[BM.X_BAR] = 103.0
    B = day_bars(o, h, l, c)
    atr = np.array([0.02])
    R = BM.orb_fills(B, np.array([1]), 1, "range", atr)
    check(R["entry_bar"][0] == 3 and abs(R["entry"][0] - 101.0) < 1e-12 and R["kind"][0] == BM.KIND_TIME and R["exit_bar"][0] == BM.X_BAR
          and abs(R["gross"][0] - (103 / 101 - 1)) < 1e-12 and abs(R["risk_bps"][0] - (101 - 99.5) / 101 * 1e4) < 1e-9,
          "long breakout: stop order at the opening-range high fills at 101 in bar 3; time exit at the 15:03 open")
    o2 = o.copy()
    o2[3], h[3] = 101.6, 101.8
    R = BM.orb_fills(day_bars(o2, h, l, c), np.array([1]), 1, "range", atr)
    check(abs(R["entry"][0] - 101.6) < 1e-12, "a bar that opens above the level fills at its open (gap through the stop order)")
    l2 = l.copy()
    l2[3] = 100.0
    R = BM.orb_fills(day_bars(o, h, l2, c), np.array([1]), 1, 0.25, atr)
    stop = 101.0 * (1 - 0.25 * 0.02)
    check(R["kind"][0] == BM.KIND_STOP and R["exit_bar"][0] == 3 and abs(R["gross"][0] - (stop / 101 - 1)) < 1e-12,
          "the fill bar also reaches the 0.25 ATR stop: stopped in that bar at the stop price (conservative)")
    R0 = BM.orb_fills(day_bars(o, h, l, c), np.array([1]), 1, "range", atr)
    og, hg, lg, cg = o.copy(), h.copy(), l.copy(), c.copy()
    og[50] = hg[50] = lg[50] = cg[50] = np.nan                                   # a missing bar inside the trade
    Rg = BM.orb_fills(day_bars(og, hg, lg, cg), np.array([1]), 1, "range", atr)
    og2, hg2, lg2, cg2 = o.copy(), h.copy(), l.copy(), c.copy()
    og2[BM.X_BAR + 2] = hg2[BM.X_BAR + 2] = lg2[BM.X_BAR + 2] = cg2[BM.X_BAR + 2] = np.nan   # missing after the exit: harmless
    Rg2 = BM.orb_fills(day_bars(og2, hg2, lg2, cg2), np.array([1]), 1, "range", atr)
    Rn = BM.orb_fills(day_bars(o, h, l, c), np.array([1]), 1, "range", atr, px_time=np.array([np.nan]))
    check(R["same_bar_stop"][0] and not R0["same_bar_stop"][0] and Rg["gap_in_trade"][0] and not Rg2["gap_in_trade"][0]
          and not R0["gap_in_trade"][0] and Rn["no_exit_price"][0] and Rn["kind"][0] == BM.KIND_NONE and not R0["no_exit_price"][0],
          "audit flags: stopped inside the entry bar; a missing bar inside the trade (not one after the exit); a triggered trade "
          "without an exit price is flagged instead of vanishing")
    o3, l3 = o.copy(), l.copy()
    o3[50], l3[50] = 99.0, 98.8
    R = BM.orb_fills(day_bars(o3, h, l3, c), np.array([1]), 1, "range", atr)
    check(R["kind"][0] == BM.KIND_STOP and R["exit_bar"][0] == 50 and abs(R["gross"][0] - (99.0 / 101 - 1)) < 1e-12,
          "a later bar opening below the stop fills at its open (gap through the stop)")
    o4 = o.copy()
    o4[BM.X_BAR] = np.nan
    o4[BM.X_BAR + 1] = 104.0
    R = BM.orb_fills(day_bars(o4, h, l, c), np.array([1]), 1, "range", atr)
    o5 = o.copy()
    o5[BM.X_BAR:] = np.nan
    c5 = c.copy()
    c5[BM.X_BAR - 1] = 101.9
    R5 = BM.orb_fills(day_bars(o5, h, l, c5), np.array([1]), 1, "range", atr)
    check(abs(R["gross"][0] - (104 / 101 - 1)) < 1e-12 and abs(R5["gross"][0] - (101.9 / 101 - 1)) < 1e-12,
          "a missing 15:03 bar exits at the next open; with none left, at the last close before it")
    so, sh, sl, sc = flat_day()
    so[0], sh[0], sl[0], sc[0] = 100.0, 100.4, 99.0, 99.2         # opening bar down: short, level 99.0, range stop 100.4
    so[2], sh[2], sl[2], sc[2] = 99.1, 99.15, 98.7, 98.8
    so[3:], sh[3:], sl[3:], sc[3:] = 98.0, 98.2, 97.8, 98.0
    so[BM.X_BAR] = 97.0
    R = BM.orb_fills(day_bars(so, sh, sl, sc), np.array([-1]), 1, "range", atr)
    check(R["entry_bar"][0] == 2 and abs(R["entry"][0] - 99.0) < 1e-12 and abs(R["gross"][0] - (1 - 97.0 / 99.0)) < 1e-12,
          "short mirror: sell stop at the opening-range low, return = 1 - exit / entry")
    no, nh, nl, nc = flat_day()
    no[0], nh[0], nl[0], nc[0] = 100.0, 100.3, 99.7, 100.1                  # later bars (high 100.05) never reach 100.3
    R = BM.orb_fills(day_bars(no, nh, nl, nc), np.array([1]), 1, "range", atr)
    check(R["kind"][0] == BM.KIND_NONE and np.isnan(R["gross"][0]), "no breakout: no trade, no return")
    R = BM.orb_fills(day_bars(*flat_day()), np.array([1]), 1, "range", atr)
    check(R["entry_bar"][0] == 1 and abs(R["entry"][0] - 100.05) < 1e-12,
          "a bar whose high only touches the level fills there (a stop order triggers on a touch)")
    o6, h6, l6, c6 = flat_day()
    o6[0], h6[0], l6[0], c6[0] = 100.0, 101.0, 99.5, 100.8
    h6[BM.E_LAST + 1] = 102.0
    R = BM.orb_fills(day_bars(o6, h6, l6, c6), np.array([1]), 1, "range", atr)
    h6[BM.E_LAST] = 102.0
    R2 = BM.orb_fills(day_bars(o6, h6, l6, c6), np.array([1]), 1, "range", atr)
    check(R["kind"][0] == BM.KIND_NONE and R2["entry_bar"][0] == BM.E_LAST, "orders live until the bar starting 14:30, not after")
    allowed = np.ones((1, BM.NB), bool)
    allowed[0, 3] = False
    R = BM.orb_fills(B, np.array([1]), 1, "range", atr, allowed=allowed)
    check(R["entry_bar"][0] == 4 and abs(R["entry"][0] - 102.0) < 1e-12, "a gate that is not armed in bar 3 delays the fill to bar 4's open")

    ov, hv, lv, cv = o.copy(), h.copy(), l.copy(), c.copy()
    vv = np.full(BM.NB, 1000.0)
    cv[20] = 100.5                                               # closes below the session VWAP
    lv[20] = 100.4
    vw = BM.session_vwap(*(day_bars(ov, hv, lv, cv, vv)[k] for k in ("high", "low", "close", "volume")))
    Bv = day_bars(ov, hv, lv, cv, vv)
    R = BM.orb_fills(Bv, np.array([1]), 1, "range", atr, exit_mode="vwap", vwap=vw)
    first_below = int(np.flatnonzero(cv[3:BM.X_BAR - 1] < vw[0, 3:BM.X_BAR - 1])[0]) + 3
    check(R["kind"][0] == BM.KIND_TRAIL and R["exit_bar"][0] == first_below + 1 and abs(R["gross"][0] - (ov[first_below + 1] / 101 - 1)) < 1e-12,
          f"VWAP trail: the first close below VWAP (bar {first_below}) exits at the next open")
    ob, hb, lb, cb = o.copy(), h.copy(), l.copy(), c.copy()
    hb[10] = 102.6                                              # +1R = 101 + 1.5 = 102.5 reached in bar 10
    lb[30], ob[30] = 100.9, 101.2                               # later back to the entry
    R = BM.orb_fills(day_bars(ob, hb, lb, cb), np.array([1]), 1, "range", atr, exit_mode="be")
    check(R["kind"][0] == BM.KIND_STOP and R["exit_bar"][0] == 30 and abs(R["gross"][0]) < 1e-12,
          "breakeven: after +1R the stop moves to the entry; a later dip to it exits flat")

    # relative volume and direction, through stock_rows
    w = WW.make_world(n=2, seed=3, start="2024-01-01", bar_start="2024-03-01", end="2024-06-28")
    s = "S000"
    F = BM.daily_features(w["daily"][s])
    days, B = BM.bar_matrix(w["intra"][s])
    out = BM.stock_rows(s, F, days, B, np.ones(len(F), bool), {}, np.full(len(F), np.nan), memory_fn=lambda F_, rows: np.full(len(rows), 0.02))
    C1 = out[1]
    v0 = B["volume"][:, 0]
    k = int(np.flatnonzero(days == C1["day"].iloc[5])[0])
    rv = v0[k] / v0[k - 14:k].mean()
    dirn = np.sign(B["close"][k, 0] - B["open"][k, 0])
    check(abs(C1["rv"].iloc[5] - rv) < 1e-9 and C1["side"].iloc[5] == dirn and (C1["rv"] >= 1).all(),
          "relative volume = first-bar volume / mean of the previous 14 sessions; side = first bar's direction; RV >= 1 kept")

    # the memory by hand: two features matter, k = 2, apart = 1
    n_ = 12
    G = pd.DataFrame({"day": pd.bdate_range("2024-01-01", periods=n_)})
    for f in BM.FEATURES:
        G[f] = np.nan
    G["mom5"] = [5, 1, 9, 2, 8, 3, 7, 4, 6, 10, 0.5, 8.5]
    G["rsi14"] = [5, 1, 9, 2, 8, 3, 7, 4, 6, 10, 0.5, 8.5]
    G["atr14"] = 0.02
    G["rr"] = np.arange(n_, dtype=float)
    Z = G[BM.FEATURES].expanding(min_periods=1).rank(pct=True).to_numpy(float)
    q = 11
    d2 = BM.SI.nan_dist(Z[q], Z[:q - 1])
    near = np.argsort(d2, kind="stable")[:2]
    got = BM.move_memory(G, np.array([12 - 0]), k=2, apart=1, min_hist=3) if False else BM.move_memory(G.iloc[:12], np.array([11]), k=2, apart=1, min_hist=3)
    q = 10
    d2 = BM.SI.nan_dist(Z[q], Z[:q])
    near = np.argsort(d2, kind="stable")[:2]
    check(abs(got[0] - 0.02 * np.median(G["rr"].to_numpy()[near])) < 1e-12,
          f"memory: ATR x median next-session range of the 2 nearest earlier days {sorted(near.tolist())} (candidates end 2 sessions back)")

    # sector peers exclude the stock itself
    cal = np.array(pd.bdate_range("2025-01-01", periods=3), dtype="datetime64[ns]")
    sp = BM.SectorPaths(cal, ["IT"])
    PA, PB = np.full((1, BM.NB), 0.01), np.full((1, BM.NB), 0.03)
    sp.add("IT", cal[:1], PA)
    sp.add("IT", cal[:1], PB)
    peerA = sp.peers("IT", cal[:1], PA, np.array([True]))
    peerX = sp.peers("IT", cal[:1], np.full((1, BM.NB), 0.5), np.array([False]))
    check(same(peerA[0, :3], [0.03] * 3) and same(peerX[0, :3], [0.02] * 3), "sector peers: the stock's own path is removed; an outsider sees the full average")

    nd = WW.make_world(n=1, seed=4, start="2023-01-02", bar_start="2023-12-01", end="2023-12-29")["nifty_daily"]
    nd["day"] = BM.SI._naive_days(nd["timestamp"]).to_numpy()
    lr = np.log(nd["close"]).diff().fillna(0).to_numpy()
    sd = nd.copy()
    sd["close"] = 500 * np.exp(np.cumsum(1.5 * lr + 0.001 * np.random.default_rng(1).standard_normal(len(lr))))
    sd["open"], sd["high"], sd["low"], sd["volume"] = sd["close"], sd["close"] * 1.01, sd["close"] * 0.99, 1e6
    bt = BM.beta_series(BM.daily_features(sd[["timestamp", "open", "high", "low", "close", "volume"]]), nd)
    check(abs(bt[-1] - 1.5) < 0.05, f"beta of a 1.5x stock: {bt[-1]:.3f}")

    d_ok = {"lo_bp": 1.0, "mean_bp": 2.0, "mean_bp_x1.5": 1.0, "sharpe": 2.0, "excess_bp": 1.0, "excess_lo_bp": 0.5, "excess_padj": 0.01}
    c_ok = {"mean_bp": 2.0, "sharpe": 1.5, "mean_bp_x1.5": 1.0, "excess_bp": 0.5}
    pmax = float(BM.CFG["excess_padj_max"])
    check(BM.verdict(d_ok, c_ok, 0.97, ranked=True) == "CHAMPION" and BM.verdict(d_ok, c_ok, 0.90, ranked=True) == "PROMISING"
          and BM.verdict(d_ok, {**c_ok, "excess_bp": -0.1}, 0.97, ranked=True) == "WATCH"
          and BM.verdict(d_ok, {**c_ok, "excess_bp": -0.1}, 0.97, ranked=False) == "CHAMPION"
          and BM.verdict(d_ok, {**c_ok, "sharpe": 0.9}, 0.97, ranked=True) == "PROMISING"
          and BM.verdict({**d_ok, "excess_lo_bp": -0.5}, c_ok, 0.97, ranked=True) == "WATCH"
          and BM.verdict({**d_ok, "excess_lo_bp": -0.5}, c_ok, 0.97, ranked=False) == "CHAMPION"
          and BM.verdict({**d_ok, "excess_padj": pmax}, c_ok, 0.97, ranked=True) == "WATCH"
          and BM.verdict({**d_ok, "excess_padj": pmax - 1e-9}, c_ok, 0.97, ranked=True) == "CHAMPION"
          and BM.verdict({**d_ok, "excess_padj": np.nan}, c_ok, 0.97, ranked=True) == "WATCH"
          and BM.verdict({k_: v_ for k_, v_ in d_ok.items() if k_ != "excess_padj"}, c_ok, 0.97, ranked=True) == "WATCH"
          and BM.verdict({**d_ok, "excess_padj": 0.5}, c_ok, 0.97, ranked=False) == "CHAMPION"
          and BM.verdict({**d_ok, "lo_bp": -1}, {**c_ok, "mean_bp": -1}, 0.5) == "WATCH"
          and BM.verdict({"mean_bp": -1, "lo_bp": -2}, {"mean_bp": -1}, 0.1) == "DEAD",
          f"verdicts: CHAMPION needs DSR, half the Sharpe kept and stress; a ranked book must beat plain, and its excess must survive "
          f"the search (p below {pmax}; missing = not passed); WATCH / DEAD below")

    x = np.random.default_rng(5).normal(0.001, 0.01, 500)
    sr = x.mean() / x.std(ddof=1)
    z = (x - x.mean()) / x.std(ddof=1)
    g3, g4 = (z ** 3).mean(), (z ** 4).mean()
    tr = np.array([0.5, 1.0, 1.5, 2.0])
    from statistics import NormalDist
    nd_ = NormalDist()
    v = (tr / np.sqrt(250)).var(ddof=1)
    sr0 = np.sqrt(v) * ((1 - 0.5772156649) * nd_.inv_cdf(1 - 1 / 4) + 0.5772156649 * nd_.inv_cdf(1 - 1 / (4 * np.e)))
    want = nd_.cdf((sr - sr0) * np.sqrt(499) / np.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2))
    check(abs(BM.deflated_sharpe(x, tr, 4) - want) < 1e-12, f"deflated Sharpe by hand: {want:.4f}")
    check(list(BM.bh(np.array([0.001, 0.04, 0.03, 0.5, np.nan]), 0.10)) == [True, True, True, False, False], "Benjamini-Hochberg by hand")
    rng = np.random.default_rng(6)
    idx = BM._block_idx(400, 1000, 10, rng)
    Mnull = rng.normal(0, 0.01, (400, 20))
    Mplant = Mnull.copy()
    Mplant[:, 3] += 0.004
    check(BM.reality_check(Mnull, idx) > 0.05 and BM.reality_check(Mplant, idx) < 0.01,
          f"Reality Check: 20 pure-noise books p {BM.reality_check(Mnull, idx):.2f}; one real book among them p {BM.reality_check(Mplant, idx):.3f}")
    # max-t p-values by hand (plain loops) on a small case; the Reality Check is their smallest; books that never differ -> n/a
    Ms, ids = rng.normal(0, 0.01, (60, 4)), BM._block_idx(60, 50, 10, np.random.default_rng(9))
    Ms[:, 1] += 0.004
    Ms[:, 3] = 0.0                                                # a book that never trades: cannot be judged
    m_ = Ms.mean(0)
    mb_ = np.array([[Ms[i_, j_].mean() for j_ in range(4)] for i_ in ids])
    se_ = mb_.std(0, ddof=1)
    want = []
    for j_ in range(4):
        if not se_[j_] > 0:
            want.append(np.nan)
            continue
        cnt = sum(max((mb_[b_, q_] - m_[q_]) / se_[q_] for q_ in range(4) if se_[q_] > 0) >= m_[j_] / se_[j_] for b_ in range(len(ids)))
        want.append((1 + cnt) / (1 + len(ids)))
    got = BM.max_t_pvalues(Ms, ids)
    check(same(got, want) and got[1] < got[0] and np.isclose(BM.reality_check(Ms, ids), np.nanmin(want))
          and np.isnan(BM.reality_check(np.zeros((60, 3)), ids)) and np.isnan(BM.max_t_pvalues(Ms[:15], ids[:, :15] % 15)).all(),
          f"max-t p-values by hand: {', '.join('n/a' if not np.isfinite(x_) else f'{x_:.3f}' for x_ in got)} (the planted book "
          f"smallest; a book that never trades n/a); the Reality Check is the smallest; books that never differ give n/a (the old code "
          f"gave p = 1/(B+1), a false 'significant')")

    # fill fairness: a continuous driftless path (each bar's high / low = the max / min of a Brownian bridge between its
    # open and close). Any entry / exit rule that only uses what has traded has a mean P&L of zero there before costs;
    # the conservative same-bar stop makes it slightly negative. A fill that peeks inside the bar would show a plus.
    # 200,000 sessions in chunks; every cell is tested on its own.
    rng = np.random.default_rng(13)
    sb = 0.036 / np.sqrt(BM.NB) * 100
    acc = {}
    for _chunk in range(10):
        Dn = 20000
        Cm = 100 + np.cumsum(rng.normal(0, sb, (Dn, BM.NB)), 1)
        Om = np.c_[np.full(Dn, 100.0), Cm[:, :-1]]
        Hm = (Om + Cm + np.sqrt((Cm - Om) ** 2 - 2 * sb * sb * np.log(1 - rng.random((Dn, BM.NB))))) / 2
        Lm = (Om + Cm - np.sqrt((Cm - Om) ** 2 - 2 * sb * sb * np.log(1 - rng.random((Dn, BM.NB))))) / 2
        Bm = {"open": Om, "high": Hm, "low": Lm, "close": Cm, "volume": np.ones((Dn, BM.NB))}
        sdm = np.where(Cm[:, 0] > Om[:, 0], 1, -1)
        vwm = BM.session_vwap(Hm, Lm, Cm, Bm["volume"])
        for r in (1, 2):
            for stp in ("range", 0.25, 0.5):
                for mode in ("time", "vwap", "be"):
                    R = BM.orb_fills(Bm, sdm, r, stp, np.full(Dn, 0.036), exit_mode=mode, vwap=vwm if mode == "vwap" else None)
                    ok = R["kind"] != 0
                    pnl = R["gross"][ok] * R["entry"][ok] * 100                # exit - entry, bp of the path's start (100)
                    a_ = acc.setdefault((r, stp, mode), [0.0, 0.0, 0])
                    a_[0] += pnl.sum()
                    a_[1] += (pnl ** 2).sum()
                    a_[2] += int(ok.sum())
    worst, rows_ = -np.inf, []
    for (r, stp, mode), (s1, s2, n_) in acc.items():
        m_ = s1 / n_
        t_ = m_ / np.sqrt((s2 / n_ - m_ * m_) / n_)
        worst = max(worst, t_)
        rows_.append(f"{r}|{stp}|{mode} {m_:+.2f}")
    check(worst < 3.0, f"fill fairness on 200,000 sessions of a continuous driftless path: no breakout cell is significantly positive "
                       f"before costs (largest t {worst:+.2f}); bp a trade: {', '.join(rows_)}")

    # gate wiring through stock_rows: hand-made session, the order fills one bar after each gate's condition first holds
    wg = WW.make_world(n=1, seed=12, start="2024-01-01", bar_start="2024-03-01", end="2024-04-30")
    sg = "S000"
    Fg = BM.daily_features(wg["daily"][sg])
    gdays, Bg0 = BM.bar_matrix(wg["intra"][sg])
    kg = len(gdays) - 1
    day_k = pd.Timestamp(gdays[kg])
    idx = np.arange(BM.NB)

    def session(sign):
        """Long (sign +1) or short mirror: opening bar sets the level at 101 (99), inside the range until bar 10, then
        a steady move away; time exit at the 15:03 open."""
        o = np.full(BM.NB, 100.8)
        h, l, c = o + 0.1, o - 0.1, o.copy()
        o[0], h[0], l[0], c[0] = 100.0, 101.0, 99.5, 100.8
        j = idx[10:]
        o[10:] = 101.0 + 0.05 * (j - 9)
        h[10:], l[10:], c[10:] = o[10:] + 0.02, o[10:] - 0.02, o[10:] + 0.01
        if sign < 0:                                                         # mirror around 100
            o, h, l, c = 200 - o, 200 - l, 200 - h, 200 - c
        B = {k_: v_.copy() for k_, v_ in Bg0.items()}
        for k_, v_ in (("open", o), ("high", h), ("low", l), ("close", c)):
            B[k_][kg] = v_
        B["volume"][kg] = B["volume"][kg] * 3
        return B

    def gx(a, sign):
        e, x = 101.0 + 0.05 * (a - 9), 101.0 + 0.05 * (BM.X_BAR - 9)
        return x / e - 1 if sign > 0 else 1 - (200 - x) / (200 - e)

    stub = lambda F_, rows: np.full(len(rows), 0.02)
    ones = np.ones(len(Fg), bool)
    got, want = [], []
    for sign in (1, -1):
        B = session(sign)
        P_own = BM.since_open(B["close"], B["open"][:, 0])
        cal_g = np.array(gdays, dtype="datetime64[ns]")
        sp = BM.SectorPaths(cal_g, ["IT"])
        sp.add("IT", gdays[kg:kg + 1], P_own[kg:kg + 1])                     # the stock itself and one peer
        sp.add("IT", gdays[kg:kg + 1], sign * np.where(idx <= 17, -0.004, 0.004)[None, :])
        nA = sign * np.where(idx <= 11, -0.005, 0.005)                       # NIFTY against the trade until the close of bar 11
        nB = sign * np.where(idx <= 14, 0.03, 0.001)                         # NIFTY far ahead of the stock until the close of bar 14
        A = BM.stock_rows(sg, Fg, gdays, B, ones, {day_k: nA}, np.zeros(len(Fg)), "IT", sp, memory_fn=stub)[1]
        Bb = BM.stock_rows(sg, Fg, gdays, B, ones, {day_k: nB}, np.ones(len(Fg)), "IT", sp, memory_fn=stub)[1]
        a, b = A[A["day"] == day_k].iloc[0], Bb[Bb["day"] == day_k].iloc[0]
        for row, plan in ((a, {"base": 10, "g_nifty": 13, "g_rs": 10, "g_nifty_rs": 13, "g_sector": 19}),
                          (b, {"g_nifty": 10, "g_rs": 16, "g_nifty_rs": 16})):
            for v, bar in plan.items():
                got.append(float(row[f"g_{v}_range"]))
                want.append(gx(bar, sign))
        if not (a["side"] == sign and a["e_range"] == 10):
            got.append(np.nan)
            want.append(0.0)
    check(len(got) == len(want) and np.allclose(got, want, rtol=0, atol=2e-6),
          "gate wiring (long and short): base fills in bar 10; NIFTY gate in 13 (NIFTY turns at the close of 12); RS gate in 16 "
          "(stock ahead of beta x NIFTY from the close of 15); NIFTY + RS in the later of the two; sector gate in 19 (peers turn at 18)")

    # a gate that cannot judge lets the order through (no sector / no NIFTY that day / no beta): the outcome equals no gate
    B = session(1)
    stub_rows = lambda nifty_, beta_, sec_, sp_: BM.stock_rows(sg, Fg, gdays, B, ones, nifty_, beta_, sec_, sp_, memory_fn=stub)[1]
    a0 = stub_rows({}, np.zeros(len(Fg)), None, None)                                  # no NIFTY bars, no sector
    a1 = stub_rows({day_k: np.where(idx <= 11, -0.005, 0.005)}, np.full(len(Fg), np.nan), None, None)    # NIFTY present, beta unknown
    a0, a1 = a0[a0["day"] == day_k].iloc[0], a1[a1["day"] == day_k].iloc[0]
    check(all(a0[f"g_{v}_range"] == a0["g_base_range"] for v in ("g_nifty", "g_sector", "g_rs", "g_nifty_rs"))
          and a1["g_g_rs_range"] == a1["g_base_range"] and abs(a1["g_g_nifty_range"] - gx(13, 1)) < 2e-6
          and not a0["ev_nifty"] and not a0["ev_sector"] and not a0["ev_rs"] and a1["ev_nifty"] and not a1["ev_rs"],
          "a gate that cannot judge (no NIFTY bars that day, no sector, no beta) lets the order through - same outcome as no gate - "
          "and the row says it was not judged")

    # the exposure-matched PLAIN benchmark, by hand: day 1 has 2 candidates, day 2 has 5; N = 3
    Cm2 = pd.DataFrame({"day": pd.to_datetime(["2025-01-02"] * 2 + ["2025-01-03"] * 5), "symbol": list("ABCDEFG"), "side": 1})
    wm_ = BM.select_book(Cm2, 1, "plain_matched", 3)["w"].to_numpy()
    wp_ = BM.select_book(Cm2, 1, "plain", 3)["w"].to_numpy()
    check(np.allclose(wm_, [1 / 3] * 2 + [0.2] * 5) and np.allclose(wp_, [0.5] * 2 + [0.2] * 5),
          "matched PLAIN: with 2 candidates and N = 3 each gets 1/3 (2/3 of the book in use, as in the 3-slot book); with 5, each 1/5")
    # the trap: thin days (2 candidates, N = 5) lose 1% a trade; busy days (20 candidates) are pure noise. A random 5-slot book
    # holds the thin-day losers at 1/5 each; full PLAIN holds them at 1/2 each. Against full PLAIN a ranking with no skill
    # 'wins' on every thin day; against the matched book the difference is exactly zero there.
    rng = np.random.default_rng(15)
    rows_ = []
    for d_, day in enumerate(pd.bdate_range("2024-01-01", periods=300)):
        nc = 2 if d_ % 2 == 0 else 20
        g_ = np.full(nc, -0.01) if nc == 2 else rng.normal(0, 0.01, nc)
        for j_ in range(nc):
            rows_.append((day, f"X{j_:02d}", 1, rng.random(), g_[j_]))
    Ct = pd.DataFrame(rows_, columns=["day", "symbol", "side", "random", "g_base_range"])
    Ct["k_base_range"] = BM.KIND_TIME
    calt = np.array(sorted(Ct["day"].unique()), dtype="datetime64[ns]")
    dr = BM.book_daily(Ct, calt, 1, "random", 5, "g_base_range", "k_base_range")[0]
    dm_ = BM.book_daily(Ct, calt, 1, "plain_matched", 5, "g_base_range", "k_base_range")[0]
    dp_ = BM.book_daily(Ct, calt, 1, "plain", 5, "g_base_range", "k_base_range")[0]
    thin_ = np.arange(len(calt)) % 2 == 0
    em, ep = (dr - dm_) * 1e4, (dr - dp_) * 1e4
    se_ = em[~thin_].std(ddof=1) / np.sqrt((~thin_).sum())
    check(np.allclose(em[thin_], 0) and abs(em.mean()) < 3 * se_ and ep[thin_].mean() > 50,
          f"benchmark trap: a random 5-slot ranking vs full PLAIN 'earns' {ep[thin_].mean():+.0f} bp on every thin day (the old benchmark); "
          f"vs the matched book exactly 0 there and {em.mean():+.2f} bp/day overall (noise, se {se_:.2f})")

    # usable sessions, positive case; zone-aware timestamps; duplicated timestamps
    o_, h_, l_, c_ = flat_day()
    c80, c79 = c_.copy(), c_.copy()
    c80[100:] = np.nan
    c79[99:] = np.nan
    check(BM.usable_sessions(day_bars(o_, h_, l_, c_))[0] and BM.usable_sessions(day_bars(o_, h_, l_, c80))[0]
          and not BM.usable_sessions(day_bars(o_, h_, l_, c79))[0], "usable: all bars, and exactly 80% of bars, count; 79% does not")
    tsu = pd.to_datetime(["2025-01-02 03:45", "2025-01-02 03:48", "2025-01-02 03:48", "2025-01-02 09:57"]).tz_localize("UTC")
    Xu = pd.DataFrame({"timestamp": tsu, "open": [1.0, 2.0, 2.5, 3.0], "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0})
    du, Bu = BM.bar_matrix(Xu)
    check(len(du) == 1 and Bu["open"][0, 0] == 1 and Bu["open"][0, 1] == 2.5 and Bu["open"][0, 124] == 3,
          "UTC timestamps are converted to IST before slotting (03:45 UTC -> the 09:15 bar); a duplicated timestamp keeps its last row")

    # the memory's spacing and minimum: every measure rises each session, so each session sits at the top of its own history
    # (percentile 1.0) - all states tie and the nearest are the earliest sessions; with rr = row number the median shows
    # which were chosen
    G2 = pd.DataFrame({"day": pd.bdate_range("2024-01-01", periods=120)})
    for f in BM.FEATURES:
        G2[f] = np.arange(120.0)
    G2["atr14"], G2["rr"] = 0.02, np.arange(120, dtype=float)
    mm = BM.move_memory(G2, np.array([100, 59, 44]), k=20, apart=5, min_hist=3)
    check(abs(mm[0] - 0.02 * 47.5) < 1e-12 and abs(mm[1] - 0.02 * 27.5) < 1e-12 and np.isnan(mm[2]),
          "memory: neighbours at least 5 sessions apart (0, 5, ... 95: median 47.5); 12 available -> scored (27.5); "
          "9 available -> no score (needs 10 of 20)")



# ----------------------------------------------------------------------
# 1b. the statistics, calibrated by simulation
# ----------------------------------------------------------------------
def stats_calibration():
    print("1b. statistics by simulation")
    rng = np.random.default_rng(17)
    n, reps = 300, 400
    idx = BM._block_idx(n, 1000, 10, np.random.default_rng(7))
    e = rng.standard_t(4, (reps, n)) * 0.01
    X = np.empty((reps, n))
    X[:, 0] = e[:, 0]
    for t in range(1, n):                                       # AR(1), rho 0.2, fat-tailed (t with 4 df): a true mean of 0
        X[:, t] = 0.2 * X[:, t - 1] + e[:, t]
    st = [BM.boot_stats(x, idx) for x in X]
    cover = float(np.mean([lo <= 0 <= hi for _, lo, hi, _ in st]))
    small = float(np.mean([p < 0.05 for _, _, _, p in st]))
    check(0.90 <= cover <= 0.98 and 0.02 <= small <= 0.09,
          f"block bootstrap on {reps} autocorrelated fat-tailed series with a true mean of 0: the 95% interval holds 0 in "
          f"{cover * 100:.1f}% of them; the one-sided p is under 0.05 in {small * 100:.1f}% (should be about 5%)")
    idx5 = BM._block_idx(n, 500, 10, np.random.default_rng(8))
    rc = [BM.reality_check(rng.normal(0, 0.006, (n, 1)) + rng.normal(0, 0.008, (n, 20)), idx5) for _ in range(200)]
    rc_rate = float(np.mean(np.array(rc) < 0.05))
    check(0.01 <= rc_rate <= 0.10, f"Reality Check on 200 sets of 20 correlated books with no edge: p < 0.05 in {rc_rate * 100:.1f}% "
                                   f"(should be about 5%)")
    null_pass, power = 0, 0
    for i in range(300):
        Xn = rng.normal(0, 0.01, (n, 20))
        sh = Xn.mean(0) / Xn.std(0, ddof=1) * np.sqrt(250)
        null_pass += BM.deflated_sharpe(Xn[:, int(np.argmax(sh))], sh, 20) >= 0.95
        Xp = Xn.copy()
        Xp[:, 0] += 0.01 * 5 / np.sqrt(250)                     # one real strategy, Sharpe about 5 a year
        shp = Xp.mean(0) / Xp.std(0, ddof=1) * np.sqrt(250)
        power += (int(np.argmax(shp)) == 0) and BM.deflated_sharpe(Xp[:, 0], shp, 20) >= 0.95
    check(null_pass / 300 <= 0.10 and power / 300 >= 0.80,
          f"deflated Sharpe: the best of 20 noise strategies passes 0.95 in {null_pass / 3:.1f}% of 300 tries; a real Sharpe-5 "
          f"strategy among them is found and passes in {power / 3:.1f}%")
    # selection: the cell with the best Sharpe among 36 related ranked cells, in a market where buying everything pays and
    # no ranking adds anything (each cell = the plain book + an excess with a true mean of zero). Its own excess lower bound
    # is above zero far more often than the nominal 2.5%; judged against the search (amendment q) it is not. A real
    # ranking (6 of the 36 cells, excess Sharpe about 4 a year) is still found.
    idx_s = BM._block_idx(n, 500, 10, np.random.default_rng(10))
    pmax = float(BM.CFG["excess_padj_max"])
    own = srch = pw_own = pw_srch = 0
    reps_s = 200
    for i_ in range(reps_s):
        plain = rng.normal(0.0012, 0.01, n)                                   # buying everything: Sharpe about 1.9 a year
        ex = rng.normal(0, 0.004, n)[:, None] + rng.normal(0, 0.004, (n, 36))  # rankings share half their noise
        for planted in (False, True):
            ex_ = ex.copy()
            if planted:
                ex_[:, :6] += 4 / np.sqrt(250) * ex.std()
            lvl = plain[:, None] + ex_
            j = int(np.argmax(lvl.mean(0) / lvl.std(0, ddof=1)))
            lo_ok = BM.boot_stats(ex_[:, j], idx_s)[1] > 0
            s_ok = lo_ok and BM.max_t_pvalues(ex_, idx_s)[j] < pmax
            if planted:
                pw_own += lo_ok and j < 6
                pw_srch += s_ok and j < 6
            else:
                own += lo_ok
                srch += s_ok
    check(own / reps_s >= 0.08 and srch / reps_s <= 0.06 and pw_srch / reps_s >= 0.80,
          f"selection: the best of 36 rankings that add nothing shows its own excess lower bound above zero in {own / reps_s * 100:.1f}% "
          f"of {reps_s} markets (nominal 2.5%); judged against the search, in {srch / reps_s * 100:.1f}%. A real ranking is picked and "
          f"passes in {pw_srch / reps_s * 100:.1f}% (own lower bound alone: {pw_own / reps_s * 100:.1f}%)")


# ----------------------------------------------------------------------
# 1c. the synthetic world itself
# ----------------------------------------------------------------------
def world_generator():
    print("1c. the synthetic world")
    kw = dict(n=6, start="2024-01-01", bar_start="2024-03-01", end="2024-06-28")
    a, b = WW.make_world(seed=5, **kw), WW.make_world(seed=5, **kw)
    same_ = (all(a["intra"][s_].equals(b["intra"][s_]) and a["daily"][s_].equals(b["daily"][s_]) for s_ in a["intra"])
             and a["nifty_bars"].equals(b["nifty_bars"]))
    c = WW.make_world(seed=5, p_cat=0.1, **kw)
    ok_r = ok_v = True
    n_cmp = 0
    for s_ in a["intra"]:
        tr = c["truth"][c["truth"]["symbol"] == s_].set_index("day")["catalyst"]
        xa, xc = a["intra"][s_], c["intra"][s_]
        for d_, g_ in xa.groupby(xa["timestamp"].dt.normalize()):
            if tr.get(d_, 0) != 0:
                continue
            gc = xc[xc["timestamp"].dt.normalize() == d_]
            ok_r &= np.allclose(np.diff(np.log(g_["close"].to_numpy())), np.diff(np.log(gc["close"].to_numpy())), atol=1e-12)
            ok_v &= np.allclose(g_["volume"].to_numpy(), gc["volume"].to_numpy())
            n_cmp += 1
    t_ = WW.make_world(seed=5, nifty_trend=True, **kw)
    nb0, nb1 = a["nifty_bars"], t_["nifty_bars"]
    quiet = t_["nifty_dir"][-len(nb0) // BM.NB:] == 0
    r0 = np.diff(np.log(nb0["close"].to_numpy()).reshape(-1, BM.NB), axis=1)[quiet]
    r1 = np.diff(np.log(nb1["close"].to_numpy()).reshape(-1, BM.NB), axis=1)[quiet]
    check(same_ and ok_r and ok_v and n_cmp > 300 and np.allclose(r0, r1, atol=1e-12),
          f"the world is reproducible from its seed, and switching one effect leaves the others' random numbers alone: catalysts on "
          f"vs off - identical returns and volumes on all {n_cmp} stock-days without a catalyst; NIFTY trends on vs off - identical "
          f"NIFTY bars on the days without a trend")


# ----------------------------------------------------------------------
# 2. planted and null worlds
# ----------------------------------------------------------------------
def worlds():
    print("2. planted and null worlds")
    cands_sip, cal_sip, sl_sip = build_world(WW.make_world(n=48, seed=1, p_cat=0.04, bar_start="2024-01-01"))   # 12 months of discovery
    R = BM.run_books(cands_sip, cal_sip, sl_sip)
    for sd in ("L", "S"):
        rv, mf = pick(R, sd, "best rv"), pick(R, sd, "best mfe")
        check(rv["verdict"] == "CHAMPION" and mf["verdict"] not in ("CHAMPION", "PROMISING"),
              f"stocks in play, {sd}: RV book {rv['verdict']} ({rv['disc_mean_bp']:+.1f} bp/day, confirmation {rv['conf_mean_bp']:+.1f}); "
              f"the blind MFE book {mf['verdict']} (excess over plain {mf['disc_excess_bp']:+.1f})")
    check(pooled(R, "L", "mfe")["adds"] and pooled(R, "S", "mfe")["adds"] and not pooled(R, "L", "rv")["adds"] and not pooled(R, "S", "rv")["adds"],
          "stocks in play: RVxMFE beats MFE (RV carries the signal) but does not add over RV")
    check(R["reality_check"]["F1 L"] < 0.01 and R["reality_check"]["F1 S"] < 0.01, f"Reality Check sees the planted edge: "
          f"F1 L {R['reality_check']['F1 L']:.4f}, F1 S {R['reality_check']['F1 S']:.4f}")
    C = R["cells"]
    rnd = C[(C["score"] == "random")]["disc_mean_bp"].max()
    check(pick(R, "L", "best rv")["disc_mean_bp"] > rnd + 10, f"RV beats the random control by a wide margin (random best {rnd:+.1f})")
    # the confirmation window must not steer selection: flip the sign of every outcome after the discovery end and re-run
    later = pd.Timestamp(BM.CFG["discovery_end"])
    flipped = {}
    for r_, Cd in cands_sip.items():
        F_ = Cd.copy()
        m_ = (F_["day"] > later).to_numpy()
        for c_ in [c for c in F_.columns if c.startswith("g_")]:
            F_.loc[m_, c_] = -F_.loc[m_, c_]
        flipped[r_] = F_
    Rf = BM.run_books(flipped, cal_sip, sl_sip)
    key_ = ["side", "pick", "score", "or_bars", "top_n", "stop"]
    s1, s2 = R["selected"][key_], Rf["selected"][key_]
    b1, b2 = pick(R, "L", "best"), pick(Rf, "L", "best")
    check(s1.equals(s2) and R["variants"]["on_cell"].equals(Rf["variants"]["on_cell"])
          and np.isclose(b1["disc_mean_bp"], b2["disc_mean_bp"]) and b1["conf_mean_bp"] > 0 > b2["conf_mean_bp"],
          f"confirmation cannot steer selection: with every later outcome sign-flipped, the same {len(s1)} cells are picked and the "
          f"gates / exits run on the same cells; only the later numbers change (best L confirmation {b1['conf_mean_bp']:+.1f} -> "
          f"{b2['conf_mean_bp']:+.1f} bp/day, verdict {b1['verdict']} -> {b2['verdict']})")

    R = run_world(WW.make_world(n=48, seed=2, state=True))
    for sd in ("L", "S"):
        mf, rv = pick(R, sd, "best mfe"), pick(R, sd, "best rv")
        check(mf["disc_mean_bp"] > rv["disc_mean_bp"] and mf["disc_excess_bp"] > 0,
              f"state-driven moves, {sd}: MFE book {mf['disc_mean_bp']:+.1f} bp/day ({mf['verdict']}) beats the RV book "
              f"{rv['disc_mean_bp']:+.1f} ({rv['verdict']})")
    check(pooled(R, "L", "rv")["disc_diff_bp"] > 0 and pooled(R, "S", "rv")["disc_diff_bp"] > 0,
          "state-driven moves: RVxMFE beats RV (the memory carries the signal)")

    R = run_world(WW.make_world(n=300, seed=21, p_cat=0.10, cat_vol=3.5, interact=True, state_thresh=-0.035, loaded_vol=2.0, loaded_volume=1.8))
    nums = {(sd, vs, wn): pooled(R, sd, vs)[f"{wn}_diff_bp"] for sd in ("L", "S") for vs in ("rv", "mfe") for wn in ("disc", "conf")}
    check(all(v > 0 for v in nums.values()) and pooled(R, "L", "rv")["adds"] and pooled(R, "S", "rv")["adds"],
          "payoff needs both (a catalyst only runs on a loaded stock): RVxMFE beats RV and MFE on both sides in both windows, and "
          "adds over RV: " + ", ".join(f"{sd}-{vs} {nums[(sd, vs, 'disc')]:+.1f}/{nums[(sd, vs, 'conf')]:+.1f}" for sd in ("L", "S") for vs in ("rv", "mfe")))

    R = run_world(WW.make_world(n=48, seed=4, p_cat=0.04, cat_mode="short_only"))
    s_, l_ = pick(R, "S", "best rv"), pick(R, "L", "best rv")
    check(s_["verdict"] in ("CHAMPION", "PROMISING") and l_["disc_mean_bp"] < s_["disc_mean_bp"] - 20 and l_["verdict"] != "CHAMPION",
          f"short-only catalysts: BIGMOVE-S {s_['verdict']} ({s_['disc_mean_bp']:+.1f}), BIGMOVE-L {l_['verdict']} ({l_['disc_mean_bp']:+.1f})")

    gw = dict(n=48, bar_start="2024-01-01", sigma=0.012, open_kick=0.006, trend_drift=0.02)
    cands_g, cal_g, sl_g = build_world(WW.make_world(seed=22, nifty_trend=True, beta=1.0, **gw))
    R = BM.run_books(cands_g, cal_g, sl_g)
    gn = [gate(R, sd, "g_nifty") for sd in ("L", "S")]
    check(all(g["adds"] for g in gn), "NIFTY trend days (each stock's own opening hides the direction): the NIFTY gate adds on both sides "
          f"({', '.join(f'{g.side} {g.disc_diff_bp:+.1f} [{g.disc_diff_lo_bp:+.1f}]' for g in gn)})")
    # here RV and the memory carry nothing, and on trend days the counter-trend side is thin: the trap the review found
    C = R["cells"]
    rnd = C[C["score"] == "random"]
    ranked_best = R["selected"][R["selected"]["pick"].isin(["best rv", "best mfe", "best rvxmfe"])]
    check(not ranked_best["verdict"].isin(["CHAMPION", "PROMISING"]).any(),
          f"no-skill rankings in a trend market: no RV / MFE / RVxMFE pick is PROMISING or CHAMPION ({sorted(set(ranked_best['verdict']))}); "
          f"for the record, the random control's excess over matched PLAIN has median {float(rnd['disc_excess_bp'].median()):+.2f} bp/day "
          f"(24 overlapping cells, lower bound above zero in {int((rnd['disc_excess_lo_bp'] > 0).sum())})")
    # the clause that a RANKED cell's gate / exit variants must also beat the same variant on the matched PLAIN book: the
    # variants are run on each side's best RV cell directly ('best' itself may be PLAIN, where the clause does not apply)
    Wg = BM.windows(cal_g)
    idx_g = {int(wm.sum()): BM._block_idx(int(wm.sum()), int(BM.CFG["boot_B"]), int(BM.CFG["boot_block"]),
                                          np.random.default_rng(int(BM.CFG["seed"]))) for wm in Wg.values() if wm.sum() >= 20}
    tsh = R["cells"].loc[R["cells"]["family"] == "F1", "disc_sharpe"].to_numpy(float)
    vr = pd.DataFrame([row for sd in ("L", "S")
                       for row in BM.run_variants(cands_g, cal_g, pick(R, sd, "best rv"), R["daily"], Wg, idx_g, tsh, R["n_trials"])[0]])
    vr = vr[~vr["verdict"].astype(str).str.startswith("NOT RUN")]
    good = vr[vr["verdict"].isin(["CHAMPION", "PROMISING"])]
    w_ = lambda r_, p_: {k_[len(p_):]: r_[k_] for k_ in r_.index if k_.startswith(p_)}
    PC = ("PROMISING", "CHAMPION")
    old_rule = [BM.verdict(w_(r_, "disc_"), w_(r_, "conf_"), r_["disc_dsr"], ranked=False) for _, r_ in vr.iterrows()]
    # the clause alone: the search check (amendment q) switched off by giving every base a p of 0
    e_rule = [BM.verdict({**w_(r_, "disc_"), "excess_padj": 0.0}, w_(r_, "conf_"), r_["disc_dsr"], ranked=True) for _, r_ in vr.iterrows()]
    bites = sum(o_ in PC and e_ not in PC for o_, e_ in zip(old_rule, e_rule))
    never_better = all(not (v_ in PC and e_ not in PC) for v_, e_ in zip(vr["verdict"], e_rule))
    check(len(vr) > 0 and ((good["disc_excess_lo_bp"] > 0) & (good["conf_excess_bp"] > 0)
                           & (good["disc_excess_padj"] < float(BM.CFG["excess_padj_max"]))).all() and bites >= 1 and never_better,
          f"a ranked cell's gate / exit variants need to beat the same variant on matched PLAIN (run on each side's best RV cell): "
          f"{bites} variant(s) that would have been PROMISING or CHAMPION on their own numbers are not, by that clause alone "
          f"({', '.join(f'{r_.side}-{r_.variant} {r_.verdict}' for r_ in vr.itertuples())})")
    # the world the review used: no open kick, so on trend days the counter-trend side is thin (part of an N-slot book in cash);
    # rankings carry nothing. Full PLAIN would credit a random ranking with 'skill'; the matched book must not.
    R = run_world(WW.make_world(n=48, seed=34, bar_start="2024-01-01", nifty_trend=True, beta=1.0, sigma=0.012, trend_drift=0.02))
    Wn, Dn_ = BM.windows(R["calendar"]), R["daily"]
    idx_ = BM._block_idx(int(Wn["disc"].sum()), int(BM.CFG["boot_B"]), int(BM.CFG["boot_block"]), np.random.default_rng(int(BM.CFG["seed"])))
    old_lo = new_lo = 0
    rk = [k_ for k_ in Dn_ if k_[1] == "random"]
    full_ = [Dn_[k_][1.0] - Dn_[(k_[0], "plain", k_[2], 0, k_[4])][1.0] for k_ in rk]
    matched_ = [Dn_[k_][1.0] - Dn_[(k_[0], "plain_matched", k_[2], k_[3], k_[4])][1.0] for k_ in rk]
    for a_, b_ in zip(full_, matched_):
        old_lo += BM.boot_stats(a_[Wn["disc"]], idx_)[1] > 0
        new_lo += BM.boot_stats(b_[Wn["disc"]], idx_)[1] > 0
    flatter = (np.mean(full_, 0)[Wn["disc"]].mean() - np.mean(matched_, 0)[Wn["disc"]].mean()) * 1e4
    bests = [pick(R, sd, "best") for sd in ("L", "S")]
    rule_ok = all((b_["score"] == "plain" or BM.excess_survives({k_[5:]: b_[k_] for k_ in b_.index if k_.startswith("disc_")}))
                  and b_["disc_lo_bp"] > 0 and b_["chosen_by"] == "met the discovery rule" for b_ in bests)
    ranked_best = R["selected"][R["selected"]["pick"].isin(["best rv", "best mfe", "best rvxmfe"])]
    # thresholds: 3 of 24 is about 5x the 2.5% a cell shows by chance (the first suite's 6 was arbitrary, and the world's
    # random numbers changed with the per-mechanism streams); 'flatter' is the bias itself, in bp/day
    check(old_lo >= 3 and new_lo <= 2 and flatter > 1.0 and rule_ok and not ranked_best["verdict"].isin(["CHAMPION", "PROMISING"]).any(),
          f"thin counter-trend days, no skill anywhere: full PLAIN flatters a random ranking by {flatter:+.2f} bp/day (its lower bound is "
          f"above zero in {old_lo} of {len(rk)} cells); against the matched book in {new_lo}; no ranked pick passes; 'best' is chosen "
          f"by the discovery rule ({', '.join(f'{b_.side} {b_.score} {b_.verdict}' for _, b_ in pd.DataFrame(bests).iterrows())})")
    R = run_world(WW.make_world(seed=25, nifty_trend=True, n_sectors=4, sector_trend=True, sector_mode="against_nifty", **gw))
    gs, gn = [gate(R, sd, "g_sector") for sd in ("L", "S")], [gate(R, sd, "g_nifty") for sd in ("L", "S")]
    check(all(g["adds"] for g in gs) and all(g["disc_diff_bp"] < 0 and not g["adds"] for g in gn),
          f"NIFTY and the sectors disagree (sectors trend against NIFTY; stocks follow their sector): the sector gate adds "
          f"({', '.join(f'{g.side} {g.disc_diff_bp:+.1f} [{g.disc_diff_lo_bp:+.1f}]' for g in gs)}) and the NIFTY gate hurts "
          f"({', '.join(f'{g.side} {g.disc_diff_bp:+.1f}' for g in gn)})")
    R = run_world(WW.make_world(seed=23, n_sectors=4, sector_trend=True, **gw))
    gs, gn = [gate(R, sd, "g_sector") for sd in ("L", "S")], [gate(R, sd, "g_nifty") for sd in ("L", "S")]
    check(all(g["adds"] for g in gs) and not any(g["adds"] for g in gn),
          f"sector trend days: the sector gate adds ({', '.join(f'{g.side} {g.disc_diff_bp:+.1f} [{g.disc_diff_lo_bp:+.1f}]' for g in gs)}); "
          f"the NIFTY gate does not ({', '.join(f'{g.side} {g.disc_diff_bp:+.1f}' for g in gn)})")
    wi = WW.make_world(seed=24, n_sectors=4, idio_trend=True, **gw)
    wi["sector_of"] = {k_: v_ for i_, (k_, v_) in enumerate(sorted(wi["sector_of"].items())) if i_ % 2 == 0}   # half are unmapped
    R = run_world(wi)
    g4 = [gate(R, sd, v) for sd in ("L", "S") for v in ("g_nifty", "g_sector", "g_rs", "g_nifty_rs")]
    judged = [gate(R, sd, "g_sector")["disc_evaluable_share"] for sd in ("L", "S")]
    check(not any(g["adds"] for g in g4) and all(pick(R, sd, "best")["disc_mean_bp"] > 0 for sd in ("L", "S"))
          and all(0.3 < j < 0.7 for j in judged),
          "stock-only trend days (the null for the gates, on a profitable base), half the stocks without a sector: no gate adds "
          f"({', '.join(f'{g.side}-{g.variant} {g.disc_diff_bp:+.1f}' for g in g4)}); the sector gate judged "
          f"{', '.join(f'{j * 100:.0f}%' for j in judged)} of picks and let the rest through")

    R0 = run_world(WW.make_world(n=48, seed=7))
    v0 = R0["selected"][~R0["selected"]["pick"].str.startswith("median")]["verdict"]
    cm0 = R0["comparison"][R0["comparison"]["or_bars"] == "pooled"]
    check(not v0.isin(["CHAMPION", "PROMISING"]).any() and not cm0["adds"].any(),
          f"NULL world with costs: no PROMISING or CHAMPION ({sorted(set(v0))}); no RVxMFE comparison adds")
    keep = (BM.COST_BPS, BM.CFG["slip_entry_bps"], BM.CFG["slip_stop_bps"], BM.CFG["slip_time_bps"])
    BM.COST_BPS, BM.CFG["slip_entry_bps"], BM.CFG["slip_stop_bps"], BM.CFG["slip_time_bps"] = 0.0, 0.0, 0.0, 0.0
    try:
        Rz = run_world(WW.make_world(n=48, seed=8))
    finally:
        BM.COST_BPS, BM.CFG["slip_entry_bps"], BM.CFG["slip_stop_bps"], BM.CFG["slip_time_bps"] = keep
    vz = Rz["selected"][~Rz["selected"]["pick"].str.startswith("median")]
    rz = Rz["reality_check"]
    check("CHAMPION" not in set(vz["verdict"]) and rz["F1 L"] > 0.05 and rz["F1 S"] > 0.05 and (vz["disc_dsr"] < 0.95).all(),
          f"NULL world with ZERO costs: no CHAMPION, Reality Check quiet (F1 L {rz['F1 L']:.3f}, F1 S {rz['F1 S']:.3f}), "
          f"best DSR {vz['disc_dsr'].max():.2f}")
    sl = R0["sleeve"]
    check(len(sl) == 6 and (sl["verdict"] != "CHAMPION").all(), "NIFTY sleeve: 6 cells, no CHAMPION in a random NIFTY")


# ----------------------------------------------------------------------
# 3. look-ahead
# ----------------------------------------------------------------------
def look_ahead():
    print("3. look-ahead")
    w = WW.make_world(n=3, seed=9, start="2023-06-01", bar_start="2024-07-01", end="2024-12-31", p_cat=0.1)
    s = "S000"
    nd = w["nifty_daily"].copy()
    nd["day"] = BM.SI._naive_days(nd["timestamp"]).to_numpy()
    nifty = BM.nifty_context(w["nifty_bars"])

    def rows_for(D, X, NDf, mem=BM.move_memory, beta_fn=BM.beta_series):
        F = BM.daily_features(D)
        days, B = BM.bar_matrix(X)
        return BM.stock_rows(s, F, days, B, BM.liquid_ok(F), nifty, beta_fn(F, NDf), memory_fn=mem)

    def leaky_memory(F, rows):                            # uses the decision day's own range (candidate r = t-1)
        Z = F[BM.FEATURES].expanding(min_periods=1).rank(pct=True).to_numpy(float)
        rr, atr = F["rr"].to_numpy(float), F["atr14"].to_numpy(float)
        out = np.full(len(rows), np.nan)
        for j, tt in enumerate(rows):
            q = tt - 1
            cand = np.flatnonzero(np.isfinite(rr[: q + 1]))
            if q < 60 or len(cand) < 20:
                continue
            d2 = BM.SI.nan_dist(Z[q], Z[cand])
            out[j] = atr[q] * np.median(rr[cand[np.argsort(d2)[:20]]])
        return out

    def leaky_beta(F, NDf):
        return np.r_[BM.beta_series(F, NDf)[1:], np.nan]       # tomorrow's beta today

    def perturb(t, r, rng, shrink):
        """The decision day's daily bar (shrunk to one price, or blown up), its bars after an r-bar opening range, and
        every later day, all changed at random; NIFTY's later closes too."""
        D2 = w["daily"][s].copy()
        ts = pd.to_datetime(D2["timestamp"]).dt.normalize()
        later = (ts >= t).to_numpy()
        n_ = int(later.sum())
        for c in ("open", "high", "low", "close"):
            D2.loc[later, c] = D2.loc[later, c].to_numpy() * rng.uniform(0.8, 1.25, n_)
        if shrink:
            today = (ts == t).to_numpy()
            for c in ("open", "high", "low"):
                D2.loc[today, c] = D2.loc[today, "close"].to_numpy()
        D2.loc[later, "high"] = D2.loc[later, ["open", "high", "low", "close"]].max(axis=1)
        D2.loc[later, "low"] = D2.loc[later, ["open", "high", "low", "close"]].min(axis=1)
        D2.loc[later, "volume"] = D2.loc[later, "volume"].to_numpy() * rng.uniform(0.3, 3.0, n_)
        X2 = w["intra"][s].copy()
        after = ((X2["timestamp"] >= t + pd.Timedelta(minutes=555 + BM.BAR * r)) | (X2["timestamp"].dt.normalize() > t)).to_numpy()
        m_ = int(after.sum())
        f = rng.uniform(0.9, 1.1, m_)
        for c in ("open", "high", "low", "close"):
            X2.loc[after, c] = X2.loc[after, c].to_numpy() * f
        X2.loc[after, "volume"] = X2.loc[after, "volume"].to_numpy() * rng.uniform(0.2, 5.0, m_)
        nd2 = nd.copy()
        lat = (nd2["day"] >= t).to_numpy()
        nd2.loc[lat, "close"] = nd2.loc[lat, "close"].to_numpy() * rng.uniform(0.9, 1.1, int(lat.sum()))
        return D2, X2, nd2

    base = rows_for(w["daily"][s], w["intra"][s], nd)
    b_mem = rows_for(w["daily"][s], w["intra"][s], nd, mem=leaky_memory)
    b_beta = rows_for(w["daily"][s], w["intra"][s], nd, beta_fn=leaky_beta)
    asof = ["rv", "side", "mfe", "atr", "beta"]
    outc = [c for c in base[1].columns if c.startswith(("g_", "k_"))]
    both = sorted(set(pd.DatetimeIndex(base[1]["day"])) & set(pd.DatetimeIndex(base[2]["day"])))
    step = max(1, len(both) // 13)
    tdays = both[step::step][:12]
    rng = np.random.default_rng(10)
    cases, held, changed = 0, 0, 0
    caught = {"memory": 0, "beta": 0}
    for i, t in enumerate(tdays):
        for r in (1, 2):
            D2, X2, nd2 = perturb(t, r, rng, shrink=(i % 2 == 0))
            P = rows_for(D2, X2, nd2)
            a = base[r][base[r]["day"] == t]
            b = P[r][P[r]["day"] == t] if r in P else base[r].iloc[:0]
            cases += 1
            if len(a) == 1 and len(b) == 1 and all(same(a[c], b[c]) for c in asof):
                held += 1
            if len(b) == 1 and not all(same(a[c], b[c]) for c in outc):
                changed += 1
            if r == 1:
                for nm, kw, B0 in (("memory", {"mem": leaky_memory}, b_mem), ("beta", {"beta_fn": leaky_beta}, b_beta)):
                    Lk = rows_for(D2, X2, nd2, **kw)
                    a_, b_ = B0[1][B0[1]["day"] == t], Lk[1][Lk[1]["day"] == t]
                    if len(a_) == 1 and len(b_) == 1 and not all(same(a_[c], b_[c]) for c in asof):
                        caught[nm] += 1
    check(cases == 24 and held == cases, f"{len(tdays)} decision days x 2 opening ranges: RV, side, memory, ATR and beta ignore the "
                                         f"day's own daily bar, its bars after the range and every later day ({held}/{cases})")
    check(changed >= 0.8 * cases, f"the perturbation is real: the day's outcomes changed in {changed}/{cases} cases")
    check(caught["memory"] >= 1 and caught["beta"] >= 1,
          f"planted leaks are caught: memory using the day's own range on {caught['memory']}/12 days, beta using the day's own return on "
          f"{caught['beta']}/12 days")

    t = pd.Timestamp(tdays[len(tdays) // 2])
    X3 = w["intra"][s].copy()
    fut = X3["timestamp"].dt.normalize() > t
    for c in ("open", "high", "low", "close"):
        X3.loc[fut, c] = X3.loc[fut, c] * 1.3
    D3 = w["daily"][s].copy()
    fut_d = pd.to_datetime(D3["timestamp"]) > t
    for c in ("open", "high", "low", "close"):
        D3.loc[fut_d, c] = D3.loc[fut_d, c] * 1.3
    nd3 = nd.copy()
    nd3.loc[nd3["day"] > t, "close"] *= 1.3
    fut_rows = rows_for(D3, X3, nd3)
    ok = True
    n_rows = 0
    for r in (1, 2):
        a, b = base[r][base[r]["day"] <= t], fut_rows[r][fut_rows[r]["day"] <= t]
        num = [c for c in a.columns if c not in ("day", "symbol", "sector")]
        ok &= len(a) == len(b) and all(same(a[c].to_numpy(float), b[c].to_numpy(float)) for c in num)
        n_rows += len(a)
    check(ok, f"changing only later days leaves every row up to {t.date()} identical, outcomes included ({n_rows} rows)")


# ----------------------------------------------------------------------
# 4. main() end to end
# ----------------------------------------------------------------------
def stand_ins(reconcile):
    """Stand-in data_quality and intraday_cache modules for a temporary root."""
    dq = types.ModuleType("data_quality")
    dq._paths = lambda root, s: (Path(root) / f"{s}_daily.parquet", Path(root) / f"{s}_daily.ok.json")
    dq.discover_symbols = lambda root: sorted(p.name[:-len("_daily.parquet")] for p in Path(root).glob("*_daily.parquet"))
    dq._read_ok = lambda p: json.loads(Path(p).read_text(encoding="utf-8")) if Path(p).exists() else None
    ic = types.ModuleType("intraday_cache")
    ic.store, ic.BAR_MIN = (lambda root: Path(root) / "intraday_3m"), 3
    ic.DECL = {"reconcile_price_tol": 0.005, "reconcile_volume_tol": 0.10}
    ic.reconcile_symbol = reconcile
    return dq, ic


def write_root(tmp: Path, w: dict) -> list:
    (tmp / "intraday_3m").mkdir()
    (tmp / "sectors").mkdir()
    (tmp / "panel").mkdir()
    syms = list(w["daily"])
    for s in syms:
        w["daily"][s].to_parquet(tmp / f"{s}_daily.parquet", index=False)
        (tmp / f"{s}_daily.ok.json").write_text(json.dumps({"series_kind": "equity"}), encoding="utf-8")
        w["intra"][s].to_parquet(tmp / "intraday_3m" / f"{s}_3m.parquet", index=False)
    w["nifty_daily"].to_parquet(tmp / "NIFTY50_daily.parquet", index=False)
    (tmp / "NIFTY50_daily.ok.json").write_text(json.dumps({"series_kind": "index"}), encoding="utf-8")
    w["nifty_bars"].to_parquet(tmp / "intraday_3m" / "NIFTY 50_3m.parquet", index=False)
    return syms


def with_modules(dq, ic, fn):
    saved = {m: sys.modules.get(m) for m in ("data_quality", "intraday_cache")}
    sys.modules.update({"data_quality": dq, "intraday_cache": ic})
    try:
        return fn()
    finally:
        for m, v in saved.items():
            if v is None:
                sys.modules.pop(m, None)
            else:
                sys.modules[m] = v


def glue():
    print("4. main() end to end (stand-in modules)")
    keep_ds = BM.CFG["discovery_start"]
    BM.CFG["discovery_start"] = "2024-07-01"            # as in the real data, the 3-minute bars begin at the discovery start
    try:
        _glue()
    finally:
        BM.CFG["discovery_start"] = keep_ds


def _glue():
    tmp = Path(tempfile.mkdtemp())
    w = WW.make_world(n=40, seed=11, p_cat=0.04, nifty_trend=True, beta=0.5)
    try:
        syms = write_root(tmp, w)
        for etf, src in (("GOLDETFX", "S006"), ("QQQINDIA", "S007")):       # two liquid ETFs with bars: one by ISIN, one by the ETF list
            w["daily"][src].to_parquet(tmp / f"{etf}_daily.parquet", index=False)
            (tmp / f"{etf}_daily.ok.json").write_text(json.dumps({"series_kind": "equity"}), encoding="utf-8")
            w["intra"][src].to_parquet(tmp / "intraday_3m" / f"{etf}_3m.parquet", index=False)
        sec = pd.DataFrame({"Company Name": syms + ["Gold ETF"], "Industry": ["IT" if i % 2 else "Banks" for i in range(len(syms))] + ["ETF"],
                            "Symbol": syms + ["GOLDETFX"], "Series": "EQ", "ISIN Code": [f"INE{i:09d}" for i in range(len(syms))] + ["INF000000001"]})
        sec.to_csv(tmp / "sectors" / "ind_nifty500list.csv", index=False)
        pd.DataFrame({"Symbol": ["QQQINDIA"], "Underlying": ["NASDAQ 100"], "ISINNumber": ["INF000000002"]}).to_csv(
            tmp / "sectors" / "eq_etfseclist.csv", index=False)
        x7 = w["intra"]["S008"]                                                       # S008: only its last 30 sessions have bars
        keep7 = x7["timestamp"].dt.normalize().isin(x7["timestamp"].dt.normalize().unique()[-30:])
        x7[keep7].to_parquet(tmp / "intraday_3m" / "S008_3m.parquet", index=False)
        bad_day = pd.Timestamp(w["intra"]["S010"]["timestamp"].dt.normalize().unique()[30])
        x10 = w["intra"]["S010"]

        def reconcile(X, d, tp, tv):                                                     # one stock-day (S010) fails reconciliation
            J = pd.DataFrame({"day": pd.Series(X["timestamp"].dt.normalize().unique())})
            is10 = len(X) == len(x10) and bool(np.isclose(X["open"].iloc[0], x10["open"].iloc[0]))
            J["ok"] = ~((J["day"] == bad_day) & is10)
            return J
        dq, ic = stand_ins(reconcile)

        def body():
            for s in syms[:6]:                                                              # 6 of 40 liquid stocks lack bars
                (tmp / "intraday_3m" / f"{s}_3m.parquet").rename(tmp / "intraday_3m" / f"{s}_3m.parquet.bak")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = BM.main(["--root", str(tmp), "--coverage-only"])
            miss = (tmp / "research2" / "bigmove" / "missing_liquid.txt").read_text(encoding="utf-8").split()
            cbs = pd.read_csv(tmp / "research2" / "bigmove" / "coverage_by_stock.csv")
            check(rc == 0 and miss == sorted(syms[:6] + ["S008"]) and not ({"GOLDETFX", "QQQINDIA"} & set(cbs["symbol"])),
                  f"--coverage-only counts DAYS: the 6 stocks without a file and S008 (30 sessions of bars) are listed {miss}; "
                  f"the two ETFs (INF ISIN; the ETF list file) are not in the universe")
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    BM.main(["--root", str(tmp)])
                check(False, "under 90% coverage the run is refused")
            except SystemExit as e:
                check("missing_liquid.txt" in str(e) and "--allow-partial-universe" in str(e), "under 90% coverage the run is refused, with the way out")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = BM.main(["--root", str(tmp), "--allow-partial-universe"])
            runs = list((tmp / "research2" / "bigmove").glob("BM_*"))
            need = ["report.md", "cells.csv", "selected.csv", "gates.csv", "exits.csv", "comparison.csv", "nifty_sleeve.csv", "thin_days.csv",
                    "regimes.csv", "daily_returns.parquet", "trades_selected.parquet", "coverage.json", "summary.json"]
            check(rc == 0 and len(runs) == 1 and all((runs[0] / f).exists() for f in need), "a partial-universe run writes every output")
            summ = json.loads((runs[0] / "summary.json").read_text(encoding="utf-8"))
            rep = (runs[0] / "report.md").read_text(encoding="utf-8")
            cv = summ["coverage"]
            check(summ["declaration"] == __import__("hashlib").sha256(BM.DECL_RAW).hexdigest()[:16] and len(summ["verdicts"]) >= 10
                  and len(summ["variant_verdicts"]) == 12 and len(summ["sleeve_verdict"]) == 1 and "L" in summ["combined_book"].get("cells", {})
                  and "NIFTY 50_3m.parquet" in cv["nifty"] and "symbols mapped" in cv["sectors"] and "ETF list read" in cv["etf_list"]
                  and all(v_["excess_p_search"] is None for v_ in summ["verdicts"] if v_["score"] == "plain")
                  and all(0 < v_["excess_p_search"] <= 1 for v_ in summ["verdicts"] if v_["excess_p_search"] is not None)
                  and any(v_["excess_p_search"] is not None for v_ in summ["verdicts"]) and "p (search)" in rep,
                  "summary: fingerprint, verdicts of every family (ranked picks with their p against the search, plain picks without), "
                  "the combined book, NIFTY under its spaced name, sector and ETF lists read")
            hyg = cv.get("data_hygiene", {})
            check(hyg.get("failed_reconciliation") == 1 and hyg.get("sessions_with_bars", 0) > 1000 and "failed reconciliation" in rep
                  and 0.5 < cv["usable_share"] < cv["covered_share"] <= 1.0,
                  f"data checks counted and reported: {hyg}; covered {cv['covered_share']:.3f}, usable {cv['usable_share']:.3f}")
            V = pd.read_csv(runs[0] / "gates.csv")
            check(len(V) == 8 and not V["verdict"].astype(str).str.startswith("NOT RUN").any() and (V["disc_evaluable_share"] > 0.9).all(),
                  "with sector files every gate runs and judges nearly every pick")
            cells = pd.read_csv(runs[0] / "cells.csv")
            T = pd.read_parquet(runs[0] / "trades_selected.parquet")
            check(not ({"GOLDETFX", "QQQINDIA"} & set(T["symbol"].astype(str))) and set(T["symbol"].astype(str)) <= set(syms[6:]),
                  "the ETFs (by ISIN and by the ETF list, both with bars) and the stocks without bars never trade")
            cols_ok = {"gross", "net", "exit_kind", "entry_bar", "exit_bar", "risk_bp", "weight", "cell", "pick"} <= set(T.columns) and T.columns.is_unique
            sel = pd.read_csv(runs[0] / "selected.csv")
            b0 = sel[sel["pick"] == "best"].iloc[0]
            key = "|".join(map(str, (b0["side"], b0["score"], int(b0["or_bars"]), int(b0["top_n"]), b0["stop"])))
            Tb = T[(T["cell"] == key) & (T["pick"] == "best")]
            net_ok = len(Tb) and np.allclose(Tb["net"], BM.net_return(Tb["gross"].to_numpy(float), Tb["exit_kind"].to_numpy()), equal_nan=True)
            check(cols_ok and bool(net_ok), "trade file: one set of stop-free columns per cell, and each trade's net = its gross after costs")
            check(all(s in rep for s in ("## Verdicts", "## RV x MFE", "## Direction gates", "## NIFTY noise-boundary", "## Controls", "## Regimes",
                                         "## Limits", "Combined book", "fewer than N candidates"))
                  and len(cells) == 2 * 2 * (3 * 2 * 3 + 1 * 3 + 2 * 2 * 3 + 1 * 2 * 3),
                  f"report sections present; {len(cells)} cells (2 ranges x 2 sides x (36 ranked + 3 plain + 12 control + 6 benchmark) / 2)")
            led = (tmp / "panel" / "research_ledger.jsonl").read_text(encoding="utf-8").splitlines()
            check(len(led) == 1 and json.loads(led[0])["run"] == runs[0].name and json.loads(led[0])["tool"] == BM.CODE_VERSION,
                  "one line appended to the research ledger, naming the run")
            import hashlib as _h
            pv = summ.get("provenance", {})
            sums = dict(reversed(line.split("  ", 1)) for line in (runs[0] / "outputs.sha256").read_text(encoding="utf-8").splitlines())
            files_ok = all(_h.sha256((runs[0] / f_).read_bytes()).hexdigest() == h_ for f_, h_ in sums.items())
            um = pd.read_csv(tmp / "research2" / "bigmove" / "universe_by_month.csv")
            check(pv.get("code_sha256_16", {}).get("bigmove_study.py") == _h.sha256(Path(BM.__file__).read_bytes()).hexdigest()[:16]
                  and pv.get("pandas") == pd.__version__ and pv.get("numpy") == np.__version__ and len(pv.get("data_fingerprint", "")) == 16
                  and "report.md" in pv.get("outputs_sha256_16", {}) and "summary.json" in sums and files_ok and len(sums) == 13
                  and {"liquid", "with_bars", "usable", "usable_share", "candidates_L_r1"} <= set(um.columns)
                  and hyg.get("triggered_without_exit_price") == 0 and "Usable share of liquid stock-days by month" in rep
                  and "Fill audit of the selected cells" in rep,
                  f"provenance (code hash, library versions, data fingerprint {pv.get('data_fingerprint')}, output hashes - "
                  f"outputs.sha256 matches all {len(sums)} files), universe by month, and the fill / data audits are in the report")
        with_modules(dq, ic, body)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # every file present, but reconciliation fails on 1 day in 5: the run stops after pass 1 instead of building books
    tmp = Path(tempfile.mkdtemp())
    w = WW.make_world(n=12, seed=14, p_cat=0.04)
    try:
        write_root(tmp, w)

        def reconcile_bad(X, d, tp, tv):
            J = pd.DataFrame({"day": pd.Series(X["timestamp"].dt.normalize().unique())})
            J["ok"] = pd.Series(np.arange(len(J)) % 5 != 0, dtype=object)
            J.loc[J.index[1], "ok"] = None                                                # a missing verdict is not a pass
            return J
        dq, ic = stand_ins(reconcile_bad)

        def body2():
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    BM.main(["--root", str(tmp)])
                return None
            except SystemExit as e:
                return str(e)
        msg = with_modules(dq, ic, body2)
        check(msg is not None and "after reconciliation" in msg and not list((tmp / "research2" / "bigmove").glob("BM_*")),
              "full files but 1 session in 5 failing reconciliation: refused after pass 1, no books written")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def glue_zones():
    print("4b. zone-aware files and an unreadable file")
    keep_ds = BM.CFG["discovery_start"]
    BM.CFG["discovery_start"] = "2024-07-01"
    tmp = Path(tempfile.mkdtemp())
    try:
        w = WW.make_world(n=12, seed=16, p_cat=0.04)
        for D in list(w["daily"].values()) + [w["nifty_daily"]]:
            D["timestamp"] = pd.to_datetime(D["timestamp"]).dt.tz_localize("Asia/Kolkata")      # as the daily cache stores them
        for X in list(w["intra"].values()) + [w["nifty_bars"]]:
            X["timestamp"] = pd.to_datetime(X["timestamp"]).dt.tz_localize("Asia/Kolkata")
        write_root(tmp, w)
        (tmp / "intraday_3m" / "S011_3m.parquet").write_bytes(b"not a parquet file")

        def reconcile(X, d, tp, tv):                                  # the stand-in reconciles on the files as stored (zone-aware)
            return pd.DataFrame({"day": pd.Series(X["timestamp"].dt.normalize().unique())}).assign(ok=True)
        dq, ic = stand_ins(reconcile)

        def body():
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = BM.main(["--root", str(tmp), "--allow-partial-universe"])
            runs = sorted((tmp / "research2" / "bigmove").glob("BM_*"))
            summ = json.loads((runs[0] / "summary.json").read_text(encoding="utf-8")) if runs else {}
            T = pd.read_parquet(runs[0] / "trades_selected.parquet") if runs else pd.DataFrame()
            hyg = summ.get("coverage", {}).get("data_hygiene", {})
            first_bar = pd.read_parquet(tmp / "intraday_3m" / "S000_3m.parquet")["timestamp"].iloc[0]
            buf2 = io.StringIO()                                    # the same study again: a rerun, not fresh evidence
            with contextlib.redirect_stdout(buf2):
                BM.main(["--root", str(tmp), "--allow-partial-universe"])
            runs = sorted((tmp / "research2" / "bigmove").glob("BM_*"))
            summ2 = json.loads((runs[-1] / "summary.json").read_text(encoding="utf-8")) if len(runs) > 1 else {}
            rep2 = (runs[-1] / "report.md").read_text(encoding="utf-8") if len(runs) > 1 else ""
            led = [json.loads(x) for x in (tmp / "panel" / "research_ledger.jsonl").read_text(encoding="utf-8").splitlines()]
            return rc, hyg, T, summ, first_bar, buf.getvalue(), summ2, rep2, led, buf2.getvalue()
        rc, hyg, T, summ, fb, out, summ2, rep2, led, out2 = with_modules(dq, ic, body)
        check(len(led) == 2 and led[0]["fresh_confirmation"] and not led[1]["fresh_confirmation"] and "RERUN #2" in rep2
              and "NOT fresh evidence" in out2 and summ2.get("provenance", {}).get("data_fingerprint") == summ["provenance"]["data_fingerprint"],
              "a second run of the same study is stamped RERUN in the report, the console and the ledger (not fresh evidence); "
              "the same data gives the same data fingerprint")
        check(rc == 0 and hyg.get("unreadable_files") == 1 and hyg.get("failed_reconciliation") == 0 and len(T) > 0
              and "S011" not in set(T["symbol"].astype(str)) and summ["coverage"]["usable_share"] > 0.85 and "WARNING S011" in out,
              f"zone-aware (Asia/Kolkata) bar and daily files run end to end (first bar {fb}); the unreadable file is skipped with a "
              f"warning and counted ({hyg})")
    finally:
        BM.CFG["discovery_start"] = keep_ds
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    by_hand()
    stats_calibration()
    world_generator()
    worlds()
    look_ahead()
    glue()
    glue_zones()
    print()
    if FAILS:
        print(f"FAILED {len(FAILS)}:")
        for f in FAILS:
            print("  - " + f)
        return 1
    print(f"VERIFIED ({BM.CODE_VERSION})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
