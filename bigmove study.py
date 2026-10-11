#!/usr/bin/env python3
"""
bigmove_study.py - BIGMOVE v1: an independent intraday strategy family for NSE stocks and NIFTY, built to catch
big same-day moves, long and short (declaration: BIGMOVE_DECLARATION.json, fixed before any run).

    python bigmove_study.py --root %CACHE_DAILY_ROOT% --coverage-only     (first: which liquid stocks lack 3-minute bars)
    python bigmove_study.py --root %CACHE_DAILY_ROOT%                     (the study)

The idea, in plain words: every morning, rank the stocks that are unusually ABLE to move today (move potential:
opening relative volume, the stock's own similar-day memory of next-session range, or both), and let the opening
range breakout decide the DIRECTION. Long book BIGMOVE-L and short book BIGMOVE-S are judged separately. Exit on
time at 15:03. Costs are the current Zerodha cash-intraday schedule plus assumed slippage, stressed 1.5x and 2x.

What it tests (see the declaration):
  F1  selection grid: score {RV, MFE, RVxMFE} x opening range {1, 2 bars} x top N {10, 20} x stop {range, 0.25 ATR,
      0.50 ATR}, plus PLAIN (every candidate), per side. A ranked cell must beat PLAIN with the same capital in use
      (the exposure-matched benchmark), and that lead must survive the search (max-t over the side's ranked cells);
      controls (random, ATR) get the same comparison and are never selected
  F2  direction gates on each side's 'best' cell: NIFTY, sector, relative strength, NIFTY + RS (a gate that cannot
      judge a stock-day lets it through)
  F3  path management on the same cell: VWAP trail, breakeven after +1R
  F4  a NIFTY noise-boundary momentum sleeve (futures costs)
  plus the paired RVxMFE vs RV vs MFE comparison, the combined L+S book and a regime table.
Discovery (2021-10 to 2024) selects; confirmation (2025-01 to 2026-07) is used once; the closing-auction period
(from 3 Aug 2026) is reported separately.

Writes only <root>\\research2\\bigmove\\ (BM_<date>_<n>\\ per run; missing_liquid.txt and coverage_by_stock.csv) and appends
one line to <root>\\panel\\research_ledger.jsonl. Reads an NSE ETF list and sector lists from <root>\\sectors\\ if present.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import platform
import re
import sys
import warnings
import zlib
from pathlib import Path
from statistics import NormalDist
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import soul_intraday_study as SI         # daily state, transitions, NaN-aware distance (tested v1.1)

CODE_VERSION = "bigmove_study v1.1"
DECL_RAW = (HERE / "BIGMOVE_DECLARATION.json").read_bytes()
DECL = json.loads(DECL_RAW.decode("utf-8"))
CFG = DECL["config"]
NB = int(CFG["session_bars"])            # 125 three-minute bars, 09:15 - 15:27
BAR = int(CFG["bar_min"])
X_BAR = int(CFG["exit_minute"]) // BAR    # the bar whose open is the time exit (15:03)
E_LAST = int(CFG["entry_last_minute"]) // BAR
FEATURES = SI.D_COLS + ["t_" + c for c in SI.TRANS]
STOPS = {"range": "range", "a25": 0.25, "a50": 0.5}
VARIANTS = ["base", "g_nifty", "g_sector", "g_rs", "g_nifty_rs", "x_vwap", "x_be"]
SCORES = ["rv", "mfe", "rvxmfe"]                 # ranked books
SELECTABLE = SCORES + ["plain"]                  # F1: ranked books and the plain 'buy every breakout' book
CONTROLS = ["random", "atr"]                     # reported, never selected
KIND_NONE, KIND_STOP, KIND_TIME, KIND_TRAIL = 0, 1, 2, 3
ETF_RE = re.compile(r"(CASE|BEES|ETF|IETF)$|ETF\d+$|^SETF|^LIQUID|^(GOLD|SILVER)(1|ADD|CASE|BEES|ETF|IETF|SHARE)?$|"
                    r"^(HDFCGOLD|TATAGOLD|BANKNIFTY1|NIFTY1|SENSEX1|MON100|MOM100|MOM50|MAFANG|MAHKTECH|MASPTOP50|N100|ICICIB22|"
                    r"HDFCNIFTY|HDFCSENSEX|KOTAKNIFTY|BSLNIFTY|AXISNIFTY|QNIFTY|NETFIT|HNGSNGBEES)$|^(EBBETF|BBETF)")  # a backstop: the ETF list is the rule
INDEX_NAMES = {"NIFTY50", "NIFTY 50", "NIFTYBANK", "NIFTY BANK", "BANKNIFTY", "INDIAVIX", "INDIA VIX", "SENSEX", "FINNIFTY",
               "NIFTY FIN SERVICE", "NIFTYIT", "NIFTY IT", "MIDCPNIFTY", "NIFTY MID SELECT"}
NIFTY_NAMES = ("NIFTY50", "NIFTY 50")


class PreconditionError(SystemExit):
    pass


def _log(msg: str) -> None:
    print(f"{dt.datetime.now():%H:%M:%S}  {msg}", flush=True)


# ----------------------------------------------------------------------
# costs
# ----------------------------------------------------------------------
def cash_cost_bps(notional: float = CFG["notional_rs"]) -> float:
    """Round-trip statutory + brokerage cost of one cash intraday trade (buy and sell of `notional` rupees), in bp."""
    brk = 2 * min(CFG["brokerage_cap_rs"], CFG["brokerage_rate"] * notional)
    txn = 2 * CFG["txn_cash"] * notional
    sebi = 2 * notional * CFG["sebi_per_crore_rs"] / 1e7
    total = brk + CFG["stt_cash_sell"] * notional + txn + sebi + CFG["stamp_cash_buy"] * notional + CFG["gst"] * (brk + txn + sebi)
    return total / notional * 1e4


def fut_cost_bps(notional: float) -> float:
    """Round-trip cost of one futures trade of `notional` rupees, in bp."""
    brk = 2 * min(CFG["brokerage_cap_rs"], CFG["brokerage_rate"] * notional)
    txn = 2 * CFG["txn_fut"] * notional
    sebi = 2 * notional * CFG["sebi_per_crore_rs"] / 1e7
    total = brk + CFG["stt_fut_sell"] * notional + txn + sebi + CFG["stamp_fut_buy"] * notional + CFG["gst"] * (brk + txn + sebi)
    return total / notional * 1e4


COST_BPS = cash_cost_bps()


def net_return(gross: np.ndarray, kind: np.ndarray, mult: float = 1.0) -> np.ndarray:
    """Net return of trades (fraction of position): gross minus slippage (entry stop order + exit by kind, x mult) minus costs;
    a slot that never traded (kind 0) earns 0."""
    gross, kind = np.asarray(gross, float), np.asarray(kind)
    slip = CFG["slip_entry_bps"] + np.where(kind == KIND_STOP, CFG["slip_stop_bps"], CFG["slip_time_bps"])
    out = gross - (mult * slip + COST_BPS) / 1e4
    return np.where(kind == KIND_NONE, 0.0, out)


# ----------------------------------------------------------------------
# daily data: liquidity, ATR, state, memory outcomes, beta
# ----------------------------------------------------------------------
def daily_features(daily: pd.DataFrame) -> pd.DataFrame:
    """One row per session (the Soul study's daily state + transitions), raw prices, 20-session median traded value,
    and rr = the NEXT session's high-low range in units of this session's ATR (the memory's outcome)."""
    F = SI.daily_frame(daily)
    d = daily.copy()
    d["day"] = SI._naive_days(d["timestamp"]).to_numpy()
    d = d.sort_values("day").drop_duplicates("day", keep="last").reset_index(drop=True)
    for c in ("open", "high", "low", "close", "volume"):
        F[c] = d[c].to_numpy(float) if c in d.columns else np.nan
    F["value20"] = (F["close"] * F["volume"]).rolling(int(CFG["value_window"]), min_periods=int(CFG["value_window"])).median()
    for c in SI.TRANS:
        F["t_" + c] = F[c] - F[c].shift(5)
    F["rr"] = ((F["high"].shift(-1) - F["low"].shift(-1)) / F["open"].shift(-1)) / F["atr14"]
    F["lr"] = np.log(F["close"]).diff()
    return F.replace([np.inf, -np.inf], np.nan)


def liquid_ok(F: pd.DataFrame) -> np.ndarray:
    """Row t can be traded on day t when the PREVIOUS close shows price, liquidity and ATR (point in time)."""
    prev = F[["close", "value20", "atr14"]].shift(1)
    return ((prev["close"] >= CFG["min_price"]) & (prev["value20"] >= CFG["min_value_cr"] * 1e7) & (prev["atr14"] > 0)).to_numpy()


def move_memory(F: pd.DataFrame, rows: np.ndarray, k: int = int(CFG["memory_k"]), apart: int = int(CFG["memory_apart"]),
                min_hist: int = int(CFG["memory_min_history"])) -> np.ndarray:
    """Expected range for trading-day rows t: ATR as of the previous close (row t-1) x the median NEXT-session range
    (in ATR units) of the stock's k most similar earlier sessions. Similarity is on the state at each session's close,
    each measure as a percentile of the stock's own history up to that session (expanding rank: nothing later is
    used). Candidates r <= t-2 (their next session r+1 <= t-1 has closed), at least `apart` sessions apart.
    Direction-free: it forecasts how far, not which way."""
    Z = F[FEATURES].expanding(min_periods=1).rank(pct=True).to_numpy(float)
    rr, atr = F["rr"].to_numpy(float), F["atr14"].to_numpy(float)
    finite_rr = np.isfinite(rr)
    out = np.full(len(rows), np.nan)
    for j, t in enumerate(np.asarray(rows, int)):
        q = t - 1
        if q < min_hist or not np.isfinite(atr[q]) or not np.isfinite(Z[q]).any():
            continue
        cand = np.flatnonzero(finite_rr[:q])                 # r <= q-1: the outcome session r+1 <= q is known
        if len(cand) < k:
            continue
        d2 = SI.nan_dist(Z[q], Z[cand])
        fin = np.isfinite(d2)
        cand, d2 = cand[fin], d2[fin]
        chosen: List[int] = []
        for i_ in np.argsort(d2, kind="stable"):
            r = int(cand[i_])
            if all(abs(r - c) >= apart for c in chosen):
                chosen.append(r)
                if len(chosen) == k:
                    break
        if len(chosen) >= min(k, int(CFG["memory_min_neighbours"])):
            out[j] = atr[q] * float(np.median(rr[chosen]))
    return out


def beta_series(F: pd.DataFrame, nifty_daily: Optional[pd.DataFrame]) -> np.ndarray:
    """60-session daily beta to NIFTY as of each row's close (aligned to F's rows)."""
    if nifty_daily is None or not len(nifty_daily):
        return np.full(len(F), np.nan)
    N = nifty_daily[["day", "close"]].rename(columns={"close": "nc"})
    J = F[["day", "lr"]].merge(N, on="day", how="left")
    J["nlr"] = np.log(J["nc"]).diff()
    w = int(CFG["beta_window"])
    mp = int(CFG["beta_min_sessions"])                           # a single missing NIFTY row must not blank beta for 60 sessions
    cov = J["lr"].rolling(w, min_periods=mp).cov(J["nlr"])
    var = J["nlr"].rolling(w, min_periods=mp).var()
    return (cov / var).replace([np.inf, -np.inf], np.nan).to_numpy(float)


# ----------------------------------------------------------------------
# 3-minute bars
# ----------------------------------------------------------------------
def ist_naive(ts) -> pd.Series:
    """Timestamps as IST wall-clock without a zone: a zone-aware series is CONVERTED to Asia/Kolkata first (dropping the
    zone without converting would put UTC 03:45 into the 03:45 slot)."""
    ts = pd.to_datetime(pd.Series(ts).reset_index(drop=True))
    if getattr(ts.dt, "tz", None) is not None:
        ts = ts.dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
    return ts


def bar_matrix(X: pd.DataFrame) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
    """Sessions x 125 matrices of open/high/low/close/volume (NaN where a bar is missing). Bar k starts at 09:15 + 3k IST.
    A duplicated timestamp keeps its last row."""
    if X is None or not len(X):
        return np.array([], dtype="datetime64[ns]"), {}
    X = X.assign(timestamp=ist_naive(X["timestamp"]).to_numpy()).drop_duplicates("timestamp", keep="last")
    ts = X["timestamp"]
    m = ((ts.dt.hour * 60 + ts.dt.minute) - 555).to_numpy()
    ok = (m >= 0) & (m < NB * BAR)
    day = ts.dt.normalize().astype("datetime64[ns]").to_numpy()[ok]
    idx = (m[ok] // BAR).astype(int)
    days, inv = np.unique(day, return_inverse=True)
    out = {}
    for c in ("open", "high", "low", "close", "volume"):
        A = np.full((len(days), NB), np.nan)
        A[inv, idx] = X[c].to_numpy(float)[ok] if c in X.columns else np.nan
        out[c] = A
    return days, out


def usable_sessions(B: Dict[str, np.ndarray]) -> np.ndarray:
    """A session counts when its first bar exists and at least 80% of its bars do."""
    if not B:
        return np.array([], bool)
    return np.isfinite(B["open"][:, 0]) & (np.isfinite(B["close"]).mean(1) >= CFG["min_bar_share"])


def since_open(C: np.ndarray, O0: np.ndarray) -> np.ndarray:
    """Return since the session open at each bar close (missing bars carry the last close forward)."""
    Cf = pd.DataFrame(C).ffill(axis=1).to_numpy(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        return Cf / O0[:, None] - 1


def _rowmax(A: np.ndarray) -> np.ndarray:
    """Row maximum ignoring NaN (NaN when the row has none), without numpy's all-NaN warning."""
    m = np.max(np.where(np.isfinite(A), A, -np.inf), 1)
    return np.where(np.isfinite(m), m, np.nan)


def _rowmin(A: np.ndarray) -> np.ndarray:
    m = np.min(np.where(np.isfinite(A), A, np.inf), 1)
    return np.where(np.isfinite(m), m, np.nan)


def first_true(M: np.ndarray, lo, hi) -> np.ndarray:
    """Per row, the first column index in [lo, hi] where M is True, else -1."""
    D, Bn = M.shape
    lo = np.broadcast_to(np.asarray(lo), (D,))
    hi = np.broadcast_to(np.asarray(hi), (D,))
    cols = np.arange(Bn)[None, :]
    W = M & (cols >= lo[:, None]) & (cols <= hi[:, None])
    idx = W.argmax(1)
    return np.where(W[np.arange(D), idx], idx, -1)


def time_exit_price(O: np.ndarray, C: np.ndarray) -> np.ndarray:
    """The open of the 15:03 bar; if missing, the next open that exists; else the last close before it."""
    D = O.shape[0]
    j = first_true(np.isfinite(O), X_BAR, NB - 1)
    px = np.where(j >= 0, O[np.arange(D), np.maximum(j, 0)], np.nan)
    Cb = pd.DataFrame(C[:, :X_BAR]).ffill(axis=1).to_numpy(float)[:, -1]
    return np.where(np.isfinite(px), px, Cb)


def session_vwap(H, L, C, V) -> np.ndarray:
    tp = (H + L + C) / 3.0
    v = np.where(np.isfinite(V) & np.isfinite(tp), V, 0.0)
    pv = np.where(v > 0, tp * v, 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.cumsum(pv, 1) / np.cumsum(v, 1)


def orb_fills(B: Dict[str, np.ndarray], side: np.ndarray, r: int, stop, atr: np.ndarray,
              allowed: Optional[np.ndarray] = None, exit_mode: str = "time", vwap: Optional[np.ndarray] = None,
              px_time: Optional[np.ndarray] = None) -> Dict[str, np.ndarray]:
    """Opening-range breakout fills for every session at once.
    side +1 long / -1 short / 0 none; r = opening-range bars; stop = 'range' or an ATR fraction; atr = ATR(14) as a
    fraction of price at the previous close; allowed[d, k] = the order is armed during bar k (a gate decided at the
    close of bar k-1). Returns gross return, exit kind, entry / exit bar, entry price and risk (bp)."""
    O, H, L, C = B["open"], B["high"], B["low"], B["close"]
    D = O.shape[0]
    rows = np.arange(D)
    hi_r, lo_r = _rowmax(H[:, :r]), _rowmin(L[:, :r])
    long, short = side > 0, side < 0
    level = np.where(long, hi_r, lo_r)
    trig = np.where(long[:, None], H >= level[:, None], L <= level[:, None]) & (side != 0)[:, None]
    if allowed is not None:
        trig &= allowed
    e = first_true(trig, r, E_LAST)
    has = e >= 0
    ee = np.maximum(e, 0)
    oe = O[rows, ee]
    entry = np.where(long, np.fmax(level, oe), np.fmin(level, oe))
    if stop == "range":
        st0 = np.where(long, lo_r, hi_r)
    else:
        st0 = np.where(long, entry * (1 - float(stop) * atr), entry * (1 + float(stop) * atr))
    risk = np.abs(entry - st0) / entry * 1e4
    hit = np.where(long[:, None], L <= st0[:, None], H >= st0[:, None])
    js = first_true(hit, ee, X_BAR - 1)
    js = np.where(has, js, -1)
    if px_time is None:
        px_time = time_exit_price(O, C)
    xb = np.full(D, X_BAR)
    xpx = px_time.copy()
    kind = np.where(has, KIND_TIME, KIND_NONE)
    stopped = js >= 0
    ojs = O[rows, np.maximum(js, 0)]
    stop_px = np.where(js == ee, st0, np.where(long, np.fmin(st0, ojs), np.fmax(st0, ojs)))

    if exit_mode == "be":                                         # after +1R the stop moves to the entry (from the next bar)
        tgt = np.where(long, entry + (entry - st0), entry - (st0 - entry))
        reach = np.where(long[:, None], H >= tgt[:, None], L <= tgt[:, None])
        b = first_true(reach, ee, X_BAR - 1)
        b = np.where(has, b, -1)
        pre = stopped & ((b < 0) | (js <= b))                      # the first stop comes first (conservative on a shared bar)
        be_hit = np.where(long[:, None], L <= entry[:, None], H >= entry[:, None])
        jb = first_true(be_hit, np.maximum(b, 0) + 1, X_BAR - 1)
        jb = np.where((b >= 0) & ~pre, jb, -1)
        ojb = O[rows, np.maximum(jb, 0)]
        be_px = np.where(long, np.fmin(entry, ojb), np.fmax(entry, ojb))
        xpx = np.where(pre, stop_px, np.where(jb >= 0, be_px, xpx))
        xb = np.where(pre, js, np.where(jb >= 0, jb, xb))
        kind = np.where(has & (pre | (jb >= 0)), KIND_STOP, kind)
    elif exit_mode == "vwap":                                     # a close on the wrong side of VWAP exits at the next open
        wrong = np.where(long[:, None], C < vwap, C > vwap)
        jt = first_true(wrong, ee, X_BAR - 2)
        jt = np.where(has, jt, -1)
        stop_first = stopped & ((jt < 0) | (js <= jt))
        trail = (jt >= 0) & ~stop_first
        jn = first_true(np.isfinite(O), np.minimum(np.maximum(jt, 0) + 1, NB - 1), NB - 1)   # the next bar that exists
        jn = np.where(jt >= 0, jn, -1)
        nxt = np.where(jn >= 0, O[rows, np.maximum(jn, 0)], px_time)
        xpx = np.where(stop_first, stop_px, np.where(trail, nxt, xpx))
        xb = np.where(stop_first, js, np.where(trail, np.where(jn >= 0, jn, X_BAR), xb))
        kind = np.where(has & stop_first, KIND_STOP, np.where(has & trail, KIND_TRAIL, kind))
    else:
        xpx = np.where(stopped, stop_px, xpx)
        xb = np.where(stopped, js, xb)
        kind = np.where(has & stopped, KIND_STOP, kind)
    with np.errstate(invalid="ignore", divide="ignore"):
        gross = np.where(long, xpx / entry - 1, 1 - xpx / entry)
    ok = has & np.isfinite(gross)
    # audit flags: the stop reached inside the entry bar (booked as the worst order: entry first, then the full stop);
    # a missing bar between the entry and the exit (it could hide a stop that would have been hit); a triggered trade
    # without a valid exit price (it would otherwise vanish as 'no trade')
    nan_c = np.cumsum(~np.isfinite(C), 1)
    xb_last = np.clip(np.where(ok, xb, 0) - 1, 0, NB - 1)
    before = np.where(ee > 0, nan_c[rows, np.maximum(ee - 1, 0)], 0)
    gaps = np.where(ok & (xb_last >= ee), nan_c[rows, xb_last] - before, 0)
    return {"gross": np.where(ok, gross, np.nan), "kind": np.where(ok, kind, KIND_NONE).astype(np.int8),
            "entry_bar": np.where(ok, e, -1), "exit_bar": np.where(ok, xb, -1), "entry": np.where(ok, entry, np.nan),
            "risk_bps": np.where(ok, risk, np.nan), "same_bar_stop": ok & (js == ee) & (js >= 0),
            "gap_in_trade": gaps > 0, "no_exit_price": has & ~np.isfinite(gross)}


# ----------------------------------------------------------------------
# context: NIFTY and sectors
# ----------------------------------------------------------------------
def nifty_context(nifty_bars: Optional[pd.DataFrame]) -> Dict[pd.Timestamp, np.ndarray]:
    """NIFTY's return since the open at each bar close, by session."""
    days, B = bar_matrix(nifty_bars)
    if not len(days):
        return {}
    keep = usable_sessions(B)                                    # first bar present and at least 80% of bars, as for stocks
    P = since_open(B["close"], B["open"][:, 0])
    return {pd.Timestamp(d): P[i] for i, d in enumerate(days) if keep[i]}


def read_lists(root: Path) -> Tuple[Dict[str, str], set, List[str]]:
    """From the CSVs in <root>\\sectors\\: symbol -> industry (files with Symbol and Industry columns, e.g. NSE's
    ind_nifty500list.csv) and the ETF set - every symbol whose ISIN starts INF in any file with an ISIN column, and every
    symbol in a file whose name contains 'etf' (e.g. NSE's eq_etfseclist.csv). Returns (sectors, etfs, files read)."""
    m, etf, used = {}, set(), []
    d = root / "sectors"
    if not d.is_dir():
        return m, etf, used
    for f in sorted(d.glob("*.csv")):
        try:
            T = pd.read_csv(f, dtype=str)
        except Exception:
            continue
        cols = {str(c).strip().lower().replace(" ", ""): c for c in T.columns}
        if "symbol" not in cols:
            continue
        syms = T[cols["symbol"]].astype(str).str.strip().str.upper()
        used.append(f.name)
        if "industry" in cols:
            for s_, ind in zip(syms, T[cols["industry"]]):
                if s_ and s_ not in m and isinstance(ind, str) and ind.strip():
                    m[s_] = ind.strip()
        isin_c = next((c for k, c in cols.items() if "isin" in k), None)
        if isin_c is not None:
            etf |= set(syms[T[isin_c].astype(str).str.strip().str.upper().str.startswith("INF").to_numpy()])
        if "etf" in f.stem.lower():
            etf |= set(syms)
    return m, etf, used


class SectorPaths:
    """Equal-weight return since the open of each sector's liquid stocks, bar by bar; a stock's own path is removed when
    it is asked for its peers (so a stock never confirms itself)."""

    def __init__(self, calendar: np.ndarray, sectors: List[str]):
        self.pos = {pd.Timestamp(d): i for i, d in enumerate(calendar)}
        self.sec = {s: i for i, s in enumerate(sorted(set(sectors)))}
        self.sum = np.zeros((len(self.sec), len(calendar), NB))
        self.cnt = np.zeros((len(self.sec), len(calendar), NB))

    def add(self, sector: str, days: np.ndarray, P: np.ndarray) -> None:
        if sector not in self.sec or not len(days):
            return
        s = self.sec[sector]
        di = np.array([self.pos.get(pd.Timestamp(d), -1) for d in days])
        ok = di >= 0
        f = np.isfinite(P[ok])
        self.sum[s, di[ok]] += np.where(f, P[ok], 0.0)
        self.cnt[s, di[ok]] += f

    def peers(self, sector: str, days: np.ndarray, P: np.ndarray, own_added: np.ndarray) -> np.ndarray:
        out = np.full((len(days), NB), np.nan)
        if sector not in self.sec:
            return out
        s = self.sec[sector]
        for k, d in enumerate(days):
            i = self.pos.get(pd.Timestamp(d), -1)
            if i < 0:
                continue
            sm, ct = self.sum[s, i].copy(), self.cnt[s, i].copy()
            if own_added[k]:
                f = np.isfinite(P[k])
                sm -= np.where(f, P[k], 0.0)
                ct -= f
            with np.errstate(invalid="ignore", divide="ignore"):
                out[k] = np.where(ct > 0, sm / ct, np.nan)
        return out


def sector_sessions(F: pd.DataFrame, days: np.ndarray, B: Dict[str, np.ndarray], liq_days: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """What one stock adds to its sector's path: its usable sessions that are liquid at the previous close (the same rule as
    stock_rows' base_ok, so its own path is removed exactly when it asks for its peers), and their return since the open."""
    rowmap = {pd.Timestamp(d): i for i, d in enumerate(F["day"])}
    trow = np.array([rowmap.get(pd.Timestamp(d), -1) for d in days])
    ok = usable_sessions(B) & (trow >= 1)
    ok[ok] = np.asarray(liq_days, bool)[trow[ok]]
    return days[ok], since_open(B["close"], B["open"][:, 0])[ok]


# ----------------------------------------------------------------------
# pass 1: one stock, every usable session -> candidate rows with every variant's outcome
# ----------------------------------------------------------------------
def stock_rows(sym: str, F: pd.DataFrame, days: np.ndarray, B: Dict[str, np.ndarray], liq_days: np.ndarray,
               nifty: Dict[pd.Timestamp, np.ndarray], beta: np.ndarray, sector: Optional[str] = None,
               sp: Optional[SectorPaths] = None, memory_fn: Callable = move_memory,
               first_day: Optional[pd.Timestamp] = None) -> Dict[int, pd.DataFrame]:
    """Candidate rows per opening range r (1 and 2 bars): liquid, usable sessions whose opening range points one way,
    with RV, the memory score, ATR and every variant x stop outcome. Everything except the outcomes uses data known
    at the end of the opening range (RV, direction) or at the previous close (ATR, memory, beta)."""
    out = {}
    if not len(days):
        return out
    use = usable_sessions(B)
    rowmap = {pd.Timestamp(d): i for i, d in enumerate(F["day"])}
    trow = np.array([rowmap.get(pd.Timestamp(d), -1) for d in days])
    liq = np.zeros(len(days), bool)
    okr = trow >= 1
    liq[okr] = liq_days[trow[okr]]
    base_ok = use & liq & okr
    O, H, L, C, V = (B[k] for k in ("open", "high", "low", "close", "volume"))
    atr = np.where(okr, F["atr14"].to_numpy(float)[np.maximum(trow - 1, 0)], np.nan)
    bet = np.where(okr, beta[np.maximum(trow - 1, 0)], np.nan)
    O0 = O[:, 0]
    P = since_open(C, O0)
    NP = np.full((len(days), NB), np.nan)
    for k, d in enumerate(days):
        v = nifty.get(pd.Timestamp(d))
        if v is not None:
            NP[k] = v
    SPth = sp.peers(sector, days, P, base_ok) if (sp is not None and sector) else np.full((len(days), NB), np.nan)
    vwap = session_vwap(H, L, C, V)
    pxt = time_exit_price(O, C)
    per_r = {}
    for r in (1, 2):                                           # relative volume and direction at the end of the opening range
        okv = np.isfinite(V[:, :r]).all(1)
        orv = np.where(okv, np.where(okv[:, None], V[:, :r], 0.0).sum(1), np.nan)
        hist = pd.Series(np.where(use, orv, np.nan)).shift(1)
        prior = hist.rolling(int(CFG["rv_lookback"]), min_periods=int(CFG["rv_min_sessions"])).mean().to_numpy()
        with np.errstate(invalid="ignore", divide="ignore"):
            rv = orv / prior
        oc = C[:, r - 1]
        side = np.where(oc > O0, 1, np.where(oc < O0, -1, 0))
        frozen = ~(_rowmax(H[:, :r]) > _rowmin(L[:, :r]))
        cand = base_ok & (side != 0) & ~frozen & np.isfinite(rv) & (rv >= CFG["rv_min"]) & np.isfinite(atr)
        if first_day is not None:                              # earlier sessions only feed the relative-volume history
            cand &= days >= np.datetime64(pd.Timestamp(first_day))
        per_r[r] = (rv, side, cand)
    any_c = per_r[1][2] | per_r[2][2]
    mem = np.full(len(days), np.nan)
    if any_c.any():                                            # the memory once per stock, only for candidate sessions
        need = np.flatnonzero(any_c)
        mem[need] = memory_fn(F, trow[need])
    for r in (1, 2):
        rv, side, cand = per_r[r]
        if not cand.any():
            continue
        sel = np.flatnonzero(cand)
        Bs = {k: v[sel] for k, v in B.items()}
        sd, at = side[sel], atr[sel]
        gates = {"g_nifty": NP[sel], "g_sector": SPth[sel], "g_rs": P[sel] - bet[sel][:, None] * NP[sel]}
        arm, ev = {}, {}
        for g, path in gates.items():
            # a gate that cannot be evaluated (no NIFTY bars that day, no sector or no liquid peer, no beta) lets the order
            # through: it is scored as 'no information', never as 'the gate said no' (which would credit the gate with
            # dropping, e.g., stocks missing from today's index lists)
            ok = np.where(np.isfinite(path), (sd[:, None] * path) > 0, True)
            arm[g] = np.concatenate([np.zeros((len(sel), 1), bool), ok[:, :-1]], 1)
            ev[g] = np.isfinite(path[:, r - 1])
        arm["g_nifty_rs"] = arm["g_nifty"] & arm["g_rs"]
        rows = {"day": days[sel], "symbol": sym, "side": sd.astype(np.int8), "rv": rv[sel], "mfe": mem[sel], "atr": at,
                "beta": bet[sel], "sector": sector or "", "ev_nifty": ev["g_nifty"], "ev_sector": ev["g_sector"], "ev_rs": ev["g_rs"]}
        for sname, stop in STOPS.items():
            for v in VARIANTS:
                if v == "base":
                    res = orb_fills(Bs, sd, r, stop, at, px_time=pxt[sel])
                    rows[f"e_{sname}"], rows[f"x_{sname}"] = res["entry_bar"].astype(np.int16), res["exit_bar"].astype(np.int16)
                    rows[f"risk_{sname}"] = res["risk_bps"].astype(np.float32)
                    rows[f"sb_{sname}"], rows[f"gp_{sname}"], rows[f"nx_{sname}"] = res["same_bar_stop"], res["gap_in_trade"], res["no_exit_price"]
                elif v.startswith("g_"):
                    res = orb_fills(Bs, sd, r, stop, at, allowed=arm[v], px_time=pxt[sel])
                elif v == "x_vwap":
                    res = orb_fills(Bs, sd, r, stop, at, exit_mode="vwap", vwap=vwap[sel], px_time=pxt[sel])
                else:
                    res = orb_fills(Bs, sd, r, stop, at, exit_mode="be", px_time=pxt[sel])
                rows[f"g_{v}_{sname}"] = res["gross"].astype(np.float32)
                rows[f"k_{v}_{sname}"] = res["kind"]
        out[r] = pd.DataFrame(rows)
    return out


# ----------------------------------------------------------------------
# pass 2: books, cells, statistics
# ----------------------------------------------------------------------
def rnd_score(days: pd.Series, syms: pd.Series) -> np.ndarray:
    """A fixed random number per stock-day (the random control): the same on every run."""
    return np.array([zlib.crc32(f"{s}|{pd.Timestamp(d).date()}|{CFG['seed']}".encode()) / 2 ** 32 for d, s in zip(days, syms)])


def add_scores(Cd: pd.DataFrame) -> pd.DataFrame:
    """RV, MFE, RVxMFE and the controls; all ranked within (day, side) over ONE candidate pool: candidates with a finite RV
    and a memory score (declared: a stock's first months after listing, before the memory has history, are in no book;
    main() counts them)."""
    Cd = Cd[np.isfinite(Cd["rv"]) & np.isfinite(Cd["mfe"])].copy()
    g = Cd.groupby(["day", "side"], sort=False)
    Cd["rvxmfe"] = g["rv"].rank(pct=True) * g["mfe"].rank(pct=True)
    Cd["random"] = rnd_score(Cd["day"], Cd["symbol"])
    return Cd.reset_index(drop=True)


def select_book(Cd: pd.DataFrame, side: int, score: str, n: int) -> pd.DataFrame:
    """One book's picks: the n best `score` candidates of `side` each day, 1/n of the book's capital each (a slot whose
    stock never breaks out stays in cash); 'plain' takes every candidate, each 1/(number of candidates that day).
    'plain_matched' is the benchmark a ranked n-slot book must beat: every candidate, with the SAME capital in use as the
    n-slot book on that day - min(count, n) / n of it, spread equally (on a day with fewer than n candidates both books
    hold all of them at 1/n, so holding cash on thin days is not mistaken for ranking skill)."""
    X = Cd[Cd["side"] == side]
    if score in ("plain", "plain_matched"):
        T = X.copy()
        cnt = T.groupby("day")["symbol"].transform("size").to_numpy(float)
        T["w"] = 1.0 / cnt if score == "plain" else np.minimum(cnt, n) / (n * cnt)
    else:
        T = X.sort_values(["day", score], ascending=[True, False], kind="stable").groupby("day", sort=False).head(n).copy()
        T["w"] = 1.0 / n
    return T


def daily_from(T: pd.DataFrame, calendar: np.ndarray, gcol: str, kcol: str, mult: float = 1.0) -> Tuple[np.ndarray, np.ndarray]:
    """The book's daily return (fraction of its capital, every calendar day; cash days 0) and each pick's net return."""
    net = net_return(T[gcol].to_numpy(float), T[kcol].to_numpy(), mult)
    s = pd.Series(net * T["w"].to_numpy(float)).groupby(T["day"].to_numpy()).sum()
    return s.reindex(pd.DatetimeIndex(calendar)).fillna(0.0).to_numpy(float), net


def book_daily(Cd: pd.DataFrame, calendar: np.ndarray, side: int, score: str, n: int, gcol: str, kcol: str,
               mult: float = 1.0) -> Tuple[np.ndarray, pd.DataFrame]:
    """select_book + daily_from in one call (tests and single books)."""
    T = select_book(Cd, side, score, n)
    daily, net = daily_from(T, calendar, gcol, kcol, mult)
    T["net"] = net
    return daily, T


TRADE_COLS = ["day", "symbol", "side", "rv", "mfe", "atr", "w", "ev_nifty", "ev_sector", "ev_rs"]


def book_series(T: pd.DataFrame, calendar: np.ndarray, gcol: str, kcol: str) -> Tuple[Dict[float, np.ndarray], pd.DataFrame]:
    """Daily returns at every slippage multiplier, and the picks (only the columns this book uses) with their
    base-slippage net."""
    dly = {}
    st = gcol.rsplit("_", 1)[-1]
    keep = [c for c in TRADE_COLS + [gcol, kcol, f"e_{st}", f"x_{st}", f"risk_{st}", f"sb_{st}", f"gp_{st}"] if c in T.columns]
    T1 = T[list(dict.fromkeys(keep))].copy()
    for mlt in CFG["stress"]:
        d_, net = daily_from(T, calendar, gcol, kcol, float(mlt))
        dly[float(mlt)] = d_
        if float(mlt) == 1.0:
            T1["net"] = net
    return dly, T1


def _block_idx(n: int, B: int, block: int, rng) -> np.ndarray:
    nb = int(np.ceil(n / block))
    st = rng.integers(0, n, size=(B, nb))
    return ((st[:, :, None] + np.arange(block)[None, None, :]).reshape(B, -1)[:, :n]) % n


def boot_stats(x: np.ndarray, idx: Optional[np.ndarray] = None) -> Tuple[float, float, float, float]:
    """Mean, 95% circular block-bootstrap interval and one-sided p (mean <= 0) of a daily series."""
    x = np.asarray(x, float)
    if len(x) < 20:
        return (float(x.mean()) if len(x) else np.nan), np.nan, np.nan, np.nan
    if idx is None:
        idx = _block_idx(len(x), int(CFG["boot_B"]), int(CFG["boot_block"]), np.random.default_rng(int(CFG["seed"])))
    mb = x[idx].mean(1)
    m = float(x.mean())
    lo, hi = np.percentile(mb, [2.5, 97.5])
    p = float((1 + np.sum(mb - m >= m)) / (1 + len(mb)))
    return m, float(lo), float(hi), p


def sharpe(x: np.ndarray) -> float:
    x = np.asarray(x, float)
    sd = x.std(ddof=1) if len(x) > 1 else 0.0
    return float(x.mean() / sd * np.sqrt(250)) if sd > 0 else np.nan


def max_dd(x: np.ndarray) -> float:
    c = np.cumsum(np.asarray(x, float))
    return float((c - np.maximum.accumulate(np.r_[0.0, c])[1:]).min()) if len(c) else np.nan


def deflated_sharpe(x: np.ndarray, trial_sharpes: np.ndarray, n_trials: int) -> float:
    """Bailey & Lopez de Prado: the probability the true Sharpe exceeds the best of n_trials pure-luck Sharpes.
    Per-period (daily) Sharpes; skew and kurtosis of x."""
    x = np.asarray(x, float)
    T = len(x)
    sd = x.std(ddof=1) if T > 2 else 0.0
    if T < 30 or sd <= 0:
        return np.nan
    sr = x.mean() / sd
    tr = np.asarray(trial_sharpes, float) / np.sqrt(250)
    tr = tr[np.isfinite(tr)]
    v = tr.var(ddof=1) if len(tr) > 1 else 0.0
    nd, g = NormalDist(), 0.5772156649
    n = max(int(n_trials), 2)
    sr0 = np.sqrt(v) * ((1 - g) * nd.inv_cdf(1 - 1 / n) + g * nd.inv_cdf(1 - 1 / (n * np.e)))
    z = (x - x.mean()) / sd
    g3, g4 = float((z ** 3).mean()), float((z ** 4).mean())
    den = 1 - g3 * sr + (g4 - 1) / 4 * sr ** 2
    if den <= 0:
        return np.nan
    return float(nd.cdf((sr - sr0) * np.sqrt(T - 1) / np.sqrt(den)))


def max_t_pvalues(M: np.ndarray, idx: Optional[np.ndarray]) -> np.ndarray:
    """Single-step max-t p-values against zero for every column of M (days x cells), studentised, with the same resamples
    for all columns: the share of resamples in which the BEST of all the columns, recentred to a true mean of zero, reaches
    this column's t. It judges a cell against the whole search, not on its own. A column that cannot be judged (fewer than
    20 days, no variation) gets NaN."""
    M = np.asarray(M, float)
    K = M.shape[1] if M.ndim == 2 else 0
    out = np.full(K, np.nan)
    if K == 0 or M.shape[0] < 20 or idx is None:
        return out
    m = M.mean(0)
    mb = np.stack([M[i].mean(0) for i in idx])          # B x K
    se = mb.std(0, ddof=1)
    ok = se > 0
    if not ok.any():
        return out
    t = m[ok] / se[ok]
    mx = ((mb[:, ok] - m[ok]) / se[ok]).max(1)
    out[ok] = (1 + (mx[:, None] >= t[None, :]).sum(0)) / (1 + len(mx))
    return out


def reality_check(M: np.ndarray, idx: np.ndarray) -> float:
    """White's Reality Check (studentised) against zero for the columns of M (days x cells): p-value of the best cell
    (the smallest max-t p-value). NaN when no column can be judged."""
    p = max_t_pvalues(M, idx)
    return float(np.nanmin(p)) if np.isfinite(p).any() else np.nan


def bh(p: np.ndarray, q: float) -> np.ndarray:
    p = np.asarray(p, float)
    ok = np.isfinite(p)
    out = np.zeros(len(p), bool)
    if not ok.any():
        return out
    ps = p[ok]
    o = np.argsort(ps)
    m = len(ps)
    thr = q * (np.arange(1, m + 1) / m)
    passed = ps[o] <= thr
    k = np.flatnonzero(passed).max() + 1 if passed.any() else 0
    sel = np.zeros(m, bool)
    sel[o[:k]] = True
    out[np.flatnonzero(ok)] = sel
    return out


def windows(calendar: np.ndarray) -> Dict[str, np.ndarray]:
    d = pd.DatetimeIndex(calendar)
    return {"disc": np.asarray((d >= pd.Timestamp(CFG["discovery_start"])) & (d <= pd.Timestamp(CFG["discovery_end"]))),
            "conf": np.asarray((d >= pd.Timestamp(CFG["confirmation_start"])) & (d <= pd.Timestamp(CFG["confirmation_end"]))),
            "post": np.asarray(d >= pd.Timestamp(CFG["post_cas_start"]))}


def series_stats(daily: Dict[float, np.ndarray], trades: pd.DataFrame, gcol: str, kcol: str, rcol: Optional[str], W: np.ndarray,
                 days: np.ndarray, idx_cache: Dict[int, np.ndarray]) -> dict:
    """Statistics of one book in one window: daily mean (bp of capital), interval, p, Sharpe, drawdown, stress, trades."""
    x = daily[1.0][W]
    n = len(x)
    if n not in idx_cache:
        idx_cache[n] = _block_idx(n, int(CFG["boot_B"]), int(CFG["boot_block"]), np.random.default_rng(int(CFG["seed"]))) if n >= 20 else None
    m, lo, hi, p = boot_stats(x, idx_cache[n])
    T = trades[trades["day"].isin(pd.DatetimeIndex(days[W]))]
    took = T[T[kcol] != KIND_NONE]
    net = took["net"].to_numpy(float)
    out = {"days": int(n), "mean_bp": m * 1e4, "lo_bp": lo * 1e4, "hi_bp": hi * 1e4, "p": p, "sharpe": sharpe(x),
           "maxdd_pct": max_dd(x) * 100, "mean_bp_x1.5": float(daily[1.5][W].mean() * 1e4) if n else np.nan,
           "mean_bp_x2": float(daily[2.0][W].mean() * 1e4) if n else np.nan, "selected": int(len(T)), "trades": int(len(took)),
           "fill_rate": float(len(took) / len(T)) if len(T) else np.nan, "net_per_trade_bp": float(net.mean() * 1e4) if len(net) else np.nan,
           "hit": float((net > 0).mean()) if len(net) else np.nan,
           "stopped": float((took[kcol] == KIND_STOP).mean()) if len(took) else np.nan}
    if rcol and rcol in took and len(took):
        R = took["net"].to_numpy(float) * 1e4 / took[rcol].to_numpy(float)
        out["avg_R"] = float(np.nanmean(R)) if np.isfinite(R).any() else np.nan
    if gcol.startswith("g_base_"):                               # audit shares (the flags describe the base trade)
        st_ = gcol.rsplit("_", 1)[-1]
        for flag, name in ((f"sb_{st_}", "same_bar_stop_share"), (f"gp_{st_}", "gap_in_trade_share")):
            if flag in took and len(took):
                out[name] = float(took[flag].astype(bool).mean())
    return out


# ----------------------------------------------------------------------
# F4: the NIFTY noise-boundary sleeve
# ----------------------------------------------------------------------
def nifty_sleeve(nifty_bars: Optional[pd.DataFrame], nifty_daily: Optional[pd.DataFrame], calendar: np.ndarray) -> Dict[str, dict]:
    """Daily results of the 6 sleeve cells (exit {time, trail} x filter {all, nr47, highvol}); one entry a day."""
    days, B = bar_matrix(nifty_bars)
    if len(days) < 30:
        return {}
    good = usable_sessions(B)                                    # first bar present and at least 80% of bars, as for stocks
    days, O, C = days[good], B["open"][good], B["close"][good]
    O0 = O[:, 0]
    Cf = pd.DataFrame(C).ffill(axis=1).to_numpy(float)
    A = np.abs(Cf / O0[:, None] - 1)
    sig = pd.DataFrame(A).shift(1).rolling(int(CFG["nifty_sigma_lookback"]), min_periods=int(CFG["nifty_sigma_min"])).mean().to_numpy(float)
    ND = None
    if nifty_daily is not None and len(nifty_daily):
        ND = nifty_daily.set_index("day")[["high", "low", "close"]] if {"high", "low"} <= set(nifty_daily.columns) else nifty_daily.set_index("day")[["close"]]
    prev_close = np.r_[np.nan, Cf[:-1, -1]]
    if ND is not None:
        pcd = ND["close"].shift(1).reindex(pd.DatetimeIndex(days)).to_numpy(float)
        prev_close = np.where(np.isfinite(pcd), pcd, prev_close)
    up = np.fmax(O0, prev_close)[:, None] * (1 + sig)
    dn = np.fmin(O0, prev_close)[:, None] * (1 - sig)
    ent = [m // BAR for m in CFG["nifty_entry_bars_start_minute"]]
    exits = [m // BAR for m in CFG["nifty_exit_bars_start_minute"]]
    D = len(days)
    side = np.zeros(D, int)
    eb = np.full(D, -1)
    for k in ent:                                                # the first check outside a band, one entry a day
        nl = (side == 0) & (Cf[:, k] > up[:, k])
        ns = (side == 0) & (Cf[:, k] < dn[:, k])
        side = np.where(nl, 1, np.where(ns, -1, side))
        eb = np.where(nl | ns, k + 1, eb)
    rows = np.arange(D)
    je = first_true(np.isfinite(O), np.minimum(np.maximum(eb, 0), NB - 1), X_BAR - 1)   # the next bar that exists
    je = np.where(eb >= 0, je, -1)
    side, eb = np.where(je >= 0, side, 0), je
    entry = np.where(je >= 0, O[rows, np.maximum(je, 0)], np.nan)
    pxt = time_exit_price(O, C)
    trail_px = pxt.copy()
    done = np.zeros(D, bool)
    for k in exits:
        back = (eb >= 0) & (k >= eb) & ~done & np.where(side > 0, Cf[:, k] < up[:, k], Cf[:, k] > dn[:, k])
        jn = first_true(np.isfinite(O), min(k + 1, NB - 1), NB - 1)
        trail_px = np.where(back, np.where(jn >= 0, O[rows, np.maximum(jn, 0)], pxt), trail_px)
        done |= back
    # filters, from the previous close only
    rng = (ND["high"] - ND["low"]) if (ND is not None and "high" in ND) else None
    nr = np.zeros(D, bool)
    hv = np.zeros(D, bool)
    if rng is not None:                                          # the PREVIOUS session was the narrowest of the last 4 or 7
        flag = ((rng <= rng.rolling(4).min()) | (rng <= rng.rolling(7).min())).astype(float)
        nr = flag.shift(1).reindex(pd.DatetimeIndex(days)).to_numpy(float) == 1.0
    if ND is not None:                                           # 14-session volatility above its 250-session median, at the previous close
        lr = np.log(ND["close"]).diff()
        rv14 = lr.rolling(int(CFG["nifty_vol_window"])).std()
        med = rv14.rolling(int(CFG["nifty_vol_median_window"]), min_periods=120).median()
        flag = (rv14 > med).astype(float).where(med.notna())
        hv = flag.shift(1).reindex(pd.DatetimeIndex(days)).to_numpy(float) == 1.0
    filt = {"all": np.ones(D, bool), "nr47": nr, "highvol": hv}
    cal = pd.DatetimeIndex(calendar)
    out = {}
    for ex, xp in (("time", pxt), ("trail", trail_px)):
        with np.errstate(invalid="ignore", divide="ignore"):
            gross = np.where(side > 0, xp / entry - 1, 1 - xp / entry)
        notional = CFG["nifty_lot"] * entry
        cost = np.array([fut_cost_bps(v) if np.isfinite(v) and v > 0 else np.nan for v in notional]) / 1e4
        for fn, f in filt.items():
            take = (side != 0) & f & np.isfinite(gross)
            daily = {}
            for mlt in CFG["stress"]:
                slip = mlt * 2 * CFG["slip_nifty_points"] / entry
                net = np.where(take, gross - cost - slip, 0.0)
                daily[float(mlt)] = pd.Series(net, index=pd.DatetimeIndex(days)).reindex(cal).fillna(0.0).to_numpy(float)
            out[f"{ex}|{fn}"] = {"daily": daily, "side": pd.Series(np.where(take, side, 0), index=pd.DatetimeIndex(days)).reindex(cal).fillna(0).to_numpy(int)}
    return out


# ----------------------------------------------------------------------
# the study
# ----------------------------------------------------------------------
def _pos(x) -> bool:
    return x is not None and np.isfinite(x) and x > 0


def excess_survives(disc: dict) -> bool:
    """A ranked cell's discovery excess over the matched PLAIN book, judged against the search (amendment q): its own lower
    bound above zero AND a max-t p-value over the side's ranked cells below excess_padj_max."""
    p = disc.get("excess_padj")
    return bool(_pos(disc.get("excess_lo_bp")) and p is not None and np.isfinite(p) and p < float(CFG["excess_padj_max"]))


def verdict(disc: dict, conf: dict, dsr: float, ranked: bool = False) -> str:
    """The declared verdicts. disc / conf hold a window's statistics; for a ranked cell they also hold its excess over the
    plain book (excess_bp, excess_lo_bp, excess_padj): the ranking must measurably beat buying everything - discovery lower
    bound of the excess > 0 and, because the cell was picked from many, the excess's max-t p over the side's ranked cells
    below excess_padj_max - and stay ahead in confirmation, for PROMISING as for CHAMPION."""
    ex_ok = (not ranked) or (excess_survives(disc) and _pos(conf.get("excess_bp")))
    if (_pos(disc.get("lo_bp")) and np.isfinite(dsr) and dsr >= CFG["dsr_min"] and _pos(disc.get("mean_bp_x1.5"))
            and _pos(conf.get("mean_bp")) and _pos(conf.get("sharpe")) and _pos(disc.get("sharpe"))
            and conf["sharpe"] >= 0.5 * disc["sharpe"] and _pos(conf.get("mean_bp_x1.5")) and ex_ok):
        return "CHAMPION"
    if _pos(disc.get("lo_bp")) and _pos(conf.get("mean_bp")) and ex_ok:
        return "PROMISING"
    if _pos(disc.get("mean_bp")) or _pos(conf.get("mean_bp")):
        return "WATCH"
    return "DEAD"


def _excess(a: np.ndarray, b: np.ndarray, W: Dict[str, np.ndarray], idx_cache: Dict[int, np.ndarray]) -> dict:
    """Paired daily difference a - b in each window: mean and 95% interval, bp."""
    out = {}
    d = a - b
    for wn, wm in W.items():
        m_, lo_, hi_, _ = boot_stats(d[wm], idx_cache.get(int(wm.sum())))
        out[f"{wn}_excess_bp"], out[f"{wn}_excess_lo_bp"], out[f"{wn}_excess_hi_bp"] = m_ * 1e4, lo_ * 1e4, hi_ * 1e4
    return out


def _series_only(x: Dict[float, np.ndarray], W: Dict[str, np.ndarray], idx_cache: Dict[int, np.ndarray]) -> dict:
    """Window statistics of a daily series that has no trade list (the combined book)."""
    out = {}
    for wn, wm in W.items():
        m_, lo_, hi_, p_ = boot_stats(x[1.0][wm], idx_cache.get(int(wm.sum())))
        out.update({f"{wn}_mean_bp": m_ * 1e4, f"{wn}_lo_bp": lo_ * 1e4, f"{wn}_hi_bp": hi_ * 1e4, f"{wn}_p": p_,
                    f"{wn}_sharpe": sharpe(x[1.0][wm]), f"{wn}_maxdd_pct": max_dd(x[1.0][wm]) * 100,
                    f"{wn}_mean_bp_x1.5": float(x[1.5][wm].mean() * 1e4) if wm.any() else np.nan})
    return out


def regime_table(series: Dict[str, np.ndarray], calendar: np.ndarray) -> pd.DataFrame:
    """Mean bp/day of each daily series between the declared regime dates (reported, never used for selection)."""
    d = pd.DatetimeIndex(calendar)
    if not len(d):
        return pd.DataFrame()
    cuts = [pd.Timestamp(x) for x in CFG["regime_dates"] if d.min() < pd.Timestamp(x) <= d.max()]
    edges = [d.min()] + cuts + [d.max() + pd.Timedelta(days=1)]
    rows = []
    for a, b in zip(edges[:-1], edges[1:]):
        m = np.asarray((d >= a) & (d < b))
        rec = {"from": a.date(), "to": d[m].max().date() if m.any() else None, "days": int(m.sum())}
        for nm, x in series.items():
            rec[nm] = float(x[m].mean() * 1e4) if m.any() else np.nan
        rows.append(rec)
    return pd.DataFrame(rows)


def picks_of(cands: Dict[int, pd.DataFrame], key: tuple, calendar: np.ndarray) -> pd.DataFrame:
    """The picks of one F1 / control / benchmark book with their net returns (rebuilt for the trade file)."""
    sname, score, r, n, st = key
    T = select_book(cands[int(r)], 1 if sname == "L" else -1, score, int(n) if n else int(CFG["top_n"][0]))
    return book_series(T, calendar, f"g_base_{st}", f"k_base_{st}")[1]


EV_OF = {"g_nifty": ["ev_nifty"], "g_sector": ["ev_sector"], "g_rs": ["ev_rs"], "g_nifty_rs": ["ev_nifty", "ev_rs"]}


def run_variants(cands: Dict[int, pd.DataFrame], calendar: np.ndarray, b, daily_store: dict, W: Dict[str, np.ndarray],
                 idx_cache: Dict[int, np.ndarray], trial_sh: np.ndarray, n_tr: int) -> Tuple[List[dict], dict]:
    """F2 gates and F3 exits on one base cell b (side, score, or_bars, top_n, stop, disc_mean_bp, disc_excess_padj), paired
    with the base; a RANKED base's variant must also beat the same variant on the exposure-matched PLAIN book, and its
    ranking must have survived the search (the base cell's max-t p)."""
    sname = b["side"]
    Cd = cands[int(b["or_bars"])]
    side = 1 if sname == "L" else -1
    ranked = b["score"] != "plain"
    base_key = (sname, b["score"], int(b["or_bars"]), int(b["top_n"]), b["stop"])
    base = daily_store[base_key]
    Tsel = select_book(Cd, side, b["score"], int(b["top_n"]))
    Tben = select_book(Cd, side, "plain_matched", int(b["top_n"])) if ranked else None
    dd = Tsel["day"].isin(pd.DatetimeIndex(calendar)[W["disc"]]).to_numpy()
    rows, vdaily = [], {}
    for v in VARIANTS[1:]:
        g, k = f"g_{v}_{b['stop']}", f"k_{v}_{b['stop']}"
        dly, T = book_series(Tsel, calendar, g, k)
        vdaily[(sname, v)] = dly
        rec = {"side": sname, "variant": v, "family": "F2" if v.startswith("g_") else "F3", "on_cell": "|".join(map(str, base_key[1:]))}
        if v in EV_OF:                                              # share of the cell's discovery picks the gate could judge
            evm = np.ones(len(Tsel), bool)
            for c_ in EV_OF[v]:
                evm &= Tsel[c_].to_numpy(bool)
            rec["disc_evaluable_share"] = float(evm[dd].mean()) if dd.any() else np.nan
        for wn, wm in W.items():
            st_ = series_stats(dly, T, g, k, None, wm, calendar, idx_cache)     # no avg R: a gated entry has its own risk
            for kk, vv in st_.items():
                rec[f"{wn}_{kk}"] = vv
            dm, dlo, dhi, dp = boot_stats(dly[1.0][wm] - base[1.0][wm], idx_cache.get(int(wm.sum())))
            rec[f"{wn}_diff_bp"], rec[f"{wn}_diff_lo_bp"], rec[f"{wn}_diff_hi_bp"] = dm * 1e4, dlo * 1e4, dhi * 1e4
            rec[f"{wn}_diff_p"] = dp
        if ranked:
            bdly, _ = book_series(Tben, calendar, g, k)
            rec.update(_excess(dly[1.0], bdly[1.0], W, idx_cache))
            rec["disc_excess_padj"] = float(b.get("disc_excess_padj", np.nan))     # the base ranking, judged against the search
        rec["disc_dsr"] = deflated_sharpe(dly[1.0][W["disc"]], trial_sh, n_tr)
        disc = {k_[5:]: rec[k_] for k_ in rec if k_.startswith("disc_")}
        conf = {k_[5:]: rec[k_] for k_ in rec if k_.startswith("conf_")}
        rec["verdict"] = verdict(disc, conf, rec["disc_dsr"], ranked=ranked)
        rec["adds"] = bool(np.isfinite(rec["disc_diff_lo_bp"]) and rec["disc_diff_lo_bp"] > 0 and np.isfinite(rec["conf_diff_bp"]) and rec["conf_diff_bp"] > 0)
        if v.startswith("g_") and not _pos(b["disc_mean_bp"]):         # on a losing book, trading less always looks better
            rec["adds"] = False
        if v in EV_OF and not (rec.get("disc_evaluable_share", 0) > 0):
            rec["verdict"], rec["adds"] = "NOT RUN (no data for this gate)", False
        rows.append(rec)
    return rows, vdaily


def run_books(cands: Dict[int, pd.DataFrame], calendar: np.ndarray, nifty_out: Dict[str, dict], log=None) -> dict:
    """Every F1 cell, control and benchmark per side; selection in discovery; F2 / F3 on each side's selected cell; the
    RVxMFE comparison; the combined L+S book; the NIFTY sleeve; regimes; verdicts."""
    W = windows(calendar)
    idx_cache: Dict[int, np.ndarray] = {}
    for wm in W.values():                                       # one set of resamples per window length, shared by all books
        n_ = int(wm.sum())
        if n_ >= 20 and n_ not in idx_cache:
            idx_cache[n_] = _block_idx(n_, int(CFG["boot_B"]), int(CFG["boot_block"]), np.random.default_rng(int(CFG["seed"])))
    cal_idx = pd.DatetimeIndex(calendar)
    cells, daily_store, thin = [], {}, []
    for r, Cd in cands.items():
        cnt = Cd.groupby(["day", "side"]).size()
        for side, sname in ((1, "L"), (-1, "S")):
            per_day = (cnt.xs(side, level="side") if side in set(cnt.index.get_level_values("side")) else pd.Series(dtype=float))
            per_day = per_day.reindex(cal_idx).fillna(0).to_numpy(float)
            for n in CFG["top_n"]:                               # days a side has fewer than N candidates (part of the book in cash)
                rec = {"side": sname, "or_bars": r, "top_n": int(n)}
                for wn, wm in W.items():
                    rec[f"{wn}_days"], rec[f"{wn}_thin_days"] = int(wm.sum()), int((per_day[wm] < n).sum())
                thin.append(rec)
            for score in SELECTABLE + CONTROLS + ["plain_matched"]:
                for n in CFG["top_n"]:
                    if score == "plain" and n != CFG["top_n"][0]:
                        continue
                    Tsel = select_book(Cd, side, score, int(n))
                    for st in STOPS:
                        g, k = f"g_base_{st}", f"k_base_{st}"
                        dly, T = book_series(Tsel, calendar, g, k)
                        key = (sname, score, r, int(n) if score != "plain" else 0, st)
                        daily_store[key] = dly
                        fam = "F1" if score in SELECTABLE else ("benchmark" if score == "plain_matched" else "control")
                        rec = {"side": sname, "score": score, "or_bars": r, "top_n": key[3], "stop": st, "family": fam}
                        for wn, wm in W.items():
                            for kk, vv in series_stats(dly, T, g, k, f"risk_{st}", wm, calendar, idx_cache).items():
                                rec[f"{wn}_{kk}"] = vv
                        cells.append(rec)
        if log:
            log(f"  books for opening range {r} bar(s) done")
    cells = pd.DataFrame(cells)
    # 'beat buying everything': a ranked cell (and each control) minus the exposure-matched PLAIN book with the same side,
    # opening range, N and stop, paired by day
    for wn in W:
        for c_ in ("excess_bp", "excess_lo_bp", "excess_hi_bp"):
            cells[f"{wn}_{c_}"] = np.nan
    for i, rr in cells.iterrows():
        if rr["score"] in ("plain", "plain_matched"):
            continue
        key = (rr["side"], rr["score"], int(rr["or_bars"]), int(rr["top_n"]), rr["stop"])
        bk = (rr["side"], "plain_matched", int(rr["or_bars"]), int(rr["top_n"]), rr["stop"])
        if bk in daily_store:
            for c_, v_ in _excess(daily_store[key][1.0], daily_store[bk][1.0], W, idx_cache).items():
                cells.loc[i, c_] = v_
    # the excess judged against the search (amendment q): each ranked F1 cell's discovery excess vs the best excess among
    # the side's ranked cells under the null (max-t, the Reality Check's resamples)
    disc_idx = idx_cache.get(int(W["disc"].sum()))
    cells["disc_excess_padj"] = np.nan
    n_ranked = {}
    for sname in ("L", "S"):
        rk_ = cells[(cells["family"] == "F1") & (cells["score"] != "plain") & (cells["side"] == sname)]
        pairs = [(i_, (sname, r_["score"], int(r_["or_bars"]), int(r_["top_n"]), r_["stop"])) for i_, r_ in rk_.iterrows()]
        pairs = [(i_, k_) for i_, k_ in pairs if k_ in daily_store and (sname, "plain_matched") + k_[2:] in daily_store]
        n_ranked[sname] = len(pairs)
        if pairs and disc_idx is not None:
            M_ = np.column_stack([(daily_store[k_][1.0] - daily_store[(sname, "plain_matched") + k_[2:]][1.0])[W["disc"]] for _, k_ in pairs])
            cells.loc[[i_ for i_, _ in pairs], "disc_excess_padj"] = max_t_pvalues(M_, disc_idx)
    # multiple testing over the F1 trials (ranked and plain cells, both sides)
    f1 = cells["family"] == "F1"
    trial_sh = cells.loc[f1, "disc_sharpe"].to_numpy(float)
    n_tr = int(f1.sum())
    cells["disc_dsr"] = np.nan
    cells["disc_fdr"] = False
    for sname in ("L", "S"):
        m = f1 & (cells["side"] == sname)
        cells.loc[m, "disc_fdr"] = bh(cells.loc[m, "disc_p"].to_numpy(float), CFG["fdr_q"])
    for i in np.flatnonzero(f1.to_numpy()):
        rr = cells.iloc[i]
        key = (rr["side"], rr["score"], int(rr["or_bars"]), int(rr["top_n"]), rr["stop"])
        cells.iloc[i, cells.columns.get_loc("disc_dsr")] = deflated_sharpe(daily_store[key][1.0][W["disc"]], trial_sh, n_tr)
    rc = {}
    for sname in ("L", "S"):
        keys = [(sname, s_, int(r_), int(n) if s_ != "plain" else 0, st) for s_ in SELECTABLE for r_ in cands for n in CFG["top_n"] for st in STOPS]
        keys = [k_ for k_ in dict.fromkeys(keys) if k_ in daily_store]
        if keys and disc_idx is not None:
            rc[f"F1 {sname}"] = reality_check(np.column_stack([daily_store[k_][1.0][W["disc"]] for k_ in keys]), disc_idx)
    # selection (discovery only) and verdicts
    sel_rows = []
    for sname in ("L", "S"):
        S_ = cells[f1 & (cells["side"] == sname)]
        if S_.empty:
            continue
        order = S_.sort_values(["disc_sharpe", "disc_mean_bp"], ascending=False)
        meets = np.array([_pos(r_["disc_lo_bp"]) and (r_["score"] == "plain" or excess_survives({k_[5:]: r_[k_] for k_ in r_.index if k_.startswith("disc_")}))
                          for _, r_ in order.iterrows()], bool)
        # 'best' (the cell F2 / F3, the combined book, the regimes and the ledger use): the highest discovery Sharpe among cells
        # that meet the discovery half of their own rule (a ranked cell: its excess too, judged against the search); if none
        # does, the highest overall
        picks = [("best", order[meets].iloc[0] if meets.any() else order.iloc[0])]
        best_rule = "met the discovery rule" if meets.any() else "none met the discovery rule: highest Sharpe"
        for sc in SELECTABLE:
            Z = S_[S_["score"] == sc].sort_values(["disc_sharpe", "disc_mean_bp"], ascending=False)
            if len(Z):
                picks.append((f"best {sc}", Z.iloc[0]))
                picks.append((f"median {sc}", Z.iloc[len(Z) // 2]))
        for label, rr in picks:
            disc = {k_[5:]: rr[k_] for k_ in rr.index if k_.startswith("disc_")}
            conf = {k_[5:]: rr[k_] for k_ in rr.index if k_.startswith("conf_")}
            vd = verdict(disc, conf, rr["disc_dsr"], ranked=rr["score"] != "plain") if not label.startswith("median") else "(reported)"
            rec_ = {"side": sname, "pick": label, "score": rr["score"], "or_bars": int(rr["or_bars"]), "top_n": int(rr["top_n"]),
                    "stop": rr["stop"], "verdict": vd, "chosen_by": best_rule if label == "best" else "",
                    **{k_: rr[k_] for k_ in rr.index if k_.startswith(("disc_", "conf_", "post_"))}}
            if rr["score"] in ("mfe", "rvxmfe"):               # is the memory more than volatility? (reported, not a verdict rule)
                ka = (sname, "atr", int(rr["or_bars"]), int(rr["top_n"]), rr["stop"])
                kk_ = (sname, rr["score"], int(rr["or_bars"]), int(rr["top_n"]), rr["stop"])
                if ka in daily_store:
                    d_ = daily_store[kk_][1.0] - daily_store[ka][1.0]
                    for wn, wm in W.items():
                        m_, lo_, hi_, _ = boot_stats(d_[wm], idx_cache.get(int(wm.sum())))
                        rec_[f"{wn}_vs_atr_bp"], rec_[f"{wn}_vs_atr_lo_bp"], rec_[f"{wn}_vs_atr_hi_bp"] = m_ * 1e4, lo_ * 1e4, hi_ * 1e4
            sel_rows.append(rec_)
    selected = pd.DataFrame(sel_rows)
    # F2 gates and F3 exits on each side's best cell
    var_rows, var_daily = [], {}
    for sname in ("L", "S"):
        if selected.empty or not (selected["side"] == sname).any():
            continue
        b = selected[(selected["side"] == sname) & (selected["pick"] == "best")].iloc[0]
        rows_, vd_ = run_variants(cands, calendar, b, daily_store, W, idx_cache, trial_sh, n_tr)
        var_rows += rows_
        var_daily.update(vd_)
    variants = pd.DataFrame(var_rows)
    if len(variants):            # multiple testing within F2 and F3, per side, on the paired improvement over the base cell (H4, H5)
        variants["disc_fdr"] = False
        for (sname, fam), G in variants.groupby(["side", "family"]):
            run_ = G[~G["verdict"].astype(str).str.startswith("NOT RUN")]
            if len(run_):
                variants.loc[run_.index, "disc_fdr"] = bh(run_["disc_diff_p"].to_numpy(float), CFG["fdr_q"])
                if disc_idx is not None:
                    bk_ = (sname,) + tuple(str(run_["on_cell"].iloc[0]).split("|"))
                    bser = daily_store[(bk_[0], bk_[1], int(bk_[2]), int(bk_[3]), bk_[4])][1.0][W["disc"]]
                    rc[f"{fam} {sname}"] = reality_check(np.column_stack([var_daily[(sname, v_)][1.0][W["disc"]] - bser for v_ in run_["variant"]]), disc_idx)
    # RVxMFE vs RV and vs MFE, paired by day for the same (opening range, N, stop)
    cmp_rows = []
    for sname in ("L", "S"):
        pooled = {"rv": [], "mfe": []}
        for r_ in cands:
            for n in CFG["top_n"]:
                for st in STOPS:
                    kx = (sname, "rvxmfe", int(r_), int(n), st)
                    if kx not in daily_store:
                        continue
                    for other in ("rv", "mfe"):
                        ko = (sname, other, int(r_), int(n), st)
                        d = daily_store[kx][1.0] - daily_store[ko][1.0]
                        pooled[other].append(d)
                        rec = {"side": sname, "vs": other, "or_bars": r_, "top_n": n, "stop": st}
                        for wn, wm in W.items():
                            m_, lo_, hi_, _ = boot_stats(d[wm], idx_cache.get(int(wm.sum())))
                            rec[f"{wn}_diff_bp"], rec[f"{wn}_lo_bp"], rec[f"{wn}_hi_bp"] = m_ * 1e4, lo_ * 1e4, hi_ * 1e4
                        cmp_rows.append(rec)
        for other, lst in pooled.items():
            if not lst:
                continue
            d = np.mean(np.vstack(lst), 0)
            rec = {"side": sname, "vs": other, "or_bars": "pooled", "top_n": "pooled", "stop": "pooled"}
            for wn, wm in W.items():
                m_, lo_, hi_, _ = boot_stats(d[wm], idx_cache.get(int(wm.sum())))
                rec[f"{wn}_diff_bp"], rec[f"{wn}_lo_bp"], rec[f"{wn}_hi_bp"] = m_ * 1e4, lo_ * 1e4, hi_ * 1e4
            rec["adds"] = bool(np.isfinite(rec["disc_lo_bp"]) and rec["disc_lo_bp"] > 0 and np.isfinite(rec["conf_diff_bp"]) and rec["conf_diff_bp"] > 0)
            cmp_rows.append(rec)
    comparison = pd.DataFrame(cmp_rows)
    # the combined book: half the capital in each side's selected cell (reported, no verdict)
    combined, comb_daily = {}, None
    if not selected.empty and set(selected["side"]) >= {"L", "S"}:
        kk = {sd: selected[(selected["side"] == sd) & (selected["pick"] == "best")].iloc[0] for sd in ("L", "S")}
        ks = {sd: (sd, r_["score"], int(r_["or_bars"]), int(r_["top_n"]), r_["stop"]) for sd, r_ in kk.items()}
        comb_daily = {m_: 0.5 * (daily_store[ks["L"]][m_] + daily_store[ks["S"]][m_]) for m_ in daily_store[ks["L"]]}
        combined = {"cells": {sd: "|".join(map(str, k_[1:])) for sd, k_ in ks.items()}, **_series_only(comb_daily, W, idx_cache)}
    # F4 NIFTY sleeve
    sl_rows = []
    sl_sh = [sharpe(v["daily"][1.0][W["disc"]]) for v in nifty_out.values()]
    for name, v in nifty_out.items():
        rec = {"cell": name}
        for wn, wm in W.items():
            x = v["daily"][1.0][wm]
            m_, lo_, hi_, p_ = boot_stats(x, idx_cache.get(int(wm.sum())))
            sd = v["side"][wm]
            rec.update({f"{wn}_mean_bp": m_ * 1e4, f"{wn}_lo_bp": lo_ * 1e4, f"{wn}_hi_bp": hi_ * 1e4, f"{wn}_p": p_,
                        f"{wn}_sharpe": sharpe(x), f"{wn}_maxdd_pct": max_dd(x) * 100, f"{wn}_trades": int((sd != 0).sum()),
                        f"{wn}_longs": int((sd > 0).sum()), f"{wn}_mean_bp_x1.5": float(v["daily"][1.5][wm].mean() * 1e4) if wm.any() else np.nan,
                        f"{wn}_net_per_trade_bp": float(x[sd != 0].mean() * 1e4) if (sd != 0).any() else np.nan})
        rec["disc_dsr"] = deflated_sharpe(v["daily"][1.0][W["disc"]], np.array(sl_sh), max(len(nifty_out), 2))
        sl_rows.append(rec)
    sleeve = pd.DataFrame(sl_rows)
    if len(sleeve):
        b = sleeve.sort_values("disc_sharpe", ascending=False).index[0]
        sleeve["selected"] = sleeve.index == b
        sleeve["disc_fdr"] = bh(sleeve["disc_p"].to_numpy(float), CFG["fdr_q"])
        disc = {k_[5:]: sleeve.loc[b, k_] for k_ in sleeve.columns if k_.startswith("disc_")}
        conf = {k_[5:]: sleeve.loc[b, k_] for k_ in sleeve.columns if k_.startswith("conf_")}
        sleeve["verdict"] = np.where(sleeve["selected"], verdict(disc, conf, sleeve.loc[b, "disc_dsr"]), "(reported)")
        if disc_idx is not None:
            rc["F4"] = reality_check(np.column_stack([v["daily"][1.0][W["disc"]] for v in nifty_out.values()]), disc_idx)
    # regimes (reported only)
    reg = {}
    for _, r_ in selected[selected["pick"] == "best"].iterrows() if len(selected) else []:
        reg[f"best {r_['side']}"] = daily_store[(r_["side"], r_["score"], int(r_["or_bars"]), int(r_["top_n"]), r_["stop"])][1.0]
    if comb_daily is not None:
        reg["combined"] = comb_daily[1.0]
    if len(sleeve):
        reg["NIFTY sleeve"] = nifty_out[sleeve.loc[sleeve["selected"], "cell"].iloc[0]]["daily"][1.0]
    return {"cells": cells, "selected": selected, "variants": variants, "comparison": comparison, "sleeve": sleeve,
            "combined": combined, "regimes": regime_table(reg, calendar), "thin_days": pd.DataFrame(thin),
            "reality_check": rc, "n_trials": n_tr, "n_ranked": n_ranked, "daily": daily_store, "variant_daily": var_daily,
            "calendar": calendar, "windows": {k_: int(v.sum()) for k_, v in W.items()}}


# ----------------------------------------------------------------------
# report
# ----------------------------------------------------------------------
def _f(x, d=1) -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"{x:+.{d}f}"


def _ci(m, lo, hi, d=1) -> str:
    return "n/a" if not np.isfinite(m) else (f"{m:+.{d}f} [{lo:+.{d}f}, {hi:+.{d}f}]" if np.isfinite(lo) else f"{m:+.{d}f}")


def _hygiene_line(h: Optional[dict]) -> str:
    if not h:
        return "Data checks: not counted."
    n = max(int(h.get("sessions_with_bars", 0)), 1)
    a, b = int(h.get("failed_reconciliation", 0)), int(h.get("no_first_bar_or_under_80pct_bars", 0))
    return (f"Data checks (they look at the whole session: hygiene, not signal): of {h.get('sessions_with_bars', 0):,} stock sessions "
            f"with bars, {a:,} ({a / n * 100:.2f}%) failed reconciliation with the daily bar and {b:,} ({b / n * 100:.2f}%) had no "
            f"first bar or under 80% of bars; both are dropped. Unreadable 3-minute files: {int(h.get('unreadable_files', 0))}. "
            f"Triggered trades without a valid exit price: {int(h.get('triggered_without_exit_price', 0))} (they would otherwise vanish "
            f"as 'no trade'; expected 0). If any of these is large, read the results with care.")


def _month_line(m: Optional[dict]) -> str:
    if not m or m.get("min") is None:
        return "Usable share by month: not counted."
    under = m.get("months_under_90pct") or []
    return (f"Usable share of liquid stock-days by month (universe_by_month.csv): lowest {m['min'] * 100:.1f}% ({m['min_month']}); "
            + (f"months under 90%: {', '.join(under)} - results in those months rest on a thinner universe."
               if under else "no month under 90%."))


def _yes(x) -> str:
    return "YES" if bool(x) is True and x == x else "no"


def _n_ranked(res: dict) -> str:
    n = res.get("n_ranked") or {}
    v = sorted(set(n.values()))
    return "n/a" if not v else (str(v[0]) if len(v) == 1 else " / ".join(f"{k} {x}" for k, x in n.items()))


def write_report(out_dir: Path, res: dict, sha: str, cov: dict) -> None:
    S, V, Cm, SL = res["selected"], res["variants"], res["comparison"], res["sleeve"]
    rc = res["reality_check"]
    prev = cov.get("previous_runs") or []
    banner = ([f"**RERUN #{len(prev) + 1} of {DECL['family_id']}: the confirmation window was already seen in "
               f"{', '.join(str(x['run']) for x in prev)}. These results are NOT fresh evidence.**", ""] if prev else [])
    L = [f"# BIGMOVE v1 - intraday breakout study", ""] + banner + [
         f"{CODE_VERSION} | declaration {sha} | {dt.datetime.now():%Y-%m-%d %H:%M} | cash-intraday costs {COST_BPS:.2f} bp a round trip at "
         f"Rs {CFG['notional_rs']:,.0f} plus slippage (entry {CFG['slip_entry_bps']:.0f} bp, stop {CFG['slip_stop_bps']:.0f} bp, time {CFG['slip_time_bps']:.0f} bp)", "",
         f"Days: discovery {res['windows']['disc']}, confirmation {res['windows']['conf']}, after the closing auction {res['windows']['post']} "
         f"(3-minute data {cov.get('bar_period', 'n/a')}). Liquid stock-days with a 3-minute session: "
         f"{cov.get('covered_share', float('nan')) * 100:.1f}% of {cov.get('liquid_stock_days', 0):,}; usable after reconciliation and the 80% rule: "
         f"{cov.get('usable_share', float('nan')) * 100:.1f}%.", "",
         _hygiene_line(cov.get("data_hygiene")), "",
         _month_line(cov.get("usable_share_by_month")), "",
         _memory_line(cov.get("candidates_without_memory")), "",
         "## Verdicts (discovery selects; confirmation used once)", "",
         "Daily return of the book in bp of its capital per day, [95% block-bootstrap interval]; Sharpe annualised; DSR = deflated Sharpe over "
         f"{res['n_trials']} trials; FDR = passes Benjamini-Hochberg q {CFG['fdr_q']} within its side. 'Excess' = minus PLAIN with the same "
         "capital in use (every candidate, min(count, N)/N of the book), paired by day: a ranked cell must beat it to be PROMISING or CHAMPION. "
         f"'p (search)' judges that excess against the search: how often the BEST of the side's {_n_ranked(res)} ranked "
         f"cells shows as much excess when no ranking has any (max-t); a ranked cell also needs it below {CFG['excess_padj_max']}.", "",
         "| side | pick | score | range bars | top N | stop | discovery bp/day | Sharpe | DSR | FDR | x1.5 slip | excess | p (search) | confirmation bp/day | Sharpe | x1.5 slip | excess | after CAS bp/day | verdict |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in S.iterrows():
        pl = r["score"] == "plain"
        exd = "(is plain)" if pl else _ci(r.get("disc_excess_bp", np.nan), r.get("disc_excess_lo_bp", np.nan), r.get("disc_excess_hi_bp", np.nan))
        exp_ = "-" if pl or not np.isfinite(r.get("disc_excess_padj", np.nan)) else f"{r['disc_excess_padj']:.3f}"
        exc = "(is plain)" if pl else _f(r.get("conf_excess_bp", np.nan))
        L.append(f"| {r['side']} | {r['pick']} | {r['score']} | {r['or_bars']} | {r['top_n'] if not pl else 'all'} | {r['stop']} | "
                 f"{_ci(r['disc_mean_bp'], r['disc_lo_bp'], r['disc_hi_bp'])} | {_f(r['disc_sharpe'], 2)} | {_f(r.get('disc_dsr', np.nan), 2)} | "
                 f"{_yes(r.get('disc_fdr'))} | {_f(r['disc_mean_bp_x1.5'])} | {exd} | {exp_} | {_ci(r['conf_mean_bp'], r['conf_lo_bp'], r['conf_hi_bp'])} | "
                 f"{_f(r['conf_sharpe'], 2)} | {_f(r['conf_mean_bp_x1.5'])} | {exc} | {_f(r['post_mean_bp'])} | **{r['verdict']}** |")
    n_side = res["n_trials"] // 2
    chosen = "; ".join(f"{r['side']} {r['chosen_by']}" for _, r in S[S["pick"] == "best"].iterrows()) if len(S) else ""
    L += ["", f"'best' = the highest discovery Sharpe among cells that meet the discovery half of their own rule (lower bound > 0; a "
              f"ranked cell's excess too: lower bound > 0 and p (search) below {CFG['excess_padj_max']}); it is the cell the gates, exits, "
              f"combined book and regimes use ({chosen}).", "",
          f"White's Reality Check (the best of the {n_side} F1 cells per side vs zero, discovery): L p = {_f(rc.get('F1 L', np.nan), 3)}, "
          f"S p = {_f(rc.get('F1 S', np.nan), 3)}.", ""]
    FA = S[~S["pick"].str.startswith("median")] if len(S) else S
    if len(FA) and "disc_same_bar_stop_share" in FA.columns:
        L += ["Fill audit of the selected cells (discovery): trades stopped inside their entry bar (booked at the worst order: entry, "
              "then the full stop) and trades with a missing bar between entry and exit (a hidden bar could hide a stop):", "",
              "| side | pick | stopped in the entry bar | missing bar inside the trade |", "|---|---|---|---|"]
        for _, r in FA.iterrows():
            sb_, gp_ = r.get("disc_same_bar_stop_share", np.nan), r.get("disc_gap_in_trade_share", np.nan)
            L.append(f"| {r['side']} | {r['pick']} | {sb_ * 100:.1f}% | {gp_ * 100:.2f}% |" if np.isfinite(sb_) and np.isfinite(gp_)
                     else f"| {r['side']} | {r['pick']} | n/a | n/a |")
        L.append("")
    VA = S[S["score"].isin(["mfe", "rvxmfe"]) & ~S["pick"].str.startswith("median")] if len(S) else S
    if len(VA) and "disc_vs_atr_bp" in VA.columns:
        L += ["Is the memory more than volatility? Each memory pick minus the ATR control with the same range, N and stop, paired by day "
              "(reported; not a verdict rule):", "", "| side | pick | discovery | confirmation | after CAS |", "|---|---|---|---|---|"]
        for _, r in VA.iterrows():
            L.append(f"| {r['side']} | {r['pick']} | {_ci(r['disc_vs_atr_bp'], r['disc_vs_atr_lo_bp'], r['disc_vs_atr_hi_bp'])} | "
                     f"{_ci(r['conf_vs_atr_bp'], r['conf_vs_atr_lo_bp'], r['conf_vs_atr_hi_bp'])} | {_f(r['post_vs_atr_bp'])} |")
        L.append("")
    C = res.get("combined") or {}
    if C:
        L += [f"Combined book (half the capital in each side's selected cell: L {C['cells']['L']}, S {C['cells']['S']}; reported, no verdict): "
              f"discovery {_ci(C['disc_mean_bp'], C['disc_lo_bp'], C['disc_hi_bp'])} bp/day, Sharpe {_f(C['disc_sharpe'], 2)}, "
              f"drawdown {_f(C['disc_maxdd_pct'], 2)}%; confirmation {_ci(C['conf_mean_bp'], C['conf_lo_bp'], C['conf_hi_bp'])}, "
              f"Sharpe {_f(C['conf_sharpe'], 2)}; after CAS {_f(C['post_mean_bp'])}.", ""]
    TH = res.get("thin_days")
    if TH is not None and len(TH):
        L += ["Days on which a side had fewer than N candidates (part of an N-slot book sits in cash; the excess benchmark holds the same "
              "cash, so this is not counted as skill):", "", "| side | range bars | top N | discovery | confirmation | after CAS |", "|---|---|---|---|---|---|"]
        for _, r in TH.iterrows():
            L.append(f"| {r['side']} | {r['or_bars']} | {r['top_n']} | {r['disc_thin_days']} of {r['disc_days']} | {r['conf_thin_days']} of "
                     f"{r['conf_days']} | {r['post_thin_days']} of {r['post_days']} |")
        L.append("")
    L += ["## RV x MFE: does the memory add to opening volume (and the reverse)?", "",
          "Paired daily difference in bp of book capital, pooled over the 12 (range, N, stop) combinations.", "",
          "| side | RVxMFE minus | discovery | confirmation | after CAS | adds |", "|---|---|---|---|---|---|"]
    if len(Cm):
        for _, r in Cm[Cm["or_bars"] == "pooled"].iterrows():
            L.append(f"| {r['side']} | {r['vs']} | {_ci(r['disc_diff_bp'], r['disc_lo_bp'], r['disc_hi_bp'])} | "
                     f"{_ci(r['conf_diff_bp'], r['conf_lo_bp'], r['conf_hi_bp'])} | {_f(r['post_diff_bp'])} | {_yes(r.get('adds'))} |")
    L += ["", "## Direction gates (F2) and path management (F3), on each side's selected cell", "",
          "'adds' = paired discovery lower bound > 0 and paired confirmation mean > 0; a gate can only add to a cell that makes money in "
          "discovery (on a losing cell, trading less always looks better). A gate that cannot judge a stock-day (no NIFTY bars, no sector "
          "or liquid peer, no beta) lets it through; 'judged' is the share of the cell's discovery picks it could judge. A variant of a "
          "ranked cell must also beat the same variant on the matched PLAIN book ('excess'), and its base cell's ranking must survive "
          "the search (the base's p (search) above).", "",
          "| side | variant | judged | discovery bp/day | vs base (paired) | excess | confirmation bp/day | vs base | FDR | verdict | adds |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in V.iterrows():
        jd = f"{r['disc_evaluable_share'] * 100:.0f}%" if np.isfinite(r.get("disc_evaluable_share", np.nan)) else "-"
        ex = _ci(r.get("disc_excess_bp", np.nan), r.get("disc_excess_lo_bp", np.nan), r.get("disc_excess_hi_bp", np.nan)) if "disc_excess_bp" in r and np.isfinite(r.get("disc_excess_bp", np.nan)) else "-"
        L.append(f"| {r['side']} | {r['variant']} | {jd} | {_ci(r['disc_mean_bp'], r['disc_lo_bp'], r['disc_hi_bp'])} | "
                 f"{_ci(r['disc_diff_bp'], r['disc_diff_lo_bp'], r['disc_diff_hi_bp'])} | {ex} | {_ci(r['conf_mean_bp'], r['conf_lo_bp'], r['conf_hi_bp'])} | "
                 f"{_ci(r['conf_diff_bp'], r['conf_diff_lo_bp'], r['conf_diff_hi_bp'])} | {_yes(r.get('disc_fdr'))} | {r['verdict']} | {_yes(r['adds'])} |")
    rcf = ", ".join(f"{k} p = {_f(v, 3)}" for k, v in rc.items() if k.startswith(("F2", "F3")))
    if rcf:
        L += ["", f"White's Reality Check on the best improvement over the base cell, within each family and side: {rcf}. "
                  "FDR here is on the paired improvement."]
    L += ["", "## NIFTY noise-boundary sleeve (F4, futures costs, spot index as stand-in)", "",
          "| cell | discovery bp/day | Sharpe | trades | per trade bp | FDR | confirmation bp/day | Sharpe | after CAS | verdict |", "|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in SL.iterrows():
        L.append(f"| {r['cell']} | {_ci(r['disc_mean_bp'], r['disc_lo_bp'], r['disc_hi_bp'])} | {_f(r['disc_sharpe'], 2)} | {r['disc_trades']} | "
                 f"{_f(r['disc_net_per_trade_bp'])} | {_yes(r.get('disc_fdr'))} | {_ci(r['conf_mean_bp'], r['conf_lo_bp'], r['conf_hi_bp'])} | "
                 f"{_f(r['conf_sharpe'], 2)} | {_f(r['post_mean_bp'])} | {r['verdict']} |")
    if "F4" in rc:
        L += ["", f"White's Reality Check over the 6 sleeve cells: p = {_f(rc['F4'], 3)}."]
    C_ = res["cells"]
    L += ["", "## Controls (never selected): is the ranking worth anything?", "",
          "A random ranking must show no excess over the matched PLAIN book (if it does, the benchmark is broken); ATR alone asks whether "
          "the memory is more than volatility.", "",
          "| side | control | range bars | top N | stop | discovery bp/day | excess | per trade bp | confirmation bp/day |", "|---|---|---|---|---|---|---|---|---|"]
    for _, r in C_[C_["family"] == "control"].iterrows():
        L.append(f"| {r['side']} | {r['score']} | {r['or_bars']} | {r['top_n']} | {r['stop']} | {_ci(r['disc_mean_bp'], r['disc_lo_bp'], r['disc_hi_bp'])} | "
                 f"{_ci(r['disc_excess_bp'], r['disc_excess_lo_bp'], r['disc_excess_hi_bp'])} | {_f(r['disc_net_per_trade_bp'])} | {_f(r['conf_mean_bp'])} |")
    RG = res.get("regimes")
    if RG is not None and len(RG):
        cols = [c for c in RG.columns if c not in ("from", "to", "days")]
        L += ["", "## Regimes (bp/day between the declared dates; reported, never used for selection)", "",
              "| from | to | days | " + " | ".join(cols) + " |", "|" + "---|" * (3 + len(cols))]
        for _, r in RG.iterrows():
            L.append(f"| {r['from']} | {r['to']} | {r['days']} | " + " | ".join(_f(r[c]) for c in cols) + " |")
    L += ["", "## Limits (from the declaration)", ""] + [f"- {x}" for x in DECL["limitations_stated_in_report"]]
    L += ["", "Every cell with all statistics is in cells.csv; daily book returns in daily_returns.parquet; trades of the selected cells in "
          "trades_selected.parquet; gates.csv, exits.csv, comparison.csv, nifty_sleeve.csv, thin_days.csv, regimes.csv.", ""]
    (out_dir / "report.md").write_text("\n".join(L), encoding="utf-8")


def _memory_line(m: Optional[dict]) -> str:
    if not m:
        return "Candidates without a memory score: not counted."
    parts = [f"{r}-bar range {v['without']:,} of {v['all']:,} ({v['without'] / max(v['all'], 1) * 100:.2f}%)" for r, v in m.items()]
    return ("Candidates dropped from every book for lack of a memory score (a stock's first months after listing, declared): "
            + "; ".join(parts) + ".")


def save(res: dict, out_dir: Path, sha: str, cov: dict, cands: Dict[int, pd.DataFrame]) -> None:
    out_dir.mkdir(parents=True, exist_ok=False)
    res["cells"].to_csv(out_dir / "cells.csv", index=False)
    res["selected"].to_csv(out_dir / "selected.csv", index=False)
    V = res["variants"]
    for fam, fn in (("F2", "gates.csv"), ("F3", "exits.csv")):
        (V[V["family"] == fam] if len(V) else V).to_csv(out_dir / fn, index=False)
    res["comparison"].to_csv(out_dir / "comparison.csv", index=False)
    res["sleeve"].to_csv(out_dir / "nifty_sleeve.csv", index=False)
    res["thin_days"].to_csv(out_dir / "thin_days.csv", index=False)
    res["regimes"].to_csv(out_dir / "regimes.csv", index=False)
    cal = pd.DatetimeIndex(res["calendar"])
    D = pd.DataFrame({"|".join(map(str, k)): v[1.0] for k, v in res["daily"].items()}, index=cal)
    D.index.name = "day"
    D.reset_index().to_parquet(out_dir / "daily_returns.parquet", index=False)
    parts = []
    for _, r in res["selected"].iterrows():
        key = (r["side"], r["score"], int(r["or_bars"]), int(r["top_n"]), r["stop"])
        T = picks_of(cands, key, res["calendar"])
        T = T[T["day"].isin(cal)]
        if not len(T):
            continue
        st = r["stop"]                                           # this cell's stop columns, under stop-free names
        names = {"day": "day", "symbol": "symbol", "side": "side", "rv": "rv", "mfe": "mfe", "atr": "atr", "w": "weight",
                 f"g_base_{st}": "gross", "net": "net", f"k_base_{st}": "exit_kind", f"e_{st}": "entry_bar", f"x_{st}": "exit_bar",
                 f"risk_{st}": "risk_bp"}
        P = T[[c for c in names if c in T.columns]].rename(columns=names)
        P["symbol"] = P["symbol"].astype(str)
        parts.append(P.assign(cell="|".join(map(str, key)), pick=r["pick"]))
    if parts:
        pd.concat(parts, ignore_index=True).to_parquet(out_dir / "trades_selected.parquet", index=False)
    (out_dir / "coverage.json").write_text(json.dumps(cov, indent=2, default=str), encoding="utf-8")
    write_report(out_dir, res, sha, cov)
    S = res["selected"]
    verd = (S[[c_ for c_ in ("side", "pick", "score", "or_bars", "top_n", "stop", "verdict", "disc_excess_padj") if c_ in S.columns]]
            .rename(columns={"disc_excess_padj": "excess_p_search"}).to_dict("records") if len(S) else [])
    for r_ in verd:                                              # plain cells have no excess: null, not NaN
        if "excess_p_search" in r_ and not (isinstance(r_["excess_p_search"], (int, float)) and np.isfinite(r_["excess_p_search"])):
            r_["excess_p_search"] = None
    vv = V[["side", "family", "variant", "on_cell", "verdict", "adds"]].to_dict("records") if len(V) else []
    SL = res["sleeve"]
    sv = SL.loc[SL["selected"], ["cell", "verdict"]].to_dict("records") if len(SL) else []
    comb = {k: v for k, v in (res.get("combined") or {}).items() if k == "cells" or k.endswith(("mean_bp", "lo_bp", "hi_bp", "sharpe"))}
    (out_dir / "summary.json").write_text(json.dumps({"tool": CODE_VERSION, "declaration": sha, "coverage": cov, "windows": res["windows"],
                                                      "reality_check": res["reality_check"], "verdicts": verd, "variant_verdicts": vv,
                                                      "sleeve_verdict": sv, "combined_book": comb, "cost_bps_round_trip": COST_BPS},
                                                     indent=2, default=str), encoding="utf-8")


# ----------------------------------------------------------------------
# the run
# ----------------------------------------------------------------------
def equity_symbols(root: Path, dq, etf_isin: set) -> List[str]:
    syms = dq.discover_symbols(root) if hasattr(dq, "discover_symbols") else []
    out = []
    for s in syms:
        u = str(s).upper()
        if u in INDEX_NAMES or ETF_RE.search(u) or u in etf_isin:
            continue
        if hasattr(dq, "_read_ok"):
            meta = dq._read_ok(Path(dq._paths(root, s)[1])) or {}
            if meta.get("series_kind", "equity") != "equity":
                continue
        out.append(s)
    return out


def load_nifty(root: Path, dq, IC) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], str]:
    nd, note = None, []
    fp = Path(dq._paths(root, "NIFTY50")[0])
    if fp.exists():
        nd = pd.read_parquet(fp)
        nd["day"] = SI._naive_days(nd["timestamp"]).to_numpy()
        nd = nd.sort_values("day").drop_duplicates("day", keep="last").reset_index(drop=True)
    else:
        note.append(f"{fp.name} not found")
    nb = None
    for nm in NIFTY_NAMES:
        f = IC.store(root) / f"{nm}_{IC.BAR_MIN}m.parquet"
        if f.exists():
            nb = pd.read_parquet(f)
            note.append(f"bars {f.name}")
            break
    if nb is None:
        note.append("no NIFTY 3-minute file (gates and sleeve not run)")
    return nd, nb, "; ".join(note)


def bar_days(path: Path) -> pd.DatetimeIndex:
    """The sessions (IST dates) a 3-minute file has any bar for; only its timestamp column is read."""
    try:
        ts = pd.read_parquet(path, columns=["timestamp"])["timestamp"]
    except Exception:
        return pd.DatetimeIndex([])
    return pd.DatetimeIndex(ist_naive(ts).dt.normalize().unique()).sort_values()


def coverage(root: Path, syms: List[str], dq, IC, start: str) -> Tuple[dict, Dict[str, pd.DataFrame], List[str], pd.DataFrame, pd.DataFrame]:
    """Liquid stock-days (point in time) from the start of the windows to the last day any 3-minute file reaches, and how
    many of them have a 3-minute session. Stocks with under 90% of their liquid days covered go to missing_liquid.txt."""
    t0 = pd.Timestamp(start)
    feats, per = {}, []
    for s in syms:
        fp = Path(dq._paths(root, s)[0])
        try:
            daily = pd.read_parquet(fp, columns=["timestamp", "open", "high", "low", "close", "volume"])
        except Exception:
            continue
        F = daily_features(daily)
        lq = liquid_ok(F) & (F["day"] >= t0).to_numpy()
        if not lq.any():
            continue
        feats[s] = F
        f = IC.store(root) / f"{s}_{IC.BAR_MIN}m.parquet"
        per.append((s, pd.DatetimeIndex(F.loc[lq, "day"]), bar_days(f) if f.exists() else pd.DatetimeIndex([])))
    ends = [h.max() for _, _, h in per if len(h)]
    last_bar = max(ends) if ends else None
    rows, liquid_days, covered_days, missing, mon = [], 0, 0, [], []
    for s, dl, have in per:
        if last_bar is not None:
            dl = dl[dl <= last_bar]
        hit = dl.isin(have)
        n, c = len(dl), int(hit.sum())
        liquid_days += n
        covered_days += c
        rows.append({"symbol": s, "liquid_days": n, "days_with_bars": c})
        if n >= 20 and c < CFG["min_coverage"] * n:
            missing.append(s)
        if n:
            mon.append(pd.DataFrame({"month": dl.to_period("M").astype(str), "liquid": 1, "with_bars": hit.astype(int)}))
    by_month = (pd.concat(mon).groupby("month")[["liquid", "with_bars"]].sum().reset_index() if mon
                else pd.DataFrame(columns=["month", "liquid", "with_bars"]))
    cov = {"liquid_stocks": len(feats), "liquid_stock_days": liquid_days, "covered_stock_days": covered_days,
           "covered_share": covered_days / liquid_days if liquid_days else float("nan"), "missing_liquid_stocks": len(missing),
           "last_bar_day": str(last_bar.date()) if last_bar is not None else None}
    return cov, feats, sorted(missing), pd.DataFrame(rows), by_month


def write_ledger(root: Path, record: dict) -> str:
    """Append this run to the project's research ledger (<root>\\panel\\research_ledger.jsonl, append-only)."""
    d = root / "panel"
    if not d.is_dir():
        return "not written (no panel folder under the root)"
    with open(d / "research_ledger.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"at": dt.datetime.now().isoformat(), **record}, default=str) + "\n")
    return str(d / "research_ledger.jsonl")


def previous_runs(root: Path) -> List[dict]:
    """Earlier runs of this family in the research ledger (their confirmation window has been seen)."""
    f = root / "panel" / "research_ledger.jsonl"
    out = []
    if not f.exists():
        return out
    for line in f.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("family") == DECL["family_id"] and rec.get("kind") == "exploration":
            out.append({"run": rec.get("run"), "at": rec.get("at"), "declaration": rec.get("declaration")})
    return out


def _sha_path(p) -> Optional[str]:
    try:
        return hashlib.sha256(Path(p).read_bytes()).hexdigest()[:16]
    except Exception:
        return None


def data_fingerprint(cands: Dict[int, pd.DataFrame], calendar: np.ndarray, nifty_bars: Optional[pd.DataFrame]) -> str:
    """A hash of everything the books are built from: the calendar, every candidate row with every outcome, NIFTY's bars."""
    h = hashlib.sha256(np.asarray(calendar, dtype="datetime64[ns]").astype(np.int64).tobytes())
    for r_ in sorted(cands):
        Cd = cands[r_]
        num = [c for c in Cd.columns if c not in ("symbol", "sector")]
        h.update(pd.util.hash_pandas_object(Cd[num], index=False).to_numpy().tobytes())
        h.update(pd.util.hash_pandas_object(Cd["symbol"].astype(str), index=False).to_numpy().tobytes())
    if nifty_bars is not None and len(nifty_bars):
        h.update(pd.util.hash_pandas_object(nifty_bars[["open", "high", "low", "close"]], index=False).to_numpy().tobytes())
    return h.hexdigest()[:16]


_WARNINGS: List[str] = []


def _record_warning(message, category, filename, lineno, file=None, line=None):
    _WARNINGS.append(f"{category.__name__}: {message} ({Path(str(filename)).name}:{lineno})")
    _record_warning.original(message, category, filename, lineno, file, line)


def provenance(out_dir: Path, sha: str, cands: Dict[int, pd.DataFrame], calendar: np.ndarray, nifty_bars, dq, IC) -> dict:
    try:
        import pyarrow
        pa_v = pyarrow.__version__
    except Exception:
        pa_v = None
    return {"tool": CODE_VERSION, "declaration": sha,
            "code_sha256_16": {"bigmove_study.py": _sha_path(Path(__file__)), "soul_intraday_study.py": _sha_path(getattr(SI, "__file__", "")),
                               "data_quality.py": _sha_path(getattr(dq, "__file__", "") or ""),
                               "intraday_cache.py": _sha_path(getattr(IC, "__file__", "") or "")},
            "python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__, "pyarrow": pa_v,
            "platform": platform.platform(), "seed": CFG["seed"], "boot_B": CFG["boot_B"], "boot_block": CFG["boot_block"],
            "data_fingerprint": data_fingerprint(cands, calendar, nifty_bars),
            "candidate_rows": {str(r_): int(len(v)) for r_, v in cands.items()},
            "warnings": sorted(set(_WARNINGS))[:100]}


def seal_outputs(out_dir: Path, prov: dict) -> None:
    """Add provenance and every output file's hash to summary.json, then write outputs.sha256 for all files."""
    files = sorted(f for f in out_dir.iterdir() if f.is_file() and f.name not in ("summary.json", "outputs.sha256"))
    prov["outputs_sha256_16"] = {f.name: _sha_path(f) for f in files}
    sp = out_dir / "summary.json"
    summ = json.loads(sp.read_text(encoding="utf-8"))
    summ["provenance"] = prov
    sp.write_text(json.dumps(summ, indent=2, default=str), encoding="utf-8")
    lines = [f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.name}" for f in files + [sp]]
    (out_dir / "outputs.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    """Runs the study, recording every warning shown on the way (they go into the provenance)."""
    _WARNINGS.clear()
    _record_warning.original = warnings.showwarning
    warnings.showwarning = _record_warning
    try:
        return _main(argv)
    finally:
        warnings.showwarning = _record_warning.original


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="BIGMOVE v1: intraday breakout study (stocks in play, long and short, NIFTY sleeve)")
    ap.add_argument("--root", required=True)
    ap.add_argument("--coverage-only", action="store_true", help="report 3-minute coverage of the liquid universe and write missing_liquid.txt")
    ap.add_argument("--allow-partial-universe", action="store_true", help="run even when under 90%% of liquid stock-days have 3-minute bars")
    a = ap.parse_args(argv)
    root = Path(a.root)
    if not root.is_dir():
        raise PreconditionError(f"--root {root} is not a folder - run 'call env_daily.bat' and pass --root %CACHE_DAILY_ROOT%")
    sha = hashlib.sha256(DECL_RAW).hexdigest()[:16]
    import data_quality as dq
    import intraday_cache as IC
    secmap, etf_set, lists_used = read_lists(root)
    syms = equity_symbols(root, dq, etf_set)
    if not syms:
        raise PreconditionError("no equity daily files found - check CACHE_DAILY_ROOT")
    etf_note = (f"ETF list read ({len(etf_set):,} ETF symbols from {', '.join(f for f in lists_used if 'etf' in f.lower()) or 'ISIN columns'})"
                if etf_set else "NO ETF list in <root>\\sectors\\ - only the name rule excludes ETFs (save NSE's eq_etfseclist.csv there)")
    _log(f"{CODE_VERSION}: {len(syms):,} equity symbols; {etf_note}")
    _log("  measuring the liquid universe's 3-minute coverage (days, not files)")
    cov, feats, missing, by_stock, by_month = coverage(root, syms, dq, IC, CFG["discovery_start"])
    cov["etf_list"] = etf_note
    base = root / "research2" / "bigmove"
    base.mkdir(parents=True, exist_ok=True)
    (base / "missing_liquid.txt").write_text("\n".join(missing) + ("\n" if missing else ""), encoding="utf-8")
    by_stock.to_csv(base / "coverage_by_stock.csv", index=False)
    _log(f"  liquid stock-days {cov['liquid_stock_days']:,} (to {cov['last_bar_day']}); with a 3-minute session "
         f"{cov['covered_share'] * 100:.1f}%; {len(missing)} liquid stocks under 90% covered -> {base / 'missing_liquid.txt'}")
    nd, nb, nnote = load_nifty(root, dq, IC)
    cov["nifty"] = nnote
    cov["sectors"] = f"{len(secmap)} symbols mapped" if secmap else "no sector files (sector gate not run)"
    _log(f"  NIFTY: {nnote}; sectors: {cov['sectors']}")
    if a.coverage_only:
        return 0
    if not (cov["covered_share"] >= CFG["min_coverage"]) and not a.allow_partial_universe:
        raise PreconditionError(f"only {cov['covered_share'] * 100:.1f}% of liquid stock-days have 3-minute bars (need "
                                f"{CFG['min_coverage'] * 100:.0f}%): fetch the stocks in missing_liquid.txt with the intraday cacher "
                                f"(full history), or rerun with --allow-partial-universe (the report will say so)")
    prev = previous_runs(root)
    cov["previous_runs"] = prev
    if prev:
        _log(f"  WARNING: rerun #{len(prev) + 1} of {DECL['family_id']} - the confirmation window was already seen in "
             f"{', '.join(str(x['run']) for x in prev)}; this run's results are NOT fresh evidence (the report says so)")
    nifty = nifty_context(nb)
    tol_p, tol_v = IC.DECL["reconcile_price_tol"], IC.DECL["reconcile_volume_tol"]
    t0 = pd.Timestamp(CFG["discovery_start"])
    t_hist = t0 - pd.Timedelta(days=int(CFG["rv_history_days_before_start"]))   # bars before the windows: RV history only
    last_bar = pd.Timestamp(cov["last_bar_day"]) if cov["last_bar_day"] else None
    hyg = {"sessions_with_bars": 0, "failed_reconciliation": 0, "no_first_bar_or_under_80pct_bars": 0, "unreadable_files": 0}

    def load_bars(s: str, count: bool = False):
        f = IC.store(root) / f"{s}_{IC.BAR_MIN}m.parquet"
        if not f.exists():
            return None, None
        try:                                                     # the cache's own reconciliation, on the files as stored
            X = pd.read_parquet(f)
            daily = pd.read_parquet(Path(dq._paths(root, s)[0]), columns=["timestamp", "open", "high", "low", "close", "volume"])
            J = IC.reconcile_symbol(X, daily, tol_p, tol_v)
        except Exception as e:                                   # one unreadable file must not stop the study
            if count:
                hyg["unreadable_files"] += 1
                _log(f"  WARNING {s}: 3-minute file not usable ({type(e).__name__}: {e}) - skipped")
            return None, None
        if not len(J):
            return None, None
        X = X.assign(timestamp=ist_naive(X["timestamp"]).to_numpy())
        jd = ist_naive(pd.to_datetime(J["day"])).dt.normalize()
        okc = J["ok"].eq(True).to_numpy()                        # a missing verdict is not a pass
        if count:                                                # whole-session data checks, counted for the report
            w_ = (jd >= t0).to_numpy()
            hyg["sessions_with_bars"] += int(w_.sum())
            hyg["failed_reconciliation"] += int((w_ & ~okc).sum())
        ok = pd.DatetimeIndex(jd[okc])
        X = X[X["timestamp"].dt.normalize().isin(ok) & (X["timestamp"] >= t_hist)]
        days, B = bar_matrix(X)
        if count and len(days):
            hyg["no_first_bar_or_under_80pct_bars"] += int((~usable_sessions(B)[days >= np.datetime64(t0)]).sum())
        return days, B

    cal_days = set()
    for F in feats.values():                                     # the market calendar, from the daily files
        cal_days.update(pd.DatetimeIndex(F.loc[F["day"] >= t0, "day"]))
    calendar = np.array(sorted(cal_days), dtype="datetime64[ns]")
    stocks = [s for s in feats if (IC.store(root) / f"{s}_{IC.BAR_MIN}m.parquet").exists()]
    sp = None
    if secmap:                                                   # pass 0: sector paths of the liquid stocks
        _log(f"pass 0: sector paths ({len(secmap):,} symbols mapped)")
        sp = SectorPaths(calendar, [secmap[s.upper()] for s in stocks if s.upper() in secmap])
        for s in stocks:
            sec = secmap.get(s.upper())
            if not sec:
                continue
            days, B = load_bars(s)
            if days is None or not len(days):
                continue
            sp.add(sec, *sector_sessions(feats[s], days, B, liquid_ok(feats[s])))
    _log(f"pass 1: {len(stocks):,} stocks (relative volume, memory, every variant's fills)")
    parts = {1: [], 2: []}
    first, last, usable_days, usable_by, use_mon = None, None, 0, {}, []
    for k, s in enumerate(stocks):
        days, B = load_bars(s, count=True)
        if days is None or not len(days):
            continue
        inwin = days >= np.datetime64(t0)
        if inwin.any():
            first = days[inwin].min() if first is None else min(first, days[inwin].min())
            last = days[inwin].max() if last is None else max(last, days[inwin].max())
        F = feats[s]
        lq = pd.DatetimeIndex(F.loc[liquid_ok(F) & (F["day"] >= t0).to_numpy(), "day"])
        if last_bar is not None:
            lq = lq[lq <= last_bar]
        u_ = lq.isin(pd.DatetimeIndex(days[usable_sessions(B)]))
        usable_by[s] = int(u_.sum())
        usable_days += usable_by[s]
        if len(lq):
            use_mon.append(pd.DataFrame({"month": lq.to_period("M").astype(str), "usable": u_.astype(int)}))
        rows = stock_rows(s, F, days, B, liquid_ok(F), nifty, beta_series(F, nd), secmap.get(s.upper()), sp, first_day=t0)
        for r_, df in rows.items():
            parts[r_].append(df)
        if (k + 1) % 100 == 0:
            _log(f"  {k + 1:,}/{len(stocks):,}")
    cov["usable_stock_days"] = usable_days
    cov["usable_share"] = usable_days / cov["liquid_stock_days"] if cov["liquid_stock_days"] else float("nan")
    cov["data_hygiene"] = hyg
    by_stock["usable_days"] = by_stock["symbol"].map(usable_by).fillna(0).astype(int)
    by_stock.to_csv(base / "coverage_by_stock.csv", index=False)
    _log(f"  usable after reconciliation and the 80% rule: {cov['usable_share'] * 100:.1f}% of liquid stock-days")
    if not (cov["usable_share"] >= CFG["min_coverage"]) and not a.allow_partial_universe:
        raise PreconditionError(f"after reconciliation only {cov['usable_share'] * 100:.1f}% of liquid stock-days are usable (need "
                                f"{CFG['min_coverage'] * 100:.0f}%; {hyg['failed_reconciliation']:,} sessions failed reconciliation, "
                                f"{hyg['no_first_bar_or_under_80pct_bars']:,} had under 80% of bars): check the 3-minute data, or rerun "
                                f"with --allow-partial-universe (the report will say so)")
    cands, no_mem = {}, {}
    for r_, lst in parts.items():
        if lst:
            Cd = pd.concat(lst, ignore_index=True)
            Cd["symbol"] = Cd["symbol"].astype("category")
            no_mem[r_] = {"without": int((np.isfinite(Cd["rv"]) & ~np.isfinite(Cd["mfe"])).sum()), "all": int(np.isfinite(Cd["rv"]).sum())}
            cands[r_] = add_scores(Cd)
    cov["candidates_without_memory"] = no_mem
    hyg["triggered_without_exit_price"] = int(sum(int(Cd[[c_ for c_ in Cd.columns if c_.startswith("nx_")]].any(axis=1).sum())
                                                  for Cd in cands.values()))           # stock-days (per opening range), any stop
    um = pd.concat(use_mon).groupby("month")["usable"].sum() if use_mon else pd.Series(dtype=int)
    by_month = by_month.set_index("month")
    by_month["usable"] = um.reindex(by_month.index).fillna(0).astype(int)
    by_month["usable_share"] = by_month["usable"] / by_month["liquid"].where(by_month["liquid"] > 0)
    for r_, Cd in cands.items():
        cm = Cd.assign(month=pd.DatetimeIndex(Cd["day"]).to_period("M").astype(str)).groupby(["month", "side"]).size().unstack(fill_value=0)
        for sd, nm in ((1, "L"), (-1, "S")):
            by_month[f"candidates_{nm}_r{r_}"] = (cm[sd] if sd in cm.columns else pd.Series(dtype=int)).reindex(by_month.index).fillna(0).astype(int)
    by_month = by_month.reset_index()
    by_month.to_csv(base / "universe_by_month.csv", index=False)
    bm_ = by_month[by_month["liquid"] > 0]
    cov["usable_share_by_month"] = {"min": float(bm_["usable_share"].min()) if len(bm_) else None,
                                    "min_month": str(bm_.loc[bm_["usable_share"].idxmin(), "month"]) if len(bm_) else None,
                                    "months_under_90pct": bm_.loc[bm_["usable_share"] < CFG["min_coverage"], "month"].tolist()}
    if not cands or first is None:
        raise PreconditionError("no candidate sessions - check the 3-minute data and the liquidity rule")
    first_c = min(Cd["day"].min() for Cd in cands.values())    # the first day any stock could be a candidate (RV needs 10 sessions)
    calendar = calendar[(calendar >= np.datetime64(first_c)) & (calendar <= last)]   # cash days inside it count
    cov["bar_period"] = f"{pd.Timestamp(first).date()} to {pd.Timestamp(last).date()}; books from {pd.Timestamp(first_c).date()}"
    _log(f"pass 2: books ({', '.join(f'{len(v):,} candidates with a {r_}-bar range' for r_, v in cands.items())})")
    res = run_books(cands, calendar, nifty_sleeve(nb, nd, calendar), _log)
    day = dt.date.today().strftime("%Y%m%d")
    k = 1
    while (base / f"BM_{day}_{k:03d}").exists():
        k += 1
    out = base / f"BM_{day}_{k:03d}"
    save(res, out, sha, cov, cands)
    seal_outputs(out, provenance(out, sha, cands, calendar, nb, dq, IC))
    S = res["selected"]
    picks = S[~S["pick"].str.startswith("median")]
    V = res["variants"]
    led = write_ledger(root, {"kind": "exploration", "tool": CODE_VERSION, "family": DECL["family_id"], "declaration": sha,
                              "run": out.name, "trials_F1": res["n_trials"], "confirmation_used": True,
                              "fresh_confirmation": not prev, "previous_runs": [x["run"] for x in prev],
                              "coverage_share": cov.get("usable_share"), "reality_check": res["reality_check"],
                              "picks": picks[["side", "pick", "score", "or_bars", "top_n", "stop", "verdict"]].to_dict("records"),
                              "variants": V[["side", "variant", "verdict", "adds"]].to_dict("records") if len(V) else [],
                              "sleeve": res["sleeve"].loc[res["sleeve"]["selected"], ["cell", "verdict"]].to_dict("records") if len(res["sleeve"]) else []})
    for _, r in picks.iterrows():
        _log(f"  {r['side']} {r['pick']:12s} {r['score']:7s} | {r['or_bars']} bar | top {r['top_n']:>2} | stop {r['stop']:5s}: "
             f"discovery {_f(r['disc_mean_bp'])} bp/day, confirmation {_f(r['conf_mean_bp'])} -> {r['verdict']}")
    print(f"  report: {out / 'report.md'}")
    print(f"  research ledger: {led}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
