#!/usr/bin/env python3
"""
tests/test_confirmation_study.py - confirmation_study v1. Prints VERIFIED on success.

 1. By hand: RSI and MACD on a rising series; a signal is None before anything trades; HIGHER_LOW needs two
    bars; GAP2_CONFIRM buys a small gap at the open.
 2. DIPS CONTINUE: picks that fall in the first 30 minutes keep falling - waiting for HOLD_OPEN is a winner.
 3. DIPS RECOVER: the early fallers are the best performers - HOLD_OPEN must NOT win (return or pain).
 4. NOISE: random paths - no rule wins at all.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import stage_e_execution as EX         # noqa: E402
import intraday_study as IS            # noqa: E402
import confirmation_study as CS        # noqa: E402

FAILS = []


def check(cond, msg):
    print(("  ok  " if cond else "  FAIL") + f"  {msg}")
    if not cond:
        FAILS.append(msg)


def session(day, opn, path, vol=1000.0):
    t0 = pd.Timestamp(day) + pd.Timedelta(hours=9, minutes=15)
    c = opn * (1 + np.asarray(path, float))
    o = np.r_[opn, c[:-1]]
    return pd.DataFrame({"timestamp": [t0 + pd.Timedelta(minutes=3 * k) for k in range(len(c))], "open": o,
                         "high": np.maximum(o, c) * 1.0004, "low": np.minimum(o, c) * 0.9996, "close": c,
                         "volume": np.full(len(c), vol)})


def world(kind: str, seed: int, ens: bool = False):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2024-07-01", "2025-05-30")
    syms = [f"S{i:02d}" for i in range(30)]
    k = np.arange(125)
    intra, daily, starts = {}, {}, {}
    for si, s in enumerate(syms):
        px, parts, kind_of_block, drift = 100.0, [], None, 0.0
        for di, d in enumerate(days):
            block_day = (di - si % 10) % 10
            if block_day == 0:                                  # an entry session: the type decides today's path and the drift after
                if kind == "noise":
                    path, drift = np.cumsum(0.0012 * rng.standard_normal(125)), 0.0
                else:
                    dip = rng.random() < 0.4
                    shape = np.where(k < 10, (k + 1) / 10, 1.0)
                    path = (-0.015 if dip else 0.008) * shape + 0.0004 * rng.standard_normal(125)
                    drift = {"continue": (-0.008 if dip else 0.006), "recover": (0.012 if dip else 0.002)}[kind]
                starts.setdefault(d, []).append(s)
            else:
                path = np.cumsum(0.0008 * rng.standard_normal(125))
            opn = px * (1 + (drift if block_day != 0 else 0.0) + 0.002 * rng.standard_normal())
            S = session(d, opn, path)
            parts.append(S)
            px = float(S["close"].iloc[-1])
        X = pd.concat(parts, ignore_index=True)
        intra[s] = X
        g = X.groupby(X["timestamp"].dt.normalize())
        daily[s] = EX.Bars.from_frame(pd.DataFrame({"timestamp": g.size().index, "open": g["open"].first().values,
                                                    "high": g["high"].max().values, "low": g["low"].min().values,
                                                    "close": g["close"].last().values}))
    cal = np.unique(np.concatenate([b.ts for b in daily.values()]))
    rows = []
    for di in range(25, len(days) - 8):
        for r, s in enumerate(starts.get(days[di + 1], [])[:3], 1):
            for eng in (("D", "ENS") if ens else ("D",)):
                rows.append({"signal_day": days[di], "symbol": s, "engine": eng, "rank": r, "traded": True})
    return pd.DataFrame(rows), daily, intra, cal


def main():
    IS.CFG["boot_B"] = 1000                     # faster bootstraps in tests; the rules are unchanged
    CS.CFG["boot_B_quantile"] = 200
    print("1. by hand")
    up = session("2024-01-03", 100.0, 0.03 * np.linspace(0.01, 1.0, 125) ** 2)          # accelerating: MACD rises
    prev = session("2024-01-02", 99.0, np.linspace(0.0, 0.01, 125))
    st = CS.state(up, prev, 99.9, 1e6, None)
    check(st["rsi"][-1] > 50 and bool(st["macd_up"][-1]), "RSI above 50 and MACD above its signal on an accelerating rise")
    check(CS.signal(st, "HOLD_OPEN", 0) is None and CS.signal(st, "HIGHER_LOW", 3) is False,
          "nothing has traded before 09:15 -> no signal; HIGHER_LOW needs two bars")
    st2 = CS.state(up, prev, 99.5, 1e6, None)                                    # gap +0.5%
    ok, px, k = CS.entry(st2, "GAP2_CONFIRM@15")
    check(ok and px == st2["open"] and k == 0, "GAP2_CONFIRM: a gap under 2% is bought at the open")
    check(len(CS.RULES) == 95, f"95 declared rules ({len(CS.RULES)})")

    print("2. DIPS CONTINUE")
    res = CS.run(*world("continue", 1, ens=True))
    R = res["rules"]
    RD = R[R["engine"] == "D"].set_index("rule")
    win = RD.loc[["HOLD_OPEN@15", "HOLD_OPEN@30"], "verdict"]
    check((win != "discarded").all(), f"waiting for HOLD_OPEN wins when dips keep falling ({dict(win)})")
    check(RD.at["HOLD_OPEN@30", "skipped_bp"] > 0, f"the skipped trades were losers: skipping saved {RD.at['HOLD_OPEN@30', 'skipped_bp']:+.0f} bp")
    RE = R[R["engine"] == "ENS"]
    check((RE["verdict"] != "discarded").any() and not RE["forward_lane"].any() and RD["forward_lane"].any(),
          "the ensemble's winners are reported but only D's become forward lanes")

    print("3. DIPS RECOVER")
    R3 = CS.run(*world("recover", 2))["rules"].set_index("rule")
    v3 = R3.loc[["HOLD_OPEN@15", "HOLD_OPEN@30", "HOLD_OPEN@WAIT"], "verdict"]
    check((v3 == "discarded").all(), f"HOLD_OPEN does not win when the early fallers recover ({dict(v3)})")
    check(R3.at["HOLD_OPEN@30", "skipped_bp"] < 0, f"skipping cost money: {R3.at['HOLD_OPEN@30', 'skipped_bp']:+.0f} bp")

    print("4. NOISE")
    R4 = CS.run(*world("noise", 3))["rules"]
    nw = R4[R4["verdict"] != "discarded"]
    check(len(nw) == 0, f"no rule wins on random paths ({len(nw)} of {len(R4)}: {list(nw['rule'])[:5]})")
    print()
    if FAILS:
        print(f"FAILED  {len(FAILS)} check(s):")
        for f in FAILS:
            print("   - " + f)
        return 1
    print(f"VERIFIED  {CS.CODE_VERSION}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
