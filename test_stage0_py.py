#!/usr/bin/env python3
"""
tests/test_stage0.py - stage0_persistence v1.0. Prints VERIFIED on success.

 1. By hand: costs per trade; every setup-side's trigger on hand-built sessions (signal at a bar's close, entry at the
    NEXT bar's open, a missing next bar enters at the following one, no entry after 14:30, time exit at 15:03); the
    plain trade; the H1 / H2 split and 2025 excluded; the 20% gap guard; Spearman, the permutation p-value (exact
    floor, and roughly uniform on independent data) and Holm.
 2. Synthetic markets (real dates, 2021-06 to 2025-03; stocks differ in volatility and in their own persistent
    open-to-close drift; U-shaped volatility and volume, occasional volume spikes; continuous price paths):
      PLANTED  15% of stocks trend after the first hour, 15% revert, the same stocks in H1 and H2 -> must PASS, with
               first-hour momentum among the passing setup-sides and the planted trenders in its top decile
      NONE     no stock-specific behaviour -> must FAIL ('no persistent stock-specific behaviour')
      MOVED    the same trenders and reverters, but reassigned to other stocks at 2023-06-01 (behaviour exists in each
               half but does not persist) -> must FAIL
 3. LOOK-AHEAD: changing a session's bars from bar m on (m across the day), its daily bar and every later day leaves
    every decision to enter at or before bar m unchanged (and every entry price before bar m), while outcomes change;
    earlier days are untouched; changing anything from 2025 on changes nothing. Planted leaks (the day's own daily
    high / low / ATR; a VWAP that sees the next bar) are caught.
 4. main() end to end with stand-in data_quality / intraday_cache modules: writes only <root>\\research2\\stage0\\
    and one ledger line; a stock without a 3-minute file is counted; a failed reconciliation is counted; a second
    run with every 2025 bar and daily row changed gives identical results and is stamped RERUN.
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
import time
import types
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))           # open_close
sys.path.append(str(HERE.parent.parent))       # bigmove_deploy (PYTHONPATH should already have it)

import stage0_persistence as S                 # noqa: E402

BM = S.BM
NB = S.NB
FAILS = []


def check(cond, msg):
    print(("  ok  " if cond else "  FAIL") + f"  {msg}")
    if not cond:
        FAILS.append(msg)


# ----------------------------------------------------------------------
# 1. by hand
# ----------------------------------------------------------------------
D0, D1 = pd.Timestamp("2022-03-01"), pd.Timestamp("2022-03-02")


def one_session(p=100.0):
    """Flat session at price p (high / low 0.01 around it), volume 1000 a bar, as 1 x 125 matrices."""
    o = np.full(NB, p)
    return {"open": o[None].copy(), "high": (o + 0.01)[None].copy(), "low": (o - 0.01)[None].copy(), "close": o[None].copy(),
            "volume": np.full((1, NB), 1000.0)}


def frame(pdh=101.0, pdl=99.0, pdc=100.0, atr=0.02, d0=D0, d1=D1):
    return pd.DataFrame({"day": [d0, d1], "high": [pdh, 0.0], "low": [pdl, 0.0], "close": [pdc, 0.0], "atr14": [atr, np.nan]})


def trades_of(B, F=None, day=D1):
    F = frame() if F is None else F
    T, P = S.stock_trades(F, np.array([np.datetime64(day, "ns")]), B, np.array([True, True]))
    return T, P


def sig(T, name):
    """(signal bar, entry bar, entry price, gross) of setup-side `name`, or None."""
    r = T[T["ss"] == S.SS.index(name)]
    return None if not len(r) else (int(r["sig"].iloc[0]), int(r["ent"].iloc[0]), float(r["entry"].iloc[0]), float(r["gross"].iloc[0]))


def setbar(B, k, o=None, h=None, l=None, c=None, v=None):
    for key, x in (("open", o), ("high", h), ("low", l), ("close", c), ("volume", v)):
        if x is not None:
            B[key][0, k] = x


def by_hand():
    print("1. by hand")
    check(abs(S.TRADE_COST * 1e4 - 12.49) < 0.01, f"cost a trade = {S.TRADE_COST * 1e4:.3f} bp (4.49 round trip + 5 entry + 3 time exit)")
    check(S.X_BAR == 116 and S.E_LAST == 105, "time exit = open of the 15:03 bar (116); last entry = the 14:30 bar (105)")
    # ORC long: bar 7 closes above the opening-range high -> entry at bar 8's open; exit at the 15:03 open
    B = one_session()
    setbar(B, 7, h=100.6, c=100.5)
    setbar(B, 8, o=100.6, h=100.7)
    for k in range(S.X_BAR, NB):
        setbar(B, k, o=101.0, h=101.01, c=101.0, l=100.99)
    T, P = trades_of(B)
    r = sig(T, "ORC_L")
    check(r is not None and r[:3] == (7, 8, 100.6) and abs(r[3] - (101.0 / 100.6 - 1)) < 1e-12,
          f"ORC_L: close above the 09:15-09:30 high at bar 7 -> entry at bar 8's open 100.6, exit 101.0 at 15:03 ({r})")
    rr = T[T["ss"] == S.SS.index("ORC_L")]
    check(abs(float(rr["net"].iloc[0]) - (101.0 / 100.6 - 1 - S.TRADE_COST)) < 1e-12, "net = gross - 12.49 bp")
    check(sig(T, "ORC_S") is None and sig(T, "ORF_L") is None, "no short break, no failure on that session")
    check(len(P) == 1 and abs(float(P["gross"].iloc[0]) - (101.0 / 100.0 - 1)) < 1e-12, "plain trade: first open 100 to the 15:03 open 101")
    B2 = {k: v.copy() for k, v in B.items()}
    for key in B2:
        B2[key][0, 8] = np.nan
    r = sig(trades_of(B2)[0], "ORC_L")
    check(r is not None and r[:3] == (7, 9, 100.0), f"bar 8 missing -> entry at bar 9's open ({r})")
    B3 = one_session()
    setbar(B3, 105, h=100.6, c=100.5)
    check(sig(trades_of(B3)[0], "ORC_L") is None, "a signal at bar 105 (14:30 close) would enter after 14:30 -> no trade")
    B3 = one_session()
    setbar(B3, 104, h=100.6, c=100.5)
    r = sig(trades_of(B3)[0], "ORC_L")
    check(r is not None and r[:2] == (104, 105), f"a signal at bar 104 enters at bar 105 ({r})")
    B3 = one_session()
    setbar(B3, 3, h=100.8, c=100.7)
    setbar(B3, 4, c=100.0)
    check(sig(trades_of(B3)[0], "ORC_L") is None, "a high inside the opening range is part of the range, not a break")
    # ORF short: closes above the range at bar 6, back below its high at bar 9
    B = one_session()
    setbar(B, 6, h=100.5, c=100.4)
    setbar(B, 7, h=100.5, c=100.3)
    setbar(B, 8, h=100.4, c=100.2)
    setbar(B, 9, c=100.0)
    T = trades_of(B)[0]
    check(sig(T, "ORF_S") is not None and sig(T, "ORF_S")[:2] == (9, 10) and sig(T, "ORC_L")[:2] == (6, 7),
          f"ORF_S: break above at bar 6, close back inside at bar 9 -> entry bar 10 ({sig(T, 'ORF_S')}); ORC_L took bar 6")
    # gaps: previous close 100, ATR 2% -> threshold 0.2 x 2% = 0.4%
    B = one_session(100.6)
    setbar(B, 4, c=100.7)
    T = trades_of(B)[0]
    check(sig(T, "GAPC_L") is not None and sig(T, "GAPC_L")[:2] == (4, 5) and sig(T, "GAPF_S") is None,
          "gap +0.6% and the 09:27 bar closes above the open -> GAPC_L at 09:30 (bar 5); no fade")
    B = one_session(100.6)
    setbar(B, 4, c=100.5)
    T = trades_of(B)[0]
    check(sig(T, "GAPF_S") is not None and sig(T, "GAPF_S")[:2] == (4, 5) and sig(T, "GAPC_L") is None,
          "gap +0.6% and the 09:27 bar closes below the open -> GAPF_S at 09:30")
    B = one_session(99.4)
    setbar(B, 4, c=99.5)
    T = trades_of(B)[0]
    check(sig(T, "GAPF_L") is not None and sig(T, "GAPC_S") is None, "gap -0.6%, first 15 minutes up -> GAPF_L")
    B = one_session(100.3)
    setbar(B, 4, c=100.5)
    check(sig(trades_of(B)[0], "GAPC_L") is None, "gap +0.3% (under 0.2 ATR) -> no gap trade")
    # first-hour momentum: +0.7% at 10:15 (threshold 0.25 x 2% = 0.5%)
    B = one_session()
    setbar(B, 19, h=100.71, c=100.7)
    T = trades_of(B)[0]
    check(sig(T, "FHM_L") is not None and sig(T, "FHM_L")[:2] == (19, 20) and sig(T, "FHM_S") is None, "FHM_L: +0.7% at 10:15 -> entry 10:15 (bar 20)")
    B = one_session()
    setbar(B, 19, l=99.29, c=99.3)
    check(sig(trades_of(B)[0], "FHM_S") is not None, "FHM_S: -0.7% at 10:15")
    B = one_session()
    setbar(B, 19, l=99.59, c=99.6)
    check(sig(trades_of(B)[0], "FHM_S") is None, "-0.4% at 10:15 (under 0.25 ATR) -> no FHM_S")
    # previous-day levels (PDH 101, PDL 99)
    B = one_session()
    setbar(B, 30, h=101.3, c=101.2)
    T = trades_of(B)[0]
    check(sig(T, "PDB_L") is not None and sig(T, "PDB_L")[:2] == (30, 31), "PDB_L: first close above PDH at bar 30")
    B = one_session(101.5)
    setbar(B, 30, h=101.8, c=101.7)
    check(sig(trades_of(B)[0], "PDB_L") is None, "opened above PDH -> no PDB_L (that is a gap, not a break)")
    B = one_session()
    for k in range(10, 15):
        setbar(B, k, l=98.8, c=98.9)
    setbar(B, 15, c=99.1)
    T = trades_of(B)[0]
    check(sig(T, "PDR_L") is not None and sig(T, "PDR_L")[:2] == (15, 16) and sig(T, "PDB_S")[:2] == (10, 11),
          f"PDR_L: closed below PDL at bar 10, back above at bar 15 -> entry 16 ({sig(T, 'PDR_L')}); PDB_S took bar 10")
    # VWAP stretch: from bar 30 the price sits 1.5% under a VWAP near 100 (threshold 0.4 x 2% = 0.8%)
    B = one_session()
    for k in range(30, NB):
        setbar(B, k, o=98.5, h=98.51, l=98.49, c=98.5)
    T = trades_of(B)[0]
    check(sig(T, "VWR_L") is not None and sig(T, "VWR_L")[:2] == (30, 31), f"VWR_L: first close 0.8% under VWAP at bar 30 ({sig(T, 'VWR_L')})")
    # compression then break: 45 sessions whose 10:15-11:15 box spans 0.2% .. 1.1%, then a session with a 0.1% box that
    # breaks up at bar 50 (narrow: under its 60-session 30th percentile) and one with a 0.6% box (not narrow)
    days = pd.bdate_range("2022-03-01", periods=48)
    Bm = {k: np.repeat(v, 47, 0) for k, v in one_session().items()}
    for j in range(45):
        Bm["high"][j, 25] = 100.0 + 0.2 + 0.02 * j
    for j in (45, 46):
        Bm["close"][j, 50], Bm["high"][j, 50] = 101.0, 101.01
    Bm["high"][45, 25] = 100.09
    Bm["high"][46, 25] = 100.6
    F = pd.DataFrame({"day": days, "high": 102.0, "low": 98.0, "close": 100.0, "atr14": 0.02})
    T, _ = S.stock_trades(F, np.asarray(days[1:], dtype="datetime64[ns]"), Bm, np.ones(len(days), bool))
    c = T[T["ss"] == S.SS.index("CMP_L")]
    check(len(c) == 1 and pd.Timestamp(c["day"].iloc[0]) == days[46] and (int(c["sig"].iloc[0]), int(c["ent"].iloc[0])) == (50, 51),
          f"CMP_L: a box under the stock's own 30th percentile, first close above it at bar 50 -> entry bar 51; a wider box -> nothing ({len(c)} trade)")
    B = one_session()
    setbar(B, 50, h=101.4, c=101.3)
    check(sig(trades_of(B)[0], "CMP_L") is None, "no box history (fewer than 40 earlier sessions) -> no compression trade")
    # volume spike: 12 quiet sessions, then a 5x bar-8 volume on an up bar
    days = pd.bdate_range("2022-03-01", periods=14)
    Bm = {k: np.repeat(v, 13, 0) for k, v in one_session().items()}
    Bm["volume"][12, 8] = 5000.0
    Bm["close"][12, 8], Bm["high"][12, 8] = 100.2, 100.21
    Bm["volume"][0, 8] = 5000.0                                                   # no history yet on the first session
    Bm["close"][0, 8], Bm["high"][0, 8] = 100.2, 100.21
    F = pd.DataFrame({"day": days, "high": 101.0, "low": 99.0, "close": 100.0, "atr14": 0.02})
    T, _ = S.stock_trades(F, np.asarray(days[1:], dtype="datetime64[ns]"), Bm, np.ones(len(days), bool))
    v = T[T["ss"] == S.SS.index("VSF_L")]
    check(len(v) == 1 and pd.Timestamp(v["day"].iloc[0]) == days[13] and int(v["sig"].iloc[0]) == 8,
          "VSF_L: a 5x bar-slot volume on an up bar fires once there is history (not on the first session)")
    # windows, 2025 and the gap guard
    check(list(S.half_of(pd.to_datetime(["2021-09-30", "2021-10-01", "2023-05-31", "2023-06-01", "2024-12-31", "2025-01-01"])))
          == ["", "H1", "H1", "H2", "H2", ""], "H1 2021-10-01..2023-05-31, H2 2023-06-01..2024-12-31, nothing else")
    B = one_session()
    setbar(B, 19, h=100.71, c=100.7)
    T, P = trades_of(B, frame(d0=pd.Timestamp("2024-12-31"), d1=pd.Timestamp("2025-01-01")), day=pd.Timestamp("2025-01-01"))
    check(len(T) == 0 and len(P) == 0, "a 2025 session gives no trade and no plain trade")
    B = one_session(126.0)
    setbar(B, 19, h=126.9, c=126.9)
    T, P = trades_of(B)
    check(len(T) == 0 and len(P) == 0, "open 26% from the previous close (split-basis mismatch) -> session dropped")
    B = one_session()
    T, P = trades_of(B, frame().assign(atr14=[np.nan, np.nan]))
    check(len(T) == 0 and len(P) == 0, "no ATR at the previous close -> session dropped")
    # statistics
    rng = np.random.default_rng(3)
    x, y = rng.normal(size=60), rng.normal(size=60)
    y[:5] = y[0]                                                                    # ties
    check(abs(S.spearman(x, y) - pd.DataFrame({"x": x, "y": y}).corr(method="spearman").iloc[0, 1]) < 1e-12, "Spearman = pandas' (with ties)")
    rho, p = S.perm_pvalue(x, x * 2 + 1, 2000, np.random.default_rng(1))
    check(abs(rho - 1) < 1e-12 and abs(p - 1 / 2001) < 1e-12, f"identical ranks: rho 1, p = 1/(1+2000) ({p:.5f})")
    ps = np.array([S.perm_pvalue(rng.normal(size=50), rng.normal(size=50), 400, np.random.default_rng(i))[1] for i in range(300)])
    check(0.02 <= (ps <= 0.05).mean() <= 0.09 and 0.40 <= (ps <= 0.5).mean() <= 0.60,
          f"independent data: p <= 0.05 in {(ps <= 0.05).mean():.1%}, p <= 0.5 in {(ps <= 0.5).mean():.1%} of 300 tries")
    h = S.holm(np.array([0.01, 0.04, 0.03, 0.2]))
    check(np.allclose(h, [0.04, 0.09, 0.09, 0.2]), f"Holm by hand: {h}")


# ----------------------------------------------------------------------
# 2. synthetic markets
# ----------------------------------------------------------------------
OFF = pd.to_timedelta(555 + 3 * np.arange(NB), unit="m")
USHAPE = np.r_[np.linspace(1.8, 0.8, 40), np.full(45, 0.7), np.linspace(0.8, 1.4, 40)]
USHAPE = USHAPE / USHAPE.mean()
VSHAPE = np.sqrt(USHAPE / USHAPE.mean())          # volatility is U-shaped too (busy open and close, quiet midday)


def _bars(o, rets, s_bar, u1, u2):
    """Bars of continuous paths, all sessions at once: each bar's high / low are the exact max / min of a Brownian bridge
    (log price, per-bar sd s_bar) between its open and close."""
    lc = np.log(o)[:, None] + np.cumsum(rets, 1)
    lo_ = np.concatenate([np.log(o)[:, None], lc[:, :-1]], 1)
    s2 = np.asarray(s_bar, float) ** 2
    hx = (lo_ + lc + np.sqrt((lc - lo_) ** 2 - 2 * s2 * np.log(u1))) / 2
    lx = (lo_ + lc - np.sqrt((lc - lo_) ** 2 - 2 * s2 * np.log(u2))) / 2
    return np.exp(lo_), np.exp(hx), np.exp(lx), np.exp(lc)


class World:
    """n stocks, daily bars from `start`, 3-minute bars from `bar_start`. Every stock has its own volatility, gap size and
    persistent open-to-close drift (no setup cares about those). trait: 'none'; 'persistent' - a share of stocks trends
    after the first hour (rest-of-day drift = tau x the first hour's return; tau_up) and a share reverts (tau_dn), the
    same stocks in H1 and H2; 'moved' - the same trait values, reassigned to other stocks from H2's first day."""

    def __init__(self, n=80, seed=0, trait="none", start="2021-06-01", bar_start="2021-10-01", end="2025-03-31",
                 tau_up=1.0, tau_dn=-0.7, share=0.15, sig=(0.012, 0.03), drift_sd=0.0005):
        self.n, self.trait, self.sig, self.drift_sd = n, trait, sig, drift_sd
        self.days = pd.bdate_range(start, end)
        self.bstart = pd.Timestamp(bar_start)
        ss = np.random.SeedSequence(seed)
        self.seeds = ss.spawn(n)
        r = np.random.default_rng(ss.spawn(1)[0])
        k = int(round(share * n))
        cls = np.zeros(n)
        perm = r.permutation(n)
        cls[perm[:k]], cls[perm[k:2 * k]] = tau_up, tau_dn
        self.tau1 = cls if trait != "none" else np.zeros(n)
        self.tau2 = (cls[r.permutation(n)] if trait == "moved" else cls) if trait != "none" else np.zeros(n)
        self.trenders = {f"S{i:03d}" for i in np.flatnonzero(cls == tau_up)}

    def stock(self, i, alter=None):
        """(symbol, daily frame, bar days, bar matrices). alter(days, daily_arrays, B) may change the generated data."""
        g = np.random.default_rng(self.seeds[i])
        T = len(self.days)
        p0, sig, drift = g.uniform(300, 2000), g.uniform(*self.sig), g.normal(0, 1.0) * self.drift_sd
        vol0 = 2e9 / p0
        gaps = g.normal(0, 0.4 * sig, T)
        noise = g.normal(0, 1.0, (T, NB))
        vnoise = g.lognormal(0, 0.3, (T, NB)) * np.where(g.random((T, NB)) < 0.01, g.lognormal(1.4, 0.4, (T, NB)), 1.0)   # 1% spike bars
        u = 1.0 - g.random((T, 2, NB))
        sb = sig / np.sqrt(NB) * VSHAPE
        rets = noise * sb + drift / NB
        tau = np.where(self.days >= S.H2[0], self.tau2[i], self.tau1[i])
        if np.any(tau != 0):
            r1 = np.exp(rets[:, :20].sum(1)) - 1                 # the first hour's return (to the 10:12 bar's close)
            rets[:, 20:S.X_BAR] += (tau * r1 / (S.X_BAR - 20))[:, None]
        lo0 = np.log(p0) + np.cumsum(gaps) + np.r_[0.0, np.cumsum(rets.sum(1))[:-1]]
        O, H, L, C = _bars(np.exp(lo0), rets, sb[None, :], u[:, 0], u[:, 1])
        V = vol0 / NB * USHAPE[None, :] * vnoise
        B = {"open": O, "high": H, "low": L, "close": C, "volume": V}
        daily = {"timestamp": self.days, "open": O[:, 0], "high": H.max(1), "low": L.min(1), "close": C[:, -1], "volume": V.sum(1)}
        keep = np.asarray(self.days >= self.bstart)
        if alter is not None:
            alter(self.days, daily, B)
        bdays = np.asarray(self.days[keep], dtype="datetime64[ns]")
        return f"S{i:03d}", pd.DataFrame(daily), bdays, {k: v[keep] for k, v in B.items()}

    def intra(self, bdays, B) -> pd.DataFrame:
        """The bar matrices as a 3-minute file (timestamp = bar start, IST, naive)."""
        ts = (pd.DatetimeIndex(bdays).to_numpy()[:, None] + OFF.to_numpy()[None, :]).ravel()
        return pd.DataFrame({"timestamp": ts, **{k: B[k].ravel() for k in ("open", "high", "low", "close", "volume")}})


def world_trades(w: World):
    T_all, P_all = [], []
    for i in range(w.n):
        sym, daily, bdays, B = w.stock(i)
        F = BM.daily_features(daily)
        T, P = S.stock_trades(F, bdays, B, BM.liquid_ok(F))
        T_all.append(T.assign(sym=sym))
        P_all.append(P.assign(sym=sym))
    trades, plain = pd.concat(T_all, ignore_index=True), pd.concat(P_all, ignore_index=True)
    trades["sym"], plain["sym"] = trades["sym"].astype("category"), plain["sym"].astype("category")
    return trades, plain


def run_world(w: World):
    trades, plain = world_trades(w)
    ps = S.per_stock(trades, plain)
    R = S.persistence(ps, trades)
    return R, S.shortlist(R, ps, trades, plain), ps, trades


def _line(R):
    keep = R[R["leg1_persistent"] | R["leg2_h2_positive"]]
    return "; ".join(f"{r.setup_side} rho {r.rho:+.2f} Holm p {r.holm_p:.4f} top H2 lo {r.top_h2_lo_bp:+.1f}" for r in keep.itertuples()) or "nothing on either leg"


def worlds():
    print("2. synthetic markets (80 stocks, 2021-06 to 2025-03)")
    t0 = time.time()
    w = World(n=80, seed=1, trait="persistent")
    R, SL, ps, trades = run_world(w)
    passed = list(R.loc[R["passes"], "setup_side"])
    ntr = trades.groupby(["sym", "ss"], observed=True).size()
    check(int(R["eligible_stocks"].min()) >= 30, f"every setup-side has >= 30 stocks with >= 30 trades per half (min {int(R['eligible_stocks'].min())}, "
          f"median trades per stock and setup-side over both halves {int(ntr.median())})")
    check(bool(R["passes"].any()), f"PLANTED: PASS ({', '.join(passed)})")
    check({"FHM_L", "FHM_S"} <= set(passed), "PLANTED: first-hour momentum passes on both sides")
    for name in ("FHM_L", "FHM_S"):
        r = R[R["setup_side"] == name].iloc[0]
        top = set(r["top_stocks"].split())
        check(len(top & w.trenders) >= 0.75 * len(top), f"PLANTED {name}: {len(top & w.trenders)} of the {len(top)} top-decile stocks are planted "
              f"trenders (rho {r['rho']:+.2f}, H2 {r['top_h2_net_bp_trade']:+.1f} bp/trade [{r['top_h2_lo_bp']:+.1f}, {r['top_h2_hi_bp']:+.1f}] a trade-day)")
        sl = SL[SL["setup_side"] == name]
        check(len(sl) == S.CFG["shortlist_n"] and len(set(sl["symbol"].head(10)) & w.trenders) >= 8,
              f"PLANTED {name}: shortlist of {len(sl)}, {len(set(sl['symbol'].head(10)) & w.trenders)} of its first 10 are trenders")
    print(f"     ({time.time() - t0:.0f} s)")
    for trait, seed in (("none", 2), ("none", 3), ("moved", 4)):
        t0 = time.time()
        R, SL, _, _ = run_world(World(n=80, seed=seed, trait=trait))
        check(not R["passes"].any() and not len(SL), f"{trait.upper()} (seed {seed}): no persistent stock-specific behaviour - {_line(R)}")
        print(f"        (leg 1 alone: {int(R['leg1_persistent'].sum())} setup-sides; leg 2 alone: {int(R['leg2_h2_positive'].sum())}; {time.time() - t0:.0f} s)")


# ----------------------------------------------------------------------
# 3. look-ahead
# ----------------------------------------------------------------------
def perturber(t: pd.Timestamp, m: int, seed: int):
    """Change day t's bars from bar m on, day t's daily row and every later day (bars and daily rows)."""
    def alter(days, daily, B):
        g = np.random.default_rng(seed)
        di = int(np.flatnonzero(days == t)[0])
        f = np.exp(g.normal(0, 0.03, (len(days), NB)))
        mask = np.zeros((len(days), NB), bool)
        mask[di, m:] = True
        mask[di + 1:, :] = True
        for k in ("open", "close"):
            B[k] = np.where(mask, B[k] * f, B[k])
        B["high"] = np.where(mask, np.maximum(B["high"] * f, np.maximum(B["open"], B["close"])), B["high"])
        B["low"] = np.where(mask, np.minimum(B["low"] * f, np.minimum(B["open"], B["close"])), B["low"])
        B["volume"] = np.where(mask, B["volume"] * np.exp(g.normal(0, 1.0, B["volume"].shape)), B["volume"])
        for k, s_ in (("high", 1.04), ("low", 0.95), ("close", 1.03), ("volume", 3.0)):
            daily[k] = np.asarray(daily[k], float).copy()
            daily[k][di:] = daily[k][di:] * s_
    return alter


def stock_run(w: World, i: int, alter=None):
    sym, daily, bdays, B = w.stock(i, alter)
    F = BM.daily_features(daily)
    return S.stock_trades(F, bdays, B, BM.liquid_ok(F))


def lookahead_cases(w, cases):
    """For each (stock, day, m): (decisions unchanged, earlier days unchanged, outcomes changed)."""
    out = []
    base = {}
    for i, t, m in cases:
        if i not in base:
            base[i] = stock_run(w, i)[0]
        A = base[i]
        Bt = stock_run(w, i, perturber(t, m, seed=i * 1000 + m))[0]
        key = ["ss", "sig", "ent"]
        a_t, b_t = A[A["day"] == t], Bt[Bt["day"] == t]
        dec_a = a_t[a_t["ent"] <= m].sort_values("ss")[key].to_numpy()
        dec_b = b_t[b_t["ent"] <= m].sort_values("ss")[key].to_numpy()
        pa = a_t[a_t["ent"] < m].sort_values("ss")["entry"].to_numpy()
        pb = b_t[b_t["ent"] < m].sort_values("ss")["entry"].to_numpy()
        same_dec = dec_a.shape == dec_b.shape and bool((dec_a == dec_b).all()) and pa.shape == pb.shape and np.allclose(pa, pb, rtol=0, atol=0)
        ea, eb = A[A["day"] < t].reset_index(drop=True), Bt[Bt["day"] < t].reset_index(drop=True)
        same_early = len(ea) == len(eb) and bool((ea[["ss", "sig", "ent"]].to_numpy() == eb[["ss", "sig", "ent"]].to_numpy()).all()) \
            and np.allclose(ea["gross"].to_numpy(float), eb["gross"].to_numpy(float), rtol=0, atol=0)
        la, lb = A[A["day"] >= t], Bt[Bt["day"] >= t]
        changed = len(la) != len(lb) or not np.allclose(la["gross"].to_numpy(float), lb["gross"].to_numpy(float))
        out.append((same_dec, same_early, changed, len(dec_a)))
    return out


def lookahead():
    print("3. look-ahead")
    w = World(n=4, seed=5, trait="persistent", tau_up=1.0, share=0.25)
    bdays = pd.DatetimeIndex(w.days[w.days >= w.bstart])
    dpick = [bdays[j] for j in (40, 200, 380, 430, 600, 790)]
    ms = [1, 4, 5, 6, 12, 20, 21, 30, 41, 60, 90, 101, 105, 106]
    cases = [(i, t, m) for i in range(3) for t in dpick for m in ms]
    for i in range(3):                                   # plus a cut at every entry bar of those days (the entry bar itself changes)
        T = stock_run(w, i)[0]
        cases += sorted({(i, pd.Timestamp(d), int(e)) for d, e in zip(T["day"], T["ent"]) if pd.Timestamp(d) in dpick} - set(cases))
    res = lookahead_cases(w, cases)
    n_dec = sum(r[3] for r in res)
    check(all(r[0] for r in res), f"{len(cases)} cuts (3 stocks x 6 days x bar m in {ms}, and at every entry bar): every decision to enter "
          f"at or before bar m and every entry price before bar m is unchanged ({n_dec} decisions compared)")
    check(all(r[1] for r in res), "every earlier day's trades are identical, outcomes included")
    check(sum(r[2] for r in res) >= 0.9 * len(res), f"the perturbation is not empty: outcomes changed in {sum(r[2] for r in res)} of {len(res)} cuts")
    hit = {name: 0 for name in S.SS}
    for i in range(3):
        T = stock_run(w, i)[0]
        for j, c in T.groupby("ss").size().items():
            hit[S.SS[int(j)]] += int(c)
    check(min(hit.values()) > 0, f"every setup-side traded in the look-ahead stocks (fewest: {min(hit, key=hit.get)} {min(hit.values())})")

    def after_2024(days, daily, B):
        late = np.asarray(days > S.H2[1])
        for k in ("open", "high", "low", "close"):
            B[k][late] *= 1.37
        B["volume"][late] *= 5.0
        for k in ("open", "high", "low", "close", "volume"):
            daily[k] = np.where(late, np.asarray(daily[k], float) * 1.37, daily[k])
    same25 = True
    for i in range(3):
        (Ta, Pa), (Tb, Pb) = stock_run(w, i), stock_run(w, i, after_2024)
        same25 &= Ta.equals(Tb) and Pa.equals(Pb)
    check(same25, "changing every 2025 bar and daily row changes no trade and no plain trade")
    # planted leaks must be caught
    keep_prev = S._prev
    S._prev = lambda F, trow, col: np.where(trow >= 0, F[col].to_numpy(float)[np.maximum(trow, 0)], np.nan)   # the day's own row
    try:
        res = lookahead_cases(w, [(i, t, m) for i in range(3) for t in dpick for m in (1, 21, 60)])
    finally:
        S._prev = keep_prev
    check(not all(r[0] for r in res), f"planted leak caught: PDH / PDL / PDC / ATR from the day's own daily row ({sum(not r[0] for r in res)} cuts flag it)")
    keep_vwap = BM.session_vwap
    BM.session_vwap = lambda H, L, C, V: np.concatenate([keep_vwap(H, L, C, V)[:, 1:], keep_vwap(H, L, C, V)[:, -1:]], 1)
    try:
        leaky = []
        for i in range(3):                               # cut at the entry bar of the leaky VWAP trades
            T = stock_run(w, i)[0]
            v = T[T["ss"].isin([S.SS.index("VWR_L"), S.SS.index("VWR_S")])]
            leaky += [(i, pd.Timestamp(d), int(e)) for d, e in zip(v["day"].iloc[::25], v["ent"].iloc[::25])]
        res = lookahead_cases(w, leaky)
    finally:
        BM.session_vwap = keep_vwap
    check(not all(r[0] for r in res), f"planted leak caught: a VWAP that includes the next bar ({sum(not r[0] for r in res)} cuts flag it)")


# ----------------------------------------------------------------------
# 4. main() end to end
# ----------------------------------------------------------------------
def stand_ins(reconcile):
    dq = types.ModuleType("data_quality")
    dq._paths = lambda root, s: (Path(root) / f"{s}_daily.parquet", Path(root) / f"{s}_daily.ok.json")
    dq.discover_symbols = lambda root: sorted(p.name[:-len("_daily.parquet")] for p in Path(root).glob("*_daily.parquet"))
    dq._read_ok = lambda p: json.loads(Path(p).read_text(encoding="utf-8")) if Path(p).exists() else None
    ic = types.ModuleType("intraday_cache")
    ic.store, ic.BAR_MIN = (lambda root: Path(root) / "intraday_3m"), 3
    ic.DECL = {"reconcile_price_tol": 0.005, "reconcile_volume_tol": 0.10}
    ic.reconcile_symbol = reconcile
    return dq, ic


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


def write_root(tmp: Path, w: World, alter=None):
    (tmp / "intraday_3m").mkdir(exist_ok=True)
    (tmp / "panel").mkdir(exist_ok=True)
    for i in range(w.n):
        sym, daily, bdays, B = w.stock(i, alter)
        daily.to_parquet(tmp / f"{sym}_daily.parquet", index=False)
        (tmp / f"{sym}_daily.ok.json").write_text(json.dumps({"series_kind": "equity"}), encoding="utf-8")
        if i != w.n - 1:                                                    # the last stock has no 3-minute file
            w.intra(bdays, B).to_parquet(tmp / "intraday_3m" / f"{sym}_3m.parquet", index=False)


def tree(root: Path) -> dict:
    return {str(p.relative_to(root)): p.stat().st_size for p in root.rglob("*") if p.is_file()}


def glue():
    print("4. main() end to end (stand-in modules)")
    tmp = Path(tempfile.mkdtemp())
    w = World(n=34, seed=6, trait="persistent")
    bad = {"sym_open": None, "day": pd.Timestamp("2022-06-15")}
    seen_tz = []

    def reconcile(X, d, tp, tv):                       # every session passes except S000 on 2022-06-15
        seen_tz.append(getattr(X["timestamp"].dt, "tz", None))
        J = pd.DataFrame({"day": pd.Series(X["timestamp"].dt.normalize().unique())})
        is0 = bool(np.isclose(float(d["open"].iloc[0]), bad["sym_open"]))
        J["ok"] = ~((J["day"] == bad["day"]) & is0)
        return J
    try:
        write_root(tmp, w)
        bad["sym_open"] = float(pd.read_parquet(tmp / "S000_daily.parquet")["open"].iloc[0])
        (tmp / "panel" / "research_ledger.jsonl").write_text('{"family": "other", "run": "X"}\n', encoding="utf-8")
        before = tree(tmp)
        dq, ic = stand_ins(reconcile)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = with_modules(dq, ic, lambda: S.main(["--root", str(tmp)]))
        after = tree(tmp)
        new = sorted(set(after) - set(before))
        changed = sorted(k for k in before if after.get(k) != before[k])
        runs = sorted((tmp / "research2" / "stage0").glob("S0_*"))
        check(rc == 0 and len(runs) == 1, f"main() ran (exit {rc}) and wrote one run folder {[r.name for r in runs]}")
        ok_paths = all(k.replace("\\", "/").startswith("research2/stage0/") for k in new)
        check(ok_paths and changed == [str(Path("panel") / "research_ledger.jsonl")],
              f"writes only research2\\stage0\\ ({len(new)} new files) and the ledger (changed: {changed})")
        led = (tmp / "panel" / "research_ledger.jsonl").read_text(encoding="utf-8").splitlines()
        rec = json.loads(led[-1])
        check(len(led) == 2 and rec["family"] == "stage0_persistence" and rec["post_2024_used"] is False and rec["fresh"] is True,
              f"one ledger line appended (verdict '{rec.get('verdict')}', fresh)")
        out = runs[0]
        files = {p.name for p in out.iterdir()}
        need = {"report.md", "summary.json", "persistence.csv", "per_stock.csv", "pooled.csv", "outputs.sha256"}
        check(need <= files, f"outputs: {sorted(files)}")
        summ = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        cov = summ["coverage"]
        check(cov["liquid_no_bars"] == 1 and cov["stocks_with_trades"] == w.n - 1, f"the stock without a 3-minute file is counted "
              f"({cov['liquid_no_bars']} without bars, {cov['stocks_with_trades']} with trades)")
        check(cov["hygiene"]["failed_reconciliation"] == 1, f"one failed reconciliation counted ({cov['hygiene']['failed_reconciliation']})")
        pst = pd.read_csv(out / "per_stock.csv")
        check(all(t is None for t in seen_tz) and len(pst) > 0, "reconciliation is given IST-naive bars")
        rep = (out / "report.md").read_text(encoding="utf-8")
        check("VERDICT" in rep and "provenance" in summ and "RERUN" not in rep, "report has a verdict; summary has provenance; not a rerun")
        # second run: every 2025 bar and daily row changed -> identical results, stamped RERUN

        def late(days, daily, B):
            lt = np.asarray(days > S.H2[1])
            for k in ("open", "high", "low", "close"):
                B[k][lt] *= 0.61
                daily[k] = np.where(lt, np.asarray(daily[k], float) * 0.61, daily[k])
        write_root(tmp, w, late)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            with_modules(dq, ic, lambda: S.main(["--root", str(tmp)]))
        runs = sorted((tmp / "research2" / "stage0").glob("S0_*"))
        o2 = runs[-1]
        same = all(pd.read_csv(out / f).equals(pd.read_csv(o2 / f)) for f in ("per_stock.csv", "persistence.csv", "pooled.csv"))
        check(len(runs) == 2 and same, "2025 data changed everywhere -> per_stock, persistence and pooled identical")
        rep2 = (o2 / "report.md").read_text(encoding="utf-8")
        rec2 = json.loads((tmp / "panel" / "research_ledger.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        check("RERUN" in rep2 and rec2["fresh"] is False and rec2["previous_runs"] == [out.name], "the second run is stamped RERUN (report and ledger)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    t0 = time.time()
    print(f"{S.CODE_VERSION} tests (bigmove_study {BM.CODE_VERSION})")
    by_hand()
    worlds()
    lookahead()
    glue()
    print(f"\n{len(FAILS)} failure(s) in {time.time() - t0:.0f} s")
    for f in FAILS:
        print("  FAIL:", f)
    if not FAILS:
        print("VERIFIED")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
