#!/usr/bin/env python3
"""
confirmation_study.py - buy only after the first minutes CONFIRM the move?

    python confirmation_study.py --root %CACHE_DAILY_ROOT%

Rules: CONFIRM_DECLARATION.json (fixed before the first run). Second pipeline: reads
intraday_v1's frozen candidate set, the daily cache and <root>\\intraday_3m\\; writes only
<root>\\research2\\confirm\\CS_YYYYMMDD_NNN\\. Descriptive: it changes nothing.

Each rule: at minute k, if the signal holds using only what is known by then, buy at the
last trade by minute k; otherwise skip (cash). Exit: the 5th close (honest). Two ways to
win - RETURN (beats open entry, skipped trades as cash) or PAIN (shallower drawdowns and a
better worst 10% on the trades taken, >= 50% of trades kept, no significant return loss) -
each through discovery (Benjamini-Hochberg) then confirmation (2025 on, used once).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import research_common as RC       # first: from a subfolder, this folder's copy must win
import stage_b_screen as SB        # noqa: E402
import stage_e_execution as EX     # noqa: E402
import intraday_cache as IC        # noqa: E402
import intraday_features as IF     # noqa: E402
import intraday_study as IS        # noqa: E402

CODE_VERSION = "confirmation_study v1"
DECL_RAW = (HERE / "CONFIRM_DECLARATION.json").read_bytes()
DECL = json.loads(DECL_RAW.decode("utf-8"))
CFG = DECL["config"]
COST = CFG["cost_bps"] / 1e4
SIGNALS = list(DECL["signals"])
CHECKS = list(CFG["checkpoints"])
RULES = [f"{s}@{k}" for s in SIGNALS for k in CHECKS] + [f"{s}@WAIT" for s in SIGNALS]


class PreconditionError(SystemExit):
    pass


def _ema(x: np.ndarray, n: int) -> np.ndarray:
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def _rsi(c: np.ndarray, n: int) -> np.ndarray:
    d = np.diff(c, prepend=c[0])
    g = pd.Series(np.clip(d, 0, None)).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    l_ = pd.Series(np.clip(-d, 0, None)).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        r = 100 - 100 / (1 + g / l_)
    return np.where(l_ == 0, 100.0, r)


def state(B: pd.DataFrame, P: pd.DataFrame, prev_close: float, adv20: float, N: Optional[pd.DataFrame]) -> dict:
    """Everything the signals need, as running arrays over the entry session's bars (pick day only for warm-up and levels)."""
    o, h, l, c, v = (B[x].to_numpy(float) for x in ("open", "high", "low", "close", "volume"))
    tp = (h + l + c) / 3.0
    cv, cpv = np.cumsum(v), np.cumsum(tp * v)
    warm = P["close"].to_numpy(float) if len(P) else np.empty(0)
    cc = np.r_[warm, c]
    f, s_, g = CFG["macd"]
    macd = _ema(cc, f) - _ema(cc, s_)
    st = {"m": IS.minutes(B), "o": o, "h": h, "l": l, "c": c, "open": o[0], "prev_close": prev_close, "adv20": adv20,
          "vwap": np.where(cv > 0, cpv / np.where(cv > 0, cv, 1), tp), "cv": cv, "upv": np.cumsum(v * (c > o)),
          "hi": np.maximum.accumulate(h), "lo": np.minimum.accumulate(l),
          "rsi": _rsi(cc, CFG["rsi_n"])[len(warm):], "macd_up": (macd > _ema(macd, g))[len(warm):],
          "pvwap": IF.vwap(P) if len(P) else np.nan, "pvpoc": IF.vpoc(P) if len(P) else np.nan, "nifty": None}
    if N is not None and len(N):
        st["nifty"] = (IS.minutes(N), N["close"].to_numpy(float), float(N["open"].iloc[0]))
    return st


