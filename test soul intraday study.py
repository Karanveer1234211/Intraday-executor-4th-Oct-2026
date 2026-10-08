#!/usr/bin/env python3
"""
tests/test_soul_intraday_study.py - soul_intraday_study v1.1. Prints VERIFIED on success.

 1. By hand: daily dimensions and outcomes; 3-minute session statistics; the entry-session shift;
    same-day percentiles; NaN-aware distance; target fills (touch, gap through, floor, missing).
 2. No look-ahead: every neighbour used lies 6+ sessions before its pick.
 3. PLANTED world: a stock's volatility regime sets how far its pick runs before fading, and a pattern
    visible only in 3-minute bars (afternoon rise vs morning rise on day T) sets whether the entry session
    dips first. The memory must predict MFE, its targets must be calibrated, a state target must be
    PROMISING, WILD regimes must show bigger MFE than CALM, and the intraday state must add information
    about the session-1 dip.
 4. NULL world: nothing about the state matters - no memory skill, no intraday gain, no systematic winners.
 5. main() end to end with stand-in modules: files found, reconciliation filter applied, honest OPEN_6
    moves past a locked open, outputs written; an edited candidate file is refused; stocks outside the
    candidate set (and NIFTY 50) never enter the percentile universe.
 6. The reviewer's pre-run checks: outcome alignment against a brute-force loop on random prices; an
    independent re-implementation of state ranks, nearest neighbours, memory summaries, targets, fills and
    rule nets; FUTURE PERTURBATION - rescaling every price after day T* changes nothing about T*'s state,
    neighbours, memory or targets; missing bars leave the daily state untouched and mark the shape NA;
    the C5 / O6 fallbacks; a target crossed at a later session's open.
"""

from __future__ import annotations

import hashlib
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

import soul_intraday_study as SI        # noqa: E402

FAILS = []
K = np.arange(125)
OFFS = (K * 3 + 555).astype(np.int64) * 60_000_000_000


def check(cond, msg):
    print(("  ok  " if cond else "  FAIL") + f"  {msg}")
    if not cond:
        FAILS.append(msg)


def bars_from(day, opn, rel, rng, vol=1000.0):
    c = opn * (1 + np.asarray(rel, float))
    o = np.r_[opn, c[:-1]]
    e = np.abs(rng.standard_normal((2, 125))) * 0.0002
    return o, np.maximum(o, c) * (1 + e[0]), np.minimum(o, c) * (1 - e[1]), c, vol * rng.uniform(0.5, 1.5, 125)


