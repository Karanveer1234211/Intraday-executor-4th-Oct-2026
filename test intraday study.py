#!/usr/bin/env python3
"""
tests/test_intraday_study.py - intraday_features v1 + intraday_study v1.3. Prints VERIFIED on success.

 1. By hand: VWAP and VPOC; limit fills (open below the level, touched, never); breakout fills (at the
    first-15-minute high, or at a gap open); descriptors of a hand-built session.
 2. Honest exits: a 5th session frozen at the lower circuit cannot fill a VWAP exit - it moves to the next
    unlocked open. The bracket with 3-minute ordering: target first, and both inside one bar = stop.
 3. PLANTED: every session dips in the first 30 minutes and recovers - buying later beats the open, and
    the catalogue protocol discovers AND confirms it.
 5. Declaration compliance: both engines and both rank groups covered; VWAP_DAY and the oracles never enter the
    protocol; only D's confirmations become forward lanes; F2 reports the entry gap; a breakout that gaps above
    the high fills at the open; the candidate set is frozen, reused, refused when edited, rebuilt only with a reason.
 4. ABSENT: random intraday paths and no overnight drift - no always-filled rule is confirmed (limit and
    breakout rules that hold cash when unfilled may legitimately look better in a zero-edge world: they skip
    the costs - reported, not judged).
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import stage_e_execution as EX         # noqa: E402
import intraday_features as IF         # noqa: E402
import intraday_study as IS            # noqa: E402

FAILS = []


def check(cond, msg):
    print(("  ok  " if cond else "  FAIL") + f"  {msg}")
    if not cond:
        FAILS.append(msg)


def session(day, opn, path):
    """125 three-minute bars from 09:15 following relative path values (len 125)."""
    t0 = pd.Timestamp(day) + pd.Timedelta(hours=9, minutes=15)
    c = opn * (1 + np.asarray(path, float))
    o = np.r_[opn, c[:-1]]
    return pd.DataFrame({"timestamp": [t0 + pd.Timedelta(minutes=3 * k) for k in range(125)], "open": o,
                         "high": np.maximum(o, c) * 1.0005, "low": np.minimum(o, c) * 0.9995, "close": c,
                         "volume": np.full(125, 1000.0)})


def world(planted: bool, seed: int, drift: float = 0.002):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2024-07-01", "2025-05-30")
    syms = [f"S{i:02d}" for i in range(24)]
    intra, daily = {}, {}
    for s in syms:
        px, parts = 100.0 * (1 + rng.random()), []
        for d in days:
            opn = px * (1 + drift + 0.004 * rng.standard_normal())
            if planted:                                   # dip to -1.5% by minute 30, recover to +0.3% by the close
                k = np.arange(125)
                path = np.where(k < 10, -0.015 * (k + 1) / 10, -0.015 + 0.018 * (k - 9) / 115)
                path = path + 0.0005 * rng.standard_normal(125)
            else:
                path = np.cumsum(0.0012 * rng.standard_normal(125))
            S = session(d, opn, path)
            parts.append(S)
            px = float(S["close"].iloc[-1])
        X = pd.concat(parts, ignore_index=True)
        intra[s] = X
        g = X.groupby(X["timestamp"].dt.normalize())
        D = pd.DataFrame({"timestamp": g.size().index, "open": g["open"].first().values, "high": g["high"].max().values,
                          "low": g["low"].min().values, "close": g["close"].last().values})
        daily[s] = EX.Bars.from_frame(D)
    cal = np.unique(np.concatenate([b.ts for b in daily.values()]))
    rows = []
    for d in days[25:-12]:
        for eng in ("D", "ENS"):
            for r, s in enumerate(rng.choice(syms, 5, replace=False), 1):
                rows.append({"signal_day": d, "symbol": s, "engine": eng, "rank": r, "traded": r <= 3})
    return pd.DataFrame(rows), daily, intra, cal


def main():
    print("1. by hand")
    d = pd.DataFrame({"timestamp": pd.date_range("2024-01-02 09:15", periods=10, freq="3min"),
                      "open": [10.0] * 10, "high": [11.0] * 10, "low": [9.0] * 10, "close": [10.0] * 10,
                      "volume": [1, 1, 1, 1, 1, 5, 5, 5, 5, 5]})
    d.loc[5:, ["high", "low", "close"]] = [[13.0, 11.0, 12.0]] * 5
    check(abs(IF.vwap(d) - (5 * 10 + 25 * 12) / 30) < 1e-12 and abs(IF.vpoc(d) - 12.0) < 1e-12,
          "VWAP (typical price, volume-weighted) and VPOC (busiest 15-minute bar) by hand")
    B = session("2024-01-03", 100.0, np.linspace(-0.001, -0.03, 125))
    px, ok = IS.limit_fill(B, 98.0)
    px2, ok2 = IS.limit_fill(B, 101.0)
    px3, ok3 = IS.limit_fill(B, 90.0)
    check(ok and px == 98.0 and ok2 and px2 == 100.0 and not ok3, "limit: touched -> the level; open already below -> the open; never -> no trade")
    U = session("2024-01-03", 100.0, np.r_[np.zeros(5), np.linspace(0.001, 0.02, 120)])
    top = float(U.iloc[:5]["high"].max())
    p4, ok4 = IS.orb_fill(U, 15)
    check(ok4 and abs(p4 - top) < 1e-9, "breakout: fills at the first-15-minute high when crossed")
    G = U.copy()
    G.loc[5, ["open", "high", "low", "close"]] = top * 1.02
    p5, ok5 = IS.orb_fill(G, 15)
    check(ok5 and abs(p5 - top * 1.02) < 1e-9, "breakout: a bar that opens above the high fills at its open (as declared)")
    dd = IF.descriptors(B, prev_close=99.0, prev_volumes=[125000.0] * 20)
    check(abs(dd["gap"] - (100 / 99 - 1)) < 1e-12 and abs(dd["rel_volume_20"] - 1.0) < 1e-12 and dd["minute_of_low"] == 372.0
          and dd["session_ret"] < 0, "descriptors: gap, relative volume, minute of the low, session return")

    print("2. honest exits and the bracket")
    P, daily, intra, cal = world(True, 1)
    s0 = "S00"
    b = daily[s0]
    e = 30
    days = intra[s0]["timestamp"].dt.normalize()
    sess = {s: intra[s0][days == pd.Timestamp(b.ts[e + s - 1])].copy() for s in range(1, 7)}
    j5 = e + 4
    lock = b.c[j5 - 1] * 0.95
    sess[5][["open", "high", "low", "close"]] = lock
    b2 = EX.Bars(b.ts, b.o.copy(), b.h.copy(), b.l.copy(), b.c.copy(), b.vol20, b.index)
    b2.o[j5] = b2.h[j5] = b2.l[j5] = b2.c[j5] = lock
    px_v = IS.exit_price("VWAP_DAY_5", b2, e, sess)
    check(abs(px_v - b2.o[j5 + 1]) < 1e-9, "a VWAP exit on a session frozen at the lower circuit moves to the next unlocked open")
    up = {1: session("2024-01-03", 100.0, np.r_[np.linspace(0, 0.04, 60), np.full(65, 0.04)])}
    for k in range(2, 6):
        up[k] = session("2024-01-03", 104.0, np.zeros(125))
    r_up = IS.bracket_intraday(b, e, up, 0.03, 0.02)
    check(abs(r_up - (0.03 - IS.COST)) < 1e-12, "3-minute bracket: the target is reached first -> +3% less costs")

    print("3. PLANTED: a 30-minute dip every session")
    res = IS.run(P, daily, intra, cal)
    Rall = res["protocol"]
    R = Rall[Rall["engine"] == "D"].set_index("rule")
    core = res["core"]
    cD = core[(core["engine"] == "D") & (core["group"] == "top3")].set_index("rule")
    check(cD.at["entry VWAP_30", "mean_bp"] > 50 and cD.at["entry VWAP_30", "lo_bp"] > 0,
          f"buying at the first-30-minute VWAP beats the open: {cD.at['entry VWAP_30', 'mean_bp']:+.0f} bp")
    check(bool(R.at["E:VWAP_30", "confirmed"]) and bool(R.at["E:TIME_30", "confirmed"]) and bool(R.at["E:VWAP_30", "forward_lane"]),
          f"the protocol discovers and confirms it for D -> forward lane ({int(R['confirmed'].sum())} rules confirmed)")
    print("5. declaration compliance")
    cov = set(zip(core["engine"], core["group"]))
    check(cov == {("D", "top3"), ("D", "ranks4_10"), ("ENS", "top3"), ("ENS", "ranks4_10")},
          "core menus cover D and the ensemble, each for the traded top 3 and ranks 4-10")
    check(not Rall["rule"].isin(["E:VWAP_DAY", "E:OPEN", "E:ORACLE_LOW", "X:CLOSE_5", "X:ORACLE_HIGH"]).any(),
          "VWAP_DAY, the baseline and the oracles never enter the protocol")
    RE = Rall[Rall["engine"] == "ENS"]
    check(RE["confirmed"].any() and not RE["forward_lane"].any(), "the ensemble's confirmations are reported but never forward lanes")
    f2 = res["findings"]["D_top3"]["F2_tug_of_war"]
    check(np.isfinite(f2["entry_gap_bp_not_earned"]) and set(res["descriptors"]["group"]) == {"top3", "ranks4_10"},
          f"F2 reports the entry gap ({f2['entry_gap_bp_not_earned']:+.1f} bp, not earned); descriptors for both rank groups")
    import tempfile, shutil
    tmp = Path(tempfile.mkdtemp())
    try:
        calls = []
        orig = IS.frozen_picks
        IS.frozen_picks = lambda root, daily, cal: (calls.append(1), P.head(50).copy())[1]
        c1, h1 = IS.frozen_candidates(tmp, daily, cal)
        c2, h2 = IS.frozen_candidates(tmp, daily, cal)
        check(len(calls) == 1 and h1 == h2 and len(c2) == 50, "candidates built once, then reused with the same fingerprint")
        fp = tmp / "research2" / "intraday" / "frozen_candidates.parquet"
        pd.read_parquet(fp).head(40).to_parquet(fp, index=False)
        try:
            IS.frozen_candidates(tmp, daily, cal)
            check(False, "an edited candidate file is refused")
        except SystemExit as e:
            check("changed since it was built" in str(e), "an edited candidate file is refused")
        c3, h3 = IS.frozen_candidates(tmp, daily, cal, "test: rebuild")
        arch = list((tmp / "research2" / "intraday").glob("frozen_candidates_*.parquet"))
        check(len(calls) == 2 and len(arch) == 1, "a rebuild needs a reason and keeps the old set beside it")
    finally:
        IS.frozen_picks = orig
        shutil.rmtree(tmp, ignore_errors=True)

    ok_all = {s_: set(X["timestamp"].dt.normalize().unique()) for s_, X in intra.items()}
    first = P[(P["engine"] == "D") & P["traded"]].iloc[0]
    e1 = cal[np.searchsorted(cal, np.datetime64(pd.Timestamp(first["signal_day"]), "ns")) + 1]
    ok_cut = {k: set(v) for k, v in ok_all.items()}
    ok_cut[first["symbol"]].discard(pd.Timestamp(e1).normalize())
    cnt = {}
    O1 = IS.pick_outcomes(P.head(12), daily, intra, cal, ["OPEN"], ["CLOSE_5", "VWAP_DAY_5"], ok_cut, cnt)
    O0 = IS.pick_outcomes(P.head(12), daily, intra, cal, ["OPEN"], ["CLOSE_5", "VWAP_DAY_5"], ok_all, {})
    check(cnt.get("entry_not_reconciled", 0) >= 1 and len(O1) < len(O0),
          "a pick whose entry session does not reconcile is excluded and counted")
    print("4. ABSENT: random intraday paths, no overnight drift")
    P0, d0, i0, c0 = world(False, 2, drift=0.0)
    res0 = IS.run(P0, d0, i0, c0)
    R0 = res0["protocol"]
    fill_dep = R0["rule"].str.contains("PULLBACK|LIMIT_|ORB_")
    always = R0[~fill_dep]
    n_conf, n_surv = int(always["confirmed"].sum()), int(always["discovery_survivor"].sum())
    check(n_conf == 0, f"no always-filled rule is confirmed ({n_surv} discovery survivors, {n_conf} confirmed of {len(always)})")
    print(f"        (fill-dependent rules, cash when unfilled: {int(R0[fill_dep]['confirmed'].sum())} of {int(fill_dep.sum())} "
          f"confirmed - skipping costs in a zero-edge world, as expected)")
    print()
    if FAILS:
        print(f"FAILED  {len(FAILS)} check(s):")
        for f in FAILS:
            print("   - " + f)
        return 1
    print(f"VERIFIED  {IS.CODE_VERSION} + {IF.CODE_VERSION}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