def signal(st: dict, sig: str, k: int) -> Optional[bool]:
    """The signal at minute k, from bars that STARTED before minute k; None when nothing has traded yet."""
    j = int((st["m"] < k).sum())
    if j == 0:
        return None
    if "&" in sig:
        return all(bool(signal(st, x, k)) for x in sig.split("&"))
    i, p = j - 1, st["c"][j - 1]
    if sig == "HOLD_OPEN":
        return p >= st["open"]
    if sig == "BREAK_FIRST_HIGH":
        return p > st["h"][0]
    if sig == "HIGHER_LOW":
        return j >= 2 and st["l"][1:j].min() >= st["l"][0]
    if sig == "UPPER_HALF":
        return st["hi"][i] > st["lo"][i] and p >= (st["hi"][i] + st["lo"][i]) / 2
    if sig == "ABOVE_VWAP":
        return p > st["vwap"][i]
    if sig == "ABOVE_PREV_VWAP":
        return bool(p > st["pvwap"])
    if sig == "ABOVE_PREV_VPOC":
        return bool(p > st["pvpoc"])
    if sig == "GAP_HELD":
        return p > st["prev_close"]
    if sig == "RSI_ABOVE_50":
        return st["rsi"][i] > 50
    if sig == "RSI_NOT_HOT":
        return st["rsi"][i] <= 70
    if sig == "MACD_UP":
        return bool(st["macd_up"][i])
    if sig == "EARLY_VOLUME":
        return bool(st["adv20"] > 0 and st["cv"][i] >= CFG["early_volume_pace"] * (k / 375.0) * st["adv20"])
    if sig == "BUY_PRESSURE":
        return st["cv"][i] > 0 and st["upv"][i] / st["cv"][i] > 0.5
    if sig in ("NIFTY_UP", "BEAT_NIFTY"):
        if st["nifty"] is None:
            return False
        nm, nc, no = st["nifty"]
        jn = int((nm < k).sum())
        if jn == 0:
            return False
        if sig == "NIFTY_UP":
            return nc[jn - 1] >= no
        return p / st["open"] - 1 > nc[jn - 1] / no - 1
    raise ValueError(sig)


def entry(st: dict, rule: str) -> tuple:
    """(confirmed, entry price, minute of entry) for one rule."""
    sig, when = rule.split("@")
    gap = st["open"] / st["prev_close"] - 1 if st["prev_close"] > 0 else 0.0
    if sig == "GAP2_CONFIRM" and gap < CFG["gap_confirm"]:
        return True, st["open"], 0
    test = "HOLD_OPEN" if sig == "GAP2_CONFIRM" else sig
    ks = range(3, CFG["wait_until"] + 1, 3) if when == "WAIT" else [int(when)]
    for k in ks:
        ok = signal(st, test, k)
        if ok:
            j = int((st["m"] < k).sum())
            return True, float(st["c"][j - 1]), k
    return False, np.nan, None


def trade_table(picks: pd.DataFrame, daily: Dict[str, EX.Bars], intra: Dict[str, pd.DataFrame], cal: np.ndarray,
                nifty: Optional[pd.DataFrame] = None, dvol: Optional[Dict[str, pd.Series]] = None,
                ok_days: Optional[Dict[str, set]] = None) -> pd.DataFrame:
    pos = {d: i for i, d in enumerate(cal)}
    nd = nifty["timestamp"].dt.normalize() if nifty is not None and len(nifty) else None
    rows = []
    for _, p in picks[picks["traded"].astype(bool)].iterrows():
        b, X = daily.get(p["symbol"]), intra.get(p["symbol"])
        i = pos.get(np.datetime64(pd.Timestamp(p["signal_day"]), "ns"))
        if b is None or X is None or i is None or i + 1 >= len(cal):
            continue
        e = b.index.get(cal[i + 1])
        if e is None or e < 1 or e + 4 >= len(b.c):
            continue
        d1, d0 = pd.Timestamp(b.ts[e]).normalize(), pd.Timestamp(b.ts[e - 1]).normalize()
        if ok_days is not None and d1 not in ok_days.get(p["symbol"], set()):
            continue
        days = X["timestamp"].dt.normalize()
        B, P = X[days == d1], X[days == d0]
        if B.empty:
            continue
        ex = IS.exit_price("CLOSE_5", b, e, {})
        if not (ex > 0):
            continue
        av = np.nan
        if dvol and p["symbol"] in dvol:
            sv = dvol[p["symbol"]]
            av = float(sv[sv.index < d1].tail(20).mean())
        st = state(B, P, float(b.c[e - 1]), av, nifty[nd == d1] if nd is not None else None)
        later_low = float(b.l[e + 1:e + 5].min())
        rec = {"signal_day": pd.Timestamp(p["signal_day"]), "symbol": p["symbol"], "engine": p["engine"],
               "base": ex / st["open"] - 1 - COST, "base_mae": min(float(st["l"].min()), later_low) / st["open"] - 1}
        for r in RULES:
            ok, px, k = entry(st, r)
            rec[f"c:{r}"] = bool(ok)
            if ok:
                after = st["l"][st["m"] >= k] if k else st["l"]
                low = min(float(after.min()) if len(after) else px, later_low)
                rec[f"n:{r}"], rec[f"m:{r}"] = ex / px - 1 - COST, min(low, px) / px - 1
            else:
                rec[f"n:{r}"], rec[f"m:{r}"] = np.nan, np.nan
        rows.append(rec)
    return pd.DataFrame(rows)


