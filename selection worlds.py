#!/usr/bin/env python3
"""
tests/selection_worlds.py - optional and slow (about 30 seconds a market, 28 markets): reproduces the numbers behind
amendment q of BIGMOVE_DECLARATION.json. Not part of the test suite; it changes nothing and writes nothing.

In 20 synthetic markets where buying everything pays and no ranking adds anything (thin counter-trend days, seeds
34-53), how often does a ranked pick (best RV, best MFE, best RVxMFE, either side) reach PROMISING or CHAMPION:
  before amendment q - its excess judged on its own lower bound (the cell was picked as the best of many);
  now                - its excess also judged against the search (max-t p over the side's ranked cells).
Then the same picks in planted markets (stocks in play, seeds 1, 2, 3, 5; short-only catalysts, seeds 4-7), where
the RV ranking is real: those verdicts must survive.

    python tests\\selection_worlds.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import test_bigmove_study as T          # noqa: E402  (the suite's worlds and settings: top N 3 / 6)

BM, WW = T.BM, T.WW
PC = ("PROMISING", "CHAMPION")
MARKETS = [("no ranking adds anything", dict(n=48, bar_start="2024-01-01", nifty_trend=True, beta=1.0, sigma=0.012, trend_drift=0.02),
            list(range(34, 54))),
           ("stocks in play (RV is real)", dict(n=48, p_cat=0.04, bar_start="2024-01-01"), [1, 2, 3, 5]),
           ("short-only catalysts (RV is real on the short side)", dict(n=48, p_cat=0.04, cat_mode="short_only"), [4, 5, 6, 7])]


def ranked_picks(R) -> list:
    """(side, pick, verdict before amendment q, verdict now, p against the search) of the per-score picks."""
    S = R["selected"]
    out = []
    for _, b in S[S["pick"].isin(["best rv", "best mfe", "best rvxmfe"])].iterrows():
        disc = {k[5:]: b[k] for k in b.index if k.startswith("disc_")}
        conf = {k[5:]: b[k] for k in b.index if k.startswith("conf_")}
        before = BM.verdict({**disc, "excess_padj": 0.0}, conf, b["disc_dsr"], ranked=True)   # the search check switched off
        out.append((b["side"], b["pick"], before, b["verdict"], float(b["disc_excess_padj"])))
    return out


def main() -> int:
    print(f"{BM.CODE_VERSION}: selection check by markets (amendment q)")
    for name, kw, seeds in MARKETS:
        print(name)
        n_before = n_now = 0
        for sd in seeds:
            t0 = time.time()
            P = ranked_picks(T.run_world(WW.make_world(seed=sd, **kw)))
            b_ = [p for p in P if p[2] in PC]
            a_ = [p for p in P if p[3] in PC]
            n_before += bool(b_)
            n_now += bool(a_)
            fmt = lambda L: ", ".join(f"{s} {pk} {v} (p {q:.3f})" for s, pk, v, q in L) or "none"
            if name.startswith("no ranking"):
                print(f"  seed {sd}: PROMISING / CHAMPION before: {fmt([(p[0], p[1], p[2], p[4]) for p in b_])}; "
                      f"now: {fmt([(p[0], p[1], p[3], p[4]) for p in a_])}  ({time.time() - t0:.0f}s)", flush=True)
            else:
                print(f"  seed {sd}: " + "; ".join(f"{p[0]} {p[1]} {p[2]} -> {p[3]} (p {p[4]:.3f})" for p in P)
                      + f"  ({time.time() - t0:.0f}s)", flush=True)
        print(f"  markets with a ranked PROMISING or CHAMPION: before {n_before} of {len(seeds)}, now {n_now} of {len(seeds)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