def make_world(planted: bool, seed: int, n_stocks: int = 40, n_days: int = 460, engines=("D", "ENS")):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2023-08-01", periods=n_days)
    syms = [f"S{i:02d}" for i in range(n_stocks)]
    sched, cands = {}, []
    for di in range(90, n_days - 12):
        for r, si in enumerate([si for si in range(n_stocks) if (di - si) % 10 == 0], 1):
            sched[(si, di)] = r
            for eng in engines:
                cands.append({"signal_day": days[di], "symbol": syms[si], "engine": eng, "rank": r, "traded": r <= 3})
    daily, intra, truth = {}, {}, []
    dns = days.values.astype("datetime64[ns]").astype(np.int64)
    for si, s in enumerate(syms):
        phase, px = int(rng.integers(0, 120)), 100.0 * (1 + rng.random())
        plan, entry = {}, {}
        if planted:
            for di in range(n_days):
                if (si, di) in sched:
                    hot = ((di + phase) // 60) % 2 == 0
                    A = (0.06 if hot else 0.015) * float(np.clip(1 + 0.2 * rng.standard_normal(), 0.3, 2.0))
                    typ = "AFT" if rng.random() < 0.5 else "MORN"
                    plan[di] = ("T", typ, di)
                    for sx in range(1, 6):
                        plan[di + sx] = ("S", sx, A, typ, di)
                    truth.append({"symbol": s, "signal_day": days[di], "A": A, "type": typ, "hot": hot})
        Os, Hs, Ls, Cs, Vs = [], [], [], [], []
        for di in range(n_days):
            hot = ((di + phase) // 60) % 2 == 0
            sig = (0.025 if hot else 0.008) if planted else 0.015
            pl = plan.get(di)
            if pl is None:
                opn = px * (1 + 0.3 * sig * rng.standard_normal())
                rel = np.cumsum(sig / np.sqrt(125) * rng.standard_normal(125))
            elif pl[0] == "T":
                opn = px * (1 + 0.002 * rng.standard_normal())
                rel = np.where(K < 80, 0.0, 0.015 * (K - 79) / 45) if pl[1] == "AFT" else np.where(K < 10, 0.015 * (K + 1) / 10, 0.015)
                rel = rel + 0.0002 * rng.standard_normal(125)
            else:
                _, sx, A, typ, d0 = pl
                opn = px
                if sx == 1:
                    entry[d0] = opn
                    rel = np.interp(K, [0, 20, 110, 124], [0, -0.02, A, 0.8 * A]) if typ == "AFT" else \
                        np.interp(K, [0, 2, 20, 124], [0, -0.003, A, 0.8 * A])
                else:
                    f = (entry[d0] * (1 - A / 2) / px) ** (1.0 / (6 - sx))
                    rel = np.interp(K, [0, 124], [0, f - 1]) + 0.0002 * rng.standard_normal(125)
            o, h, l, c, v = bars_from(days[di], opn, rel, rng)
            Os.append(o), Hs.append(h), Ls.append(l), Cs.append(c), Vs.append(v)
            px = float(c[-1])
        O, H, L, C, V = (np.vstack(x) for x in (Os, Hs, Ls, Cs, Vs))
        ts = (dns[:, None] + OFFS[None, :]).ravel().astype("datetime64[ns]")
        intra[s] = pd.DataFrame({"timestamp": ts, "open": O.ravel(), "high": H.ravel(), "low": L.ravel(), "close": C.ravel(), "volume": V.ravel()})
        daily[s] = pd.DataFrame({"timestamp": days, "open": O[:, 0], "high": H.max(1), "low": L.min(1), "close": C[:, -1], "volume": V.sum(1)})
    return pd.DataFrame(cands), daily, intra, pd.DataFrame(truth)


def by_hand():
    print("1. by hand")
    n = 80
    c = 100 * 1.01 ** np.arange(n)
    df = pd.DataFrame({"timestamp": pd.bdate_range("2024-01-01", periods=n), "open": c * 0.995, "high": c * 1.01,
                       "low": c * 0.99, "close": c, "volume": np.full(n, 1000.0)})
    F = SI.daily_frame(df)
    o, h = c * 0.995, c * 1.01
    check(abs(F["mom5"].iloc[10] - (1.01 ** 5 - 1)) < 1e-12 and abs(F["dd60"].iloc[70]) < 1e-12 and abs(F["close_loc"].iloc[30] - 0.5) < 1e-9
          and abs(F["gap"].iloc[30] - (0.995 * 1.01 - 1)) < 1e-12, "daily dimensions: momentum, drawdown, close location, gap")
    check(abs(F["mfe5"].iloc[5] - (h[10] / o[6] - 1)) < 1e-12 and abs(F["CLOSE_5"].iloc[5] - (c[10] / o[6] - 1 - SI.COST)) < 1e-12
          and abs(F["OPEN_6"].iloc[5] - (o[11] / o[6] - 1 - SI.COST)) < 1e-12 and np.isnan(F["CLOSE_5"].iloc[n - 3]),
          "outcomes of buying at the next open: MFE, 5th close, 6th open; incomplete at the end of data")
    rng = np.random.default_rng(1)
    day = pd.Timestamp("2024-03-04")
    cl = 100 + 0.01 * K
    vol = np.where(K * 3 >= 315, 3.0, 1.0)
    X = pd.DataFrame({"timestamp": (np.int64(day.value) + OFFS).astype("datetime64[ns]"), "open": np.r_[100.0, cl[:-1]],
                      "high": np.maximum(np.r_[100.0, cl[:-1]], cl), "low": np.minimum(np.r_[100.0, cl[:-1]], cl), "close": cl, "volume": vol})
    S = SI.session_stats(X).iloc[0]
    tp = (X["high"] + X["low"] + X["close"]) / 3
    vw = float((tp * X["volume"]).sum() / X["volume"].sum())
    check(abs(S["ret_30"] - (cl[9] / 100 - 1)) < 1e-12 and abs(S["last_hour_share"] - 60 / 165) < 1e-12 and S["low_minute"] == 0
          and S["high_minute"] == 372 and abs(S["afternoon_ret"] - (cl[-1] / cl[79] - 1)) < 1e-12 and abs(S["close_vs_vwap"] - (cl[-1] / vw - 1)) < 1e-12,
          "3-minute session: first-30-minute return, last-hour share, minutes of low/high, afternoon return, close vs VWAP")
    two = pd.concat([X, X.assign(timestamp=X["timestamp"] + pd.Timedelta(days=1), low=X["low"] * 0.97)], ignore_index=True)
    dd = pd.DataFrame({"timestamp": [day, day + pd.Timedelta(days=1)], "open": [100.0, 100.0], "high": [101.3, 101.3], "low": [99.0, 96.0],
                       "close": [101.2, 101.2], "volume": [165.0, 165.0]})
    Pn = SI.build_panel({"AAA": dd}, {"AAA": two}.get)
    check(abs(Pn["s1_mae"].iloc[0] - (two["low"].iloc[125:].min() / 100.0 - 1)) < 1e-6 and np.isnan(Pn["s1_mae"].iloc[1]),
          "the entry-session columns of day T hold day T+1's intraday behaviour")
    P3 = pd.DataFrame({"symbol": pd.Categorical(["A", "B", "C"]), "day": [day] * 3, **{c_: [1.0, 3.0, 2.0] for c_ in SI.PCT_COLS},
                       "has_bars": [True] * 3})
    P3 = SI.add_states(P3)
    check(np.allclose(P3.sort_values("symbol")["p_mom20"].to_numpy(float), [1 / 3, 1.0, 2 / 3], atol=1e-6), "same-day percentiles")
    d2 = SI.nan_dist(np.array([0.0, np.nan, 1.0]), np.array([[0.0, 5.0, 1.0], [1.0, np.nan, np.nan], [np.nan, np.nan, np.nan]]))
    check(abs(d2[0]) < 1e-12 and abs(d2[1] - 3.0) < 1e-12 and np.isinf(d2[2]), "distance skips missing dimensions and rescales; no overlap = never a neighbour")
    O5 = np.array([[100, 103, 99, 99, 99]] * 5, float)
    H5 = np.array([[101, 104, 100, 100, 100]] * 5, float)
    px, hit = SI.target_fills(O5, H5, np.full(5, 100.0), np.array([0.02, 0.035, 0.10, np.nan, 0.001]))
    check(abs(px[0] - 103) < 1e-9 and abs(px[1] - 103.5) < 1e-9 and not hit[2] and not hit[3] and abs(px[4] - 100.5) < 1e-9,
          "targets: gap through fills at the open, touch fills at the target, never / missing = no fill, floor +0.5%")


def no_look_ahead(res):
    info = res["neighbours"]
    qpos, lag = info["query_pos"], SI.CFG["lag_sessions"]
    worst = -10 ** 9
    for key in ("cm", "cmd", "cmp", "own", "own_intraday"):
        for qp, nb in zip(qpos, info[key]):
            if nb is not None and len(nb):
                worst = max(worst, int(np.max(nb) - (qp - lag)))
    n_used = sum(len(x) for x in info["cm"] if x is not None)
    check(worst <= 0 and n_used > 0, f"no look-ahead: every neighbour lies {lag}+ sessions before its pick ({n_used:,} cross neighbours checked)")


def planted():
    print("3. PLANTED world")
    cands, daily, intra, truth = make_world(True, 11)
    res = SI.run(cands, daily, intra.get)
    print("2. no look-ahead")
    no_look_ahead(res)
    print("3. PLANTED world (results)")
    A = res["accuracy"]
    acc = A[(A["engine"] == "D") & (A["window"] == "whole")].set_index("what")
    r = acc.loc["cross memory: median MFE -> MFE"]
    check(r["spearman"] > 0.3 and r["lo"] > 0, f"the memory predicts how far a pick runs: Spearman {r['spearman']:+.2f} [{r['lo']:+.2f}, {r['hi']:+.2f}]")
    C = res["calibration"].set_index(["engine", "target"]).loc["D"]
    h30, h50, h70 = C.loc["SQ30", "whole_hit_pct"], C.loc["SQ50", "whole_hit_pct"], C.loc["SQ70", "whole_hit_pct"]
    check(h30 > h50 > h70 and 30 <= h50 <= 70, f"state targets are calibrated: reached {h30:.0f}% / {h50:.0f}% / {h70:.0f}% (expected about 70 / 50 / 30)")
    R = res["rules"].set_index(["engine", "rule"])
    v = R.loc[("D", "SQ30|C5")]
    check(v["verdict"] == "PROMISING" and bool(v["shadow_candidate"]),
          f"a state-specific target is PROMISING: SQ30|C5 {v['whole_bp']:+.0f} bp [{v['whole_lo']:+.0f}, {v['whole_hi']:+.0f}] vs the 5th close")
    check(R.loc[("D", "SQ30|C5"), "whole_bp"] > R.loc[("D", "T10|C5"), "whole_bp"],
          f"state targets beat a fixed +10% that low-energy picks never reach ({R.loc[('D', 'SQ30|C5'), 'whole_bp']:+.0f} vs {R.loc[('D', 'T10|C5'), 'whole_bp']:+.0f} bp)")
    B = res["behaviour"]["regime"]
    wild = B[B["state"].str.endswith("WILD")]
    calm = B[B["state"].str.endswith("CALM")]
    mw = float(np.average(wild["mfe_med_pct"], weights=wild["n"])) if len(wild) else np.nan
    mc = float(np.average(calm["mfe_med_pct"], weights=calm["n"])) if len(calm) else np.nan
    check(np.isfinite(mw) and np.isfinite(mc) and mw > mc + 1.0, f"state labels separate behaviour: median MFE WILD {mw:.2f}% vs CALM {mc:.2f}%")
    add = A[(A["engine"] == "D") & (A["window"] == "whole") & (A["test"] == "intraday adds")].set_index("what")
    a = add.loc["session-1 dip: full minus daily-only"]
    check(a["lo"] > 0, f"the intraday state adds information about the entry-session dip: +{a['spearman']:.2f} [{a['lo']:+.2f}, {a['hi']:+.2f}] Spearman")
    a2 = add.loc["session-1 dip: full minus daily + daily-bar pick day"]
    check(a2["lo"] > 0, f"... and it comes from the 3-minute bars, not the daily bar ({a2['spearman']:+.2f} [{a2['lo']:+.2f}, {a2['hi']:+.2f}])")
    cv = res["coverage"]
    check(cv["plain_exit_fallback"] == 0 and cv["D_picks"] > 900 and cv["picks_with_bars_S1"] == cv["traded_picks"],
          f"coverage: {cv['D_picks']:,} D picks, all with entry-session bars")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "SI_test"
        SI.save(res, out, "testsha", "testcand")
        rep = (out / "soul_intraday_report.md").read_text(encoding="utf-8")
        check(all(x in rep for x in ("## 1. State identification", "## 2. Behaviour", "## 3. Does the Soul know", "## 4. Targets",
                                     "### Normal targets", "### State-specific targets", "### Stock-specific targets", "## 8. Shadow-lane"))
              and (out / "picks.parquet").exists() and (out / "rules.csv").exists(), "report and data files written")


def null_world():
    print("4. NULL world")
    cands, daily, intra, _ = make_world(False, 12)
    res = SI.run(cands, daily, intra.get)
    A = res["accuracy"]
    acc = A[(A["engine"] == "D") & (A["window"] == "whole")].set_index("what")
    r = acc.loc["cross memory: median MFE -> MFE"]
    check(r["lo"] <= 0 <= r["hi"] or abs(r["spearman"]) < 0.08, f"no memory skill: Spearman {r['spearman']:+.2f} [{r['lo']:+.2f}, {r['hi']:+.2f}]")
    add = A[(A["engine"] == "D") & (A["window"] == "whole") & (A["test"] == "intraday adds")].set_index("what")
    a = add.loc["session-1 dip: full minus daily-only"]
    check(a["lo"] <= 0 <= a["hi"], f"no intraday gain: {a['spearman']:+.2f} [{a['lo']:+.2f}, {a['hi']:+.2f}]")
    R = res["rules"]
    RD = R[R["engine"] == "D"]
    keep_all = RD[~RD["rule"].str.startswith("VETO")]
    prom = list(keep_all.loc[keep_all["verdict"] == "PROMISING", "rule"])
    check(len(prom) <= 2, f"no systematic winners among rules that keep every trade: {len(prom)} of {len(keep_all)} PROMISING {prom}")
    E = res["picks"]
    n_open, bad = 0, 0
    for _, r in E[E["hit:T2|C5"] == 1].iterrows():
        tp = r["entry"] * 1.02
        for s_ in range(1, 6):
            if s_ > 1 and r[f"O{s_}"] >= tp:
                n_open += 1
                bad += int(not same([r["net:T2|C5"]], [r[f"O{s_}"] / r["entry"] - 1 - SI.COST]))
                break
            if r[f"H{s_}"] >= tp:
                break
    check(n_open > 20 and bad == 0, f"a target first crossed at a later session's open fills at that open, not at the target ({n_open} picks, {bad} wrong)")
    v = RD[RD["rule"] == "VETO_BOTH_NEG"].iloc[0]
    saved = (1 - v["taken_pct"]) * SI.CFG["cost_bps"]
    check(abs(v["whole_bp"] - saved) < 15, f"a veto's gain in a zero-edge world is just the cost it skips: {v['whole_bp']:+.1f} bp "
                                           f"vs {saved:.1f} bp of costs on the {(1 - v['taken_pct']) * 100:.0f}% of trades skipped")


def glue():
    print("5. main() end to end (stand-in modules)")
    cands, daily, intra, _ = make_world(True, 13, n_stocks=20, n_days=300, engines=("D",))
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / "daily").mkdir()
        (tmp / "intraday_3m").mkdir()
        for s in daily:
            daily[s].to_parquet(tmp / "daily" / f"{s}.parquet", index=False)
            intra[s].to_parquet(tmp / "intraday_3m" / f"{s}_3m.parquet", index=False)
        for extra in ("ZZZ", "NIFTY 50"):                     # not candidates: must stay out of the percentile universe
            daily["S00"].to_parquet(tmp / "daily" / f"{extra}.parquet", index=False)
            intra["S00"].to_parquet(tmp / "intraday_3m" / f"{extra}_3m.parquet", index=False)
        cdir = tmp / "research2" / "intraday"
        cdir.mkdir(parents=True)
        cands.to_parquet(cdir / "frozen_candidates.parquet", index=False)
        sha = hashlib.sha256((cdir / "frozen_candidates.parquet").read_bytes()).hexdigest()[:16]
        (cdir / "frozen_candidates.json").write_text(json.dumps({"sha": sha}), encoding="utf-8")
        tr = cands[cands["traded"]].iloc[40]
        dlist = pd.bdate_range("2023-08-01", periods=300)
        di = int(np.flatnonzero(dlist == tr["signal_day"])[0])
        bad_day, lock = dlist[di + 1], (tr["symbol"], di + 6)

        dq = types.ModuleType("data_quality")
        dq._paths = lambda root, sym: (Path(root) / "daily" / f"{sym}.parquet", None)
        ic = types.ModuleType("intraday_cache")
        ic.store, ic.BAR_MIN = (lambda root: Path(root) / "intraday_3m"), 3
        ic.DECL = {"reconcile_price_tol": 0.005, "reconcile_volume_tol": 0.10}

        def reconcile(X, d, tp, tv, sym_hint=[None]):
            days_ = pd.Series(pd.to_datetime(X["timestamp"]).dt.normalize().unique())
            sym = X.attrs.get("sym")
            return pd.DataFrame({"day": days_, "ok": ~((days_ == bad_day) & (X["close"].iloc[0] == intra[tr["symbol"]]["close"].iloc[0]))})
        ic.reconcile_symbol = reconcile
        ex = types.ModuleType("stage_e_execution")

        class B:
            def __init__(self, df):
                self.ts = pd.to_datetime(df["timestamp"]).values.astype("datetime64[ns]")
                self.o, self.h, self.l, self.c = (df[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        ex.load_bars = lambda root, syms: {s: B(pd.read_parquet(Path(root) / "daily" / f"{s}.parquet")) for s in syms}
        ex.plan_exit = lambda b, e, k, plan: (None, "close", float(b.c[e + k - 1]), {"data_end": False})
        bars_by_id = {}
        ex.lower_locked = lambda b, j, side: (side == "open" and abs(b.o[j] - daily[lock[0]]["open"].iloc[lock[1]]) < 1e-12)
        saved = {m: sys.modules.get(m) for m in ("data_quality", "intraday_cache", "stage_e_execution")}
        sys.modules.update({"data_quality": dq, "intraday_cache": ic, "stage_e_execution": ex})
        try:
            rc = SI.main(["--root", str(tmp)])
            outs = list((tmp / "research2" / "soul_intraday").glob("SI_*"))
            ok = rc == 0 and len(outs) == 1 and (outs[0] / "soul_intraday_report.md").exists() and (outs[0] / "summary.json").exists()
            check(ok, "main() reads the frozen candidates, daily and 3-minute files and writes the report")
            cov = json.loads((outs[0] / "summary.json").read_text(encoding="utf-8"))["coverage"]
            check(cov["stock_days"] == sum(len(daily[s]) for s in daily),
                  f"the percentile universe is exactly the candidate stocks: {cov['stock_days']:,} stock-days, none from ZZZ or NIFTY 50")
            E = pd.read_parquet(outs[0] / "picks.parquet")
            row = E[(E["symbol"] == tr["symbol"]) & (pd.to_datetime(E["signal_day"]) == tr["signal_day"])].iloc[0]
            check(np.isnan(row["s1_mae"]), "a pick whose entry session does not reconcile gets no entry-session intraday values")
            check(abs(row["px_OPEN_6"] - daily[lock[0]]["open"].iloc[lock[1] + 1]) < 1e-9,
                  "an exit at the 6th open that is locked at the lower circuit moves to the next unlocked open")
            fp = cdir / "frozen_candidates.parquet"
            cands.head(50).to_parquet(fp, index=False)
            try:
                SI.main(["--root", str(tmp)])
                check(False, "an edited candidate file is refused")
            except SystemExit as e:
                check("changed since it was built" in str(e), "an edited candidate file is refused")
        finally:
            for m, v in saved.items():
                if v is None:
                    sys.modules.pop(m, None)
                else:
                    sys.modules[m] = v
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def perturb_after(daily, intra, t_star, seed):
    """Rescale every session after t_star (prices by a random factor per stock-day, volume too) - the past is untouched."""
    rng = np.random.default_rng(seed)
    d2, i2 = {}, {}
    for s in daily:
        D, X = daily[s].copy(), intra[s].copy()
        days = pd.to_datetime(D["timestamp"])
        f = np.where(days > t_star, rng.uniform(0.8, 1.25, len(D)), 1.0)
        fv = np.where(days > t_star, rng.uniform(0.5, 2.0, len(D)), 1.0)
        for c in ("open", "high", "low", "close"):
            D[c] = D[c] * f
        D["volume"] = D["volume"] * fv
        pos = np.searchsorted(days.values, X["timestamp"].dt.normalize().values)
        for c in ("open", "high", "low", "close"):
            X[c] = X[c] * f[pos]
        X["volume"] = X["volume"] * fv[pos]
        d2[s], i2[s] = D, X
    return d2, i2


MEM_COLS = lambda E: [c for c in E.columns if c.split("_")[0] in ("cm", "cmd", "cmp", "om", "oi")] + ["rq50", "iq50"]
STATE_COLS = ["regime", "iregime", "shape", "transition", "seq3", "atr14", "has_bars_T"]


def same(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    return a.shape == b.shape and bool(np.all((np.isnan(a) & np.isnan(b)) | (np.abs(a - b) <= 1e-9 * np.maximum(1.0, np.abs(a)))))


def reviewer_checks():
    print("6. the reviewer's pre-run checks")
    rng = np.random.default_rng(5)
    n = 40
    c = 100 * np.exp(np.cumsum(0.02 * rng.standard_normal(n)))
    o = c * (1 + 0.01 * rng.standard_normal(n))
    h, l = np.maximum(o, c) * (1 + 0.01 * rng.random(n)), np.minimum(o, c) * (1 - 0.01 * rng.random(n))
    df = pd.DataFrame({"timestamp": pd.bdate_range("2024-01-01", periods=n), "open": o, "high": h, "low": l, "close": c,
                       "volume": rng.uniform(1e3, 2e3, n)})
    F = SI.daily_frame(df)
    want = {k: np.full(n, np.nan) for k in ("mfe5", "mae5", "CLOSE_3", "CLOSE_5", "CLOSE_7", "CLOSE_10", "OPEN_6")}
    for i in range(n):
        if i + 1 >= n:
            continue
        e = o[i + 1]
        if i + 5 < n:
            want["mfe5"][i] = max(h[i + 1:i + 6]) / e - 1
            want["mae5"][i] = min(l[i + 1:i + 6]) / e - 1
        for k in (3, 5, 7, 10):
            if i + k < n:
                want[f"CLOSE_{k}"][i] = c[i + k] / e - 1 - SI.COST
        if i + 6 < n:
            want["OPEN_6"][i] = o[i + 6] / e - 1 - SI.COST
    bad = [k for k in want if not same(F[k].to_numpy(), want[k])]
    check(not bad, f"outcome alignment matches a brute-force loop on random prices for MFE, MAE, CLOSE_3/5/7/10, OPEN_6 {bad or ''}")

    cands, daily, intra, _ = make_world(True, 21, n_stocks=24, n_days=260, engines=("D",))
    keep_cfg = dict(SI.CFG)
    SI.CFG.update({"k_cross": 7, "min_cross": 3, "k_own": 5, "min_regime": 3})
    try:
        P = SI.add_states(SI.build_panel(daily, intra.get, SI.CFG["state_start"]))
        R0 = SI.build_panel(daily, intra.get, SI.CFG["state_start"])
        d0 = pd.Timestamp(sorted(R0["day"].unique())[200])
        sub = R0[R0["day"] == d0]
        ranks = sub["mom20"].rank(pct=True).to_numpy()
        got = P.set_index(["symbol", "day"]).loc[list(zip(sub["symbol"], sub["day"])), "p_mom20"].to_numpy(float)
        check(np.allclose(got, ranks, atol=1e-6) and len(sub) == len(daily),
              f"percentiles rank each day across exactly the {len(daily)} stocks given (independent ranking)")
        res = SI.run(cands, daily, intra.get)
        E = res["picks"]
        E = E[E["engine"] == "D"].reset_index(drop=True)
        key = {(str(sy), d): i for i, (sy, d) in enumerate(zip(P["symbol"].astype(str), P["day"]))}
        cand_rows = sorted({key[(str(sy), pd.Timestamp(d))] for sy, d in zip(cands["symbol"], cands["signal_day"]) if (str(sy), pd.Timestamp(d)) in key})
        pool = P.iloc[cand_rows]
        pool = pool[np.isfinite(pool["CLOSE_5"].to_numpy(float))]
        lag, kc = SI.CFG["lag_sessions"], SI.CFG["k_cross"]
        errs, checked = [], 0
        for j in range(60, len(E), 37):
            pk = E.iloc[j]
            q = P.iloc[key[(pk["symbol"], pd.Timestamp(pk["signal_day"]))]]
            qv = q[SI.SET_FULL].to_numpy(float)
            cand = pool[pool["pos"] <= q["pos"] - lag]
            dist = []
            for _, r in cand.iterrows():
                cv = r[SI.SET_FULL].to_numpy(float)
                ok = np.isfinite(qv) & np.isfinite(cv)
                if ok.sum() < max(1, int(np.ceil(0.5 * np.isfinite(qv).sum()))):
                    continue
                dist.append((((qv[ok] - cv[ok]) ** 2).sum() * len(qv) / ok.sum(), r))
            dist.sort(key=lambda x: x[0])
            nb = [r for _, r in dist[:kc]]
            if len(nb) < SI.CFG["min_cross"]:
                continue
            mfe = np.array([r["mfe5"] for r in nb], float)
            exp = {"cm_net5": np.mean([r["CLOSE_5"] for r in nb]), "cm_mfe_q30": np.quantile(mfe, 0.3), "cm_mfe_q50": np.quantile(mfe, 0.5),
                   "cm_mfe_q70": np.quantile(mfe, 0.7), "cm_p5": np.mean(mfe >= 0.05), "cm_n": len(nb)}
            for kname, v in exp.items():
                if not same([pk[kname]], [v]):
                    errs.append(f"{kname} {pk[kname]:.6f} vs {v:.6f}")
            x = max(exp["cm_mfe_q50"], SI.CFG["target_floor"])
            tp, fill = pk["entry"] * (1 + x), None
            for s_ in range(1, 6):
                if s_ > 1 and pk[f"O{s_}"] >= tp:
                    fill = pk[f"O{s_}"]
                    break
                if pk[f"H{s_}"] >= tp:
                    fill = tp
                    break
            net_c5 = (fill if fill is not None else pk["px_CLOSE_5"]) / pk["entry"] - 1 - SI.COST
            net_o6 = (fill if fill is not None else pk["px_OPEN_6"]) / pk["entry"] - 1 - SI.COST
            if not (same([pk["net:SQ50|C5"]], [net_c5]) and same([pk["net:SQ50|O6"]], [net_o6])):
                errs.append(f"SQ50 net {pk['net:SQ50|C5']:.6f} vs {net_c5:.6f}")
            checked += 1
        check(checked >= 5 and not errs, f"an independent re-implementation agrees on neighbours, memory, targets, fills and nets "
                                          f"for {checked} picks {errs[:3] or ''}")
        miss = E["hit:T10|C5"] == 0
        check(same(E.loc[miss, "net:T10|C5"], E.loc[miss, "base"]) and same(E.loc[miss, "net:T10|O6"], E.loc[miss, "OPEN_6"]) and miss.sum() > 50,
              f"a target that is never reached falls back to the 5th close (C5) or the 6th open (O6) exactly ({int(miss.sum())} picks)")
        ud = sorted(cands["signal_day"].unique())
        diff, n_q, n_h = [], 0, 0
        for idx in (60, 100, 140):
            T_star = pd.Timestamp(ud[idx])
            sub_c = cands[cands["signal_day"] <= T_star]
            d2, i2 = perturb_after(daily, intra, T_star, idx)
            A = SI.run(sub_c, daily, intra.get)["picks"]
            B = SI.run(sub_c, d2, i2.get)["picks"]
            A = A[A["signal_day"] == T_star].sort_values("symbol").reset_index(drop=True)
            B = B[B["signal_day"] == T_star].sort_values("symbol").reset_index(drop=True)
            lv_a, lv_b = SI.target_levels(A), SI.target_levels(B)
            diff += [f"{T_star.date()} {c_}" for c_ in STATE_COLS + MEM_COLS(A) if not same(A[c_], B[c_])]
            diff += [f"{T_star.date()} target {k}" for k in lv_a if not same(lv_a[k], lv_b[k])]
            diff += [f"{T_star.date()} outcome unchanged?"] if same(A["base"], B["base"]) else []
            n_q += len(A)
            n_h += int(np.isfinite(A[[c_ for c_ in A.columns if "_h_CLOSE_10" in c_]].to_numpy(float)).sum())
        check(n_q >= 6 and n_h > 0 and not diff,
              f"FUTURE PERTURBATION: rescaling every price after the pick changes its outcome but not its state, neighbours, memory "
              f"(incl. the per-horizon averages) or targets - {n_q} picks on 3 dates {diff[:6] or ''}")

        tr = E.iloc[100]
        drop_day = pd.Timestamp(tr["signal_day"])
        loader2 = lambda s_: intra[s_][~((s_ == tr["symbol"]) & (intra[s_]["timestamp"].dt.normalize() == drop_day))]
        P2 = SI.add_states(SI.build_panel(daily, loader2, SI.CFG["state_start"]))
        a = P.set_index(["symbol", "day"]).loc[(tr["symbol"], drop_day)]
        b = P2.set_index(["symbol", "day"]).loc[(tr["symbol"], drop_day)]
        daily_dims = [c_ for c_ in SI.SET_DAY_PLUS]
        bar_dims = ["p_" + c_ for c_ in SI.I_BARS]
        check(same(a[daily_dims], b[daily_dims]) and np.isnan(b[bar_dims].to_numpy(float)).all() and b["shape"] == -1
              and a["shape"] >= 0 and a["iregime"] == b["iregime"] and a["regime"] == b["regime"],
              "missing bars on day T: daily state and labels unchanged, bar dimensions missing (not invented), shape marked NA")
        E2 = SI.run(cands, daily, loader2)["picks"]
        r2 = E2[(E2["symbol"] == tr["symbol"]) & (E2["signal_day"] == drop_day) & (E2["engine"] == "D")].iloc[0]
        check(not bool(r2["has_bars_T"]) and r2["cm_n"] >= SI.CFG["min_cross"],
              f"... and its memory still forms from the shared dimensions ({int(r2['cm_n'])} neighbours)")
        win = lambda s_: intra[s_][intra[s_]["timestamp"].dt.normalize().isin(
            [d_ for d_, sy in zip(cands["signal_day"], cands["symbol"]) if sy == s_])]
        try:
            SI.run(cands, daily, win)
            check(False, "thin 3-minute coverage (pick days only) is refused")
        except SystemExit as e:
            check("full-history download" in str(e), f"thin 3-minute coverage (pick days only) is refused: {str(e)[:60]}...")
        cv = SI.run(cands, daily, win, allow_partial_bars=True)["coverage"]
        check(cv["bar_coverage"] < 0.5 and cv["universe_stocks"] == len(daily),
              f"... unless --allow-partial-bars, and the coverage is reported ({cv['bar_coverage'] * 100:.1f}% of stock-days)")
    finally:
        SI.CFG.clear()
        SI.CFG.update(keep_cfg)


def main():
    SI.CFG["boot_B"], SI.CFG["boot_B_rank"] = 1000, 300          # faster bootstraps in tests; the rules are unchanged
    by_hand()
    reviewer_checks()
    planted()
    null_world()
    glue()
    print()
    if FAILS:
        print(f"FAILED  {len(FAILS)} check(s):")
        for f in FAILS:
            print("   - " + f)
        return 1
    print(f"VERIFIED  {SI.CODE_VERSION}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