def worst10(T: pd.DataFrame, r: str) -> dict:
    """10th percentile of the trades taken minus 10th percentile of open entry over all trades, day-block bootstrap."""
    if T.empty:
        return {"mean_bp": np.nan, "lo_bp": np.nan, "hi_bp": np.nan}
    days = np.sort(T["signal_day"].unique())
    di = np.searchsorted(days, T["signal_day"].to_numpy())
    conf, net, base = T[f"c:{r}"].to_numpy(bool), T[f"n:{r}"].to_numpy(float), T["base"].to_numpy(float)

    def wq(vals, w, q=0.10):
        o = np.argsort(vals)
        cw = np.cumsum(w[o])
        return vals[o][np.searchsorted(cw, q * cw[-1])] if cw[-1] > 0 else np.nan
    point = (np.percentile(net[conf], 10) if conf.any() else np.nan) - np.percentile(base, 10)
    rng, n, blk = np.random.default_rng(CFG["seed"]), len(days), CFG["boot_block"]
    out = []
    for _ in range(CFG["boot_B_quantile"]):
        st = rng.integers(0, n, size=int(np.ceil(n / blk)))
        cnt = np.bincount(((st[:, None] + np.arange(blk)[None, :]) % n).ravel()[:n], minlength=n).astype(float)
        w = cnt[di]
        a = wq(net[conf], w[conf]) if conf.any() else np.nan
        out.append(a - wq(base, w))
    out = np.asarray(out, float)
    out = out[np.isfinite(out)]
    if not len(out):
        return {"mean_bp": point * 1e4, "lo_bp": np.nan, "hi_bp": np.nan}
    lo, hi = np.percentile(out, [2.5, 97.5])
    return {"mean_bp": point * 1e4, "lo_bp": lo * 1e4, "hi_bp": hi * 1e4}


def series(T: pd.DataFrame, r: str) -> Dict[str, pd.Series]:
    c = T[f"c:{r}"].astype(bool)
    g = T["signal_day"]
    contrib = T[f"n:{r}"].where(c, 0.0)
    return {"strategy": (contrib - T["base"]).groupby(g).mean().sort_index(),
            "confirmed": (T[f"n:{r}"] - T["base"])[c].groupby(g[c]).mean().sort_index(),
            "skipped": (-T["base"])[~c].groupby(g[~c]).mean().sort_index(),
            "mae": (T[f"m:{r}"] - T["base_mae"])[c].groupby(g[c]).mean().sort_index()}


def judge(T: pd.DataFrame) -> pd.DataFrame:
    disc = T[T["signal_day"] <= pd.Timestamp(CFG["discovery_end"])]
    conf = T[T["signal_day"] >= pd.Timestamp(CFG["confirmation_start"])]
    rows = []
    for r in RULES:
        rec = {"rule": r}
        for tag, W in (("d", disc), ("c", conf)):
            S = series(W, r)
            for key in ("strategy", "mae"):
                b = IS.boot(S[key])
                rec.update({f"{tag}_{key}_{x}": b[x] for x in ("mean_bp", "lo_bp", "hi_bp", "p")})
            w = worst10(W, r)
            rec.update({f"{tag}_w10_{x}": w[x] for x in ("mean_bp", "lo_bp", "hi_bp")})
            rec[f"{tag}_retention"] = float(W[f"c:{r}"].mean()) if len(W) else np.nan
        S = series(T, r)
        rec["confirmed_bp"] = float(S["confirmed"].mean() * 1e4) if len(S["confirmed"]) else np.nan
        rec["skipped_bp"] = float(S["skipped"].mean() * 1e4) if len(S["skipped"]) else np.nan
        rows.append(rec)
    R = pd.DataFrame(rows)
    rs = set(IS.bh(dict(zip(R["rule"], R["d_strategy_p"])), CFG["fdr_q"]))
    ps = set(IS.bh(dict(zip(R["rule"], R["d_mae_p"])), CFG["fdr_q"]))
    R["return_winner"] = R["rule"].isin(rs) & (R["d_strategy_mean_bp"] > 0) & (R["c_strategy_lo_bp"] > 0)
    R["pain_winner"] = (R["rule"].isin(ps) & (R["d_mae_mean_bp"] > 0) & (R["c_mae_lo_bp"] > 0)
                        & (R["d_w10_lo_bp"] > 0) & (R["c_w10_lo_bp"] > 0)
                        & (R["d_strategy_hi_bp"] >= 0) & (R["c_strategy_hi_bp"] >= 0)
                        & (R["d_retention"] >= CFG["retention_min"]) & (R["c_retention"] >= CFG["retention_min"]))
    R["verdict"] = np.select([R["return_winner"] & R["pain_winner"], R["return_winner"], R["pain_winner"]],
                             ["RETURN + PAIN winner", "RETURN winner", "PAIN winner"], "discarded")
    return R


def run(picks, daily, intra, cal, nifty=None, dvol=None, ok_days=None) -> dict:
    T = trade_table(picks, daily, intra, cal, nifty, dvol, ok_days)
    if T.empty:
        raise PreconditionError("no traded pick has a usable entry session - check the 3-minute cache")
    out = {}
    for eng in ("D", "ENS"):
        Te = T[T["engine"] == eng]
        if len(Te):
            R = judge(Te).assign(engine=eng)
            R["forward_lane"] = (R["verdict"] != "discarded") & (eng == "D")
            out[eng] = R
    return {"trades": T, "rules": pd.concat(out.values(), ignore_index=True)}


def write_report(out: Path, R: pd.DataFrame, n: dict, sha: str) -> None:
    f = lambda a, b, c: f"{a:+.1f} [{b:+.1f}, {c:+.1f}]"
    L = ["# Confirmation entry study", "", f"{CODE_VERSION} | declaration {sha} | {n['trades']:,} traded picks | {len(RULES)} rules", "",
         "Each rule buys at minute k only if its signal confirms, else skips (cash); exit = the 5th close. RETURN winner: beats open "
         "entry (skips as cash). PAIN winner: shallower drawdowns AND a better worst 10% on the trades taken, >= 50% kept, no significant "
         "return loss. Both must pass discovery (BH q 0.10, to 2024) then confirmation (2025 on, once). bp per trade; 95% intervals.", ""]
    for eng in ("D", "ENS"):
        Re = R[R["engine"] == eng].copy()
        if Re.empty:
            continue
        Re["k"] = Re["verdict"] != "discarded"
        Re = Re.sort_values(["k", "d_strategy_p"], ascending=[False, True])
        L += [f"## {eng} traded top 3{' - forward lanes only from D' if eng == 'ENS' else ''}", "",
              "| rule | kept disc/conf | strategy vs open disc | conf | confirmed / skipped | drawdown (MAE) disc | conf | worst 10% disc | conf | verdict |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for _, r in Re.iterrows():
            L.append(f"| {r['rule']} | {r['d_retention']:.0%} / {r['c_retention']:.0%} | "
                     f"{f(r['d_strategy_mean_bp'], r['d_strategy_lo_bp'], r['d_strategy_hi_bp'])} | {f(r['c_strategy_mean_bp'], r['c_strategy_lo_bp'], r['c_strategy_hi_bp'])} | "
                     f"{r['confirmed_bp']:+.1f} / {r['skipped_bp']:+.1f} | {f(r['d_mae_mean_bp'], r['d_mae_lo_bp'], r['d_mae_hi_bp'])} | "
                     f"{f(r['c_mae_mean_bp'], r['c_mae_lo_bp'], r['c_mae_hi_bp'])} | {f(r['d_w10_mean_bp'], r['d_w10_lo_bp'], r['d_w10_hi_bp'])} | "
                     f"{f(r['c_w10_mean_bp'], r['c_w10_lo_bp'], r['c_w10_hi_bp'])} | {r['verdict']} |")
        L.append("")
    L += ["confirmed = waiting's effect on the trades taken; skipped = what skipping saved (+) or cost (-). Drawdown and worst-10% "
          "deltas: positive = less pain. Nothing here changes the engines or the paper test.", ""]
    (out / "confirm_report.md").write_text("\n".join(L), encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Confirmation entry study")
    ap.add_argument("--root", required=True)
    a = ap.parse_args(argv)
    root = Path(a.root)
    sha = hashlib.sha256(DECL_RAW).hexdigest()[:16]
    files = sorted(IC.store(root).glob(f"*_{IC.BAR_MIN}m.parquet"))
    if not files:
        raise PreconditionError(f"no 3-minute data in {IC.store(root)}")
    if not (root / "research2" / "intraday" / "frozen_candidates.parquet").exists():
        raise PreconditionError("run intraday_study.py first: this family uses its frozen candidate set")
    syms = [f.name[: -len(f"_{IC.BAR_MIN}m.parquet")] for f in files]
    daily = EX.load_bars(root, syms)
    intra = {s: pd.read_parquet(f) for s, f in zip(syms, files)}
    cal = np.unique(np.concatenate([b.ts for b in daily.values()]))
    picks, cand_sha = IS.frozen_candidates(root, daily, cal)
    nifty = intra.pop("NIFTY 50", None)
    from data_quality import _paths
    dvol, ok_days = {}, {}
    for s_ in intra:
        fp_, _ = _paths(root, s_)
        if Path(fp_).exists():
            v = pd.read_parquet(fp_, columns=["timestamp", "open", "high", "low", "close", "volume"])
            v["timestamp"] = SB._naive(v["timestamp"])
            dvol[s_] = v.assign(timestamp=v["timestamp"].dt.normalize()).set_index("timestamp")["volume"].astype(float)
            J = IC.reconcile_symbol(intra[s_], v, IS.CFG["reconcile_price_tol"], IS.CFG["reconcile_volume_tol"])
            ok_days[s_] = set(pd.to_datetime(J.loc[J["ok"], "day"]).dt.normalize()) if len(J) else set()
    res = run(picks, daily, intra, cal, nifty, dvol, ok_days)
    day = dt.date.today().strftime("%Y%m%d")
    k = 1
    while (root / "research2" / "confirm" / f"CS_{day}_{k:03d}").exists():
        k += 1
    out = root / "research2" / "confirm" / f"CS_{day}_{k:03d}"
    out.mkdir(parents=True)
    res["rules"].to_csv(out / "rules.csv", index=False)
    res["trades"].to_parquet(out / "trades.parquet", index=False)
    write_report(out, res["rules"], {"trades": len(res["trades"])}, sha)
    R = res["rules"]
    for eng in ("D", "ENS"):
        Re = R[R["engine"] == eng]
        print(f"{CODE_VERSION} [{eng}]: return winners {int(Re['return_winner'].sum())}, pain winners {int(Re['pain_winner'].sum())} of {len(Re)} rules")
    print(f"  candidates {cand_sha}; report: {out / 'confirm_report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
