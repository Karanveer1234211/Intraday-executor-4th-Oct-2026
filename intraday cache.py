#!/usr/bin/env python3
"""
intraday_cache.py - 3-minute bars for the stocks the frozen engines picked (coarser bars derived).

    python intraday_cache.py import --root %CACHE_DAILY_ROOT% --src <folder or file> --dry-run
    python intraday_cache.py import --root %CACHE_DAILY_ROOT% --src <folder or file>
    python intraday_cache.py update --root %CACHE_DAILY_ROOT% [--start 2021-10-01]
    python intraday_cache.py check  --root %CACHE_DAILY_ROOT%

Second pipeline. Writes only to <root>\\intraday_3m\\ (one <SYMBOL>_3m.parquet per
stock: timestamp in IST, open, high, low, close, volume - one row per 3-minute bar,
09:15 to 15:27 bar starts, 125 a session). resample() derives 15-minute or any coarser
bars from them, so there is one source of truth. Never touches the daily cache, the panels,
the paper ledger or anything frozen.

  import  existing 3-minute files (CSV or parquet; one file per stock named
          after it, or files with a 'symbol' column). Timestamps with a time zone are
          converted to IST; timestamps without one are taken as IST. Only bars inside
          the session are kept. --dry-run reports what it found and writes nothing.
  update  fetches from Kite (the same login and symbol lookup as Daily_cache_v27) for
          every stock frozen D or the ensemble ever had in its top 10, plus every paper
          pick: from the last cached bar (or --start) to the last COMPLETED session -
          today's bars count only after 15:45, as with the daily cache.
  check   reconciles every stock-day with the daily cache: first open, high, low and
          last close within 0.5%, volume within 10%. A ratio near 2, 3, 5 or 10 points
          at a different split-adjustment basis. Writes intraday_quality.csv.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import research_common as RC       # first: from a subfolder, this folder's copy must win
import stage_b_screen as SB        # noqa: E402

CODE_VERSION = "intraday_cache v1.2"   # v1.2: correct session-size label, no pandas warning on a first save (v1.1: 3-minute bars)
DECL = json.loads((HERE / "INTRADAY_DECLARATION.json").read_text(encoding="utf-8"))["config"]
COLS = ["timestamp", "open", "high", "low", "close", "volume"]
BAR_MIN = int(DECL["bar_minutes"])
FIRST_BAR = dt.time(9, 15)
LAST_BAR = (dt.datetime.combine(dt.date.today(), dt.time(15, 30)) - dt.timedelta(minutes=BAR_MIN)).time()
CHUNK_DAYS = 60
MIN_GAP_S = 0.35                      # about 3 requests a second, Kite's historical limit


class PreconditionError(SystemExit):
    pass


def _log(msg: str) -> None:
    print(f"{dt.datetime.now():%H:%M:%S}  {msg}", flush=True)


def store(root: Path) -> Path:
    return root / f"intraday_{BAR_MIN}m"


def path_for(root: Path, sym: str) -> Path:
    return store(root) / f"{sym}_{BAR_MIN}m.parquet"


# ----------------------------------------------------------------------
# normalising and saving
# ----------------------------------------------------------------------
def normalise(df: pd.DataFrame) -> pd.DataFrame:
    """Any intraday frame -> COLS, IST-naive timestamps, session bars on the declared grid only, sorted, no duplicates."""
    low = {c.lower().strip(): c for c in df.columns}
    tcol = next((low[k] for k in ("timestamp", "datetime", "date", "time") if k in low), None)
    if tcol is None:
        raise ValueError(f"no timestamp column in {list(df.columns)}")
    out = pd.DataFrame({"timestamp": pd.to_datetime(df[tcol], errors="coerce")})
    for c in ("open", "high", "low", "close", "volume"):
        if c not in low:
            raise ValueError(f"no '{c}' column in {list(df.columns)}")
        out[c] = pd.to_numeric(df[low[c]], errors="coerce")
    ts = out["timestamp"]
    if getattr(ts.dt, "tz", None) is not None:
        out["timestamp"] = ts.dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
    out = out.dropna(subset=["timestamp", "open", "high", "low", "close"])
    t = out["timestamp"].dt.time
    mins = out["timestamp"].dt.hour * 60 + out["timestamp"].dt.minute - (9 * 60 + 15)
    out = out[(t >= FIRST_BAR) & (t <= LAST_BAR) & (mins % BAR_MIN == 0) & (out["timestamp"].dt.second == 0)]
    out = out.drop_duplicates("timestamp", keep="last").sort_values("timestamp").reset_index(drop=True)
    out["volume"] = out["volume"].fillna(0.0)
    return out[COLS]


def resample(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Coarser bars from the stored ones, anchored at 09:15 each session (15 -> 09:15, 09:30, ... 15:15)."""
    if minutes % BAR_MIN:
        raise ValueError(f"{minutes} minutes is not a multiple of the {BAR_MIN}-minute bars")
    d = df.copy()
    day = d["timestamp"].dt.normalize()
    off = ((d["timestamp"] - day - pd.Timedelta(hours=9, minutes=15)) // pd.Timedelta(minutes=minutes)) * pd.Timedelta(minutes=minutes)
    d["bucket"] = day + pd.Timedelta(hours=9, minutes=15) + off
    g = d.sort_values("timestamp").groupby("bucket")
    out = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                        "close": g["close"].last(), "volume": g["volume"].sum()})
    return out.rename_axis("timestamp").reset_index()[COLS]


def merge_save(root: Path, sym: str, new: pd.DataFrame) -> int:
    """Merge new bars into the stock's file (new wins on overlap) and save atomically. Returns rows added."""
    store(root).mkdir(parents=True, exist_ok=True)
    fp = path_for(root, sym)
    old = pd.read_parquet(fp) if fp.exists() else None
    parts = [x for x in (old, new) if x is not None and len(x)]
    both = (pd.concat(parts, ignore_index=True) if len(parts) > 1 else (parts[0] if parts else new.iloc[0:0]))
    both = both.drop_duplicates("timestamp", keep="last").sort_values("timestamp")
    tmp = fp.with_suffix(".tmp")
    both.reset_index(drop=True).to_parquet(tmp, index=False)
    tmp.replace(fp)
    return int(len(both) - (len(old) if old is not None else 0))


# ----------------------------------------------------------------------
# import
# ----------------------------------------------------------------------
def symbol_from_name(p: Path) -> str:
    s = p.stem.upper()
    for suf in ("_3MINUTE", "_3MIN", "_3M", "-3MIN", "-3M", "_15MIN", "_15M", "-15MIN", "-15M", "_INTRADAY", "_NSE"):
        if s.endswith(suf):
            s = s[: -len(suf)]
    return s


def cmd_import(root: Path, src: Path, dry_run: bool) -> pd.DataFrame:
    files = [src] if src.is_file() else sorted(p for p in src.rglob("*") if p.suffix.lower() in (".csv", ".parquet"))
    if not files:
        raise PreconditionError(f"no CSV or parquet files under {src}")
    rows = []
    for fp in files:
        try:
            raw = pd.read_parquet(fp) if fp.suffix.lower() == ".parquet" else pd.read_csv(fp)
            low = {c.lower(): c for c in raw.columns}
            groups = raw.groupby(raw[low["symbol"]].astype(str).str.upper()) if "symbol" in low else [(symbol_from_name(fp), raw)]
            for sym, g in groups:
                df = normalise(g)
                added = 0 if dry_run else merge_save(root, sym, df)
                rows.append({"file": fp.name, "symbol": sym, "bars": len(df), "added": added,
                             "first": df["timestamp"].min(), "last": df["timestamp"].max(), "error": ""})
        except Exception as e:
            rows.append({"file": fp.name, "symbol": symbol_from_name(fp), "bars": 0, "added": 0, "error": f"{type(e).__name__}: {e}"})
    R = pd.DataFrame(rows)
    _log(f"import{' (DRY RUN - nothing written)' if dry_run else ''}: {len(files):,} files, {R['symbol'].nunique():,} stocks, "
         f"{int(R['bars'].sum()):,} bars, {int((R['error'] != '').sum())} files with errors")
    return R


# ----------------------------------------------------------------------
# update from Kite
# ----------------------------------------------------------------------
def get_provider():
    import Daily_cache_v27 as DC
    return DC.KiteProvider()


def last_complete_day(now: Optional[dt.datetime] = None) -> dt.date:
    now = now or dt.datetime.now()
    return now.date() if now.time() >= dt.time(15, 45) else now.date() - dt.timedelta(days=1)


def picked_symbols(root: Path) -> List[str]:
    import freeze_engines as FZ
    pp = root / "panel_oc" / "panel.parquet"
    man = FZ.verify_frozen(pp)
    extra = RC.load_symbol_list(root / RC.UNIVERSE_EXCLUDE_FILE)
    syms = set()
    for eng in ("D", "ENS"):
        pr = pd.read_parquet(pp.parent / "stage_d" / man["engines"][eng]["run"] / "preds.parquet")
        pr = pr[pr["target"].astype(str) == man["target"]]
        pr = pr[~pr["symbol"].astype(str).map(lambda s: RC.is_etf_symbol(s, extra))]
        pr = pr.sort_values(["timestamp", "score", "symbol"], ascending=[True, False, True])
        syms |= set(pr.groupby("timestamp").head(DECL["top"])["symbol"].astype(str))
    led = root / "paper" / "ledger.jsonl"
    if led.exists():
        syms |= {json.loads(l)["symbol"] for l in led.read_text(encoding="utf-8").splitlines() if l.strip()}
    return sorted(syms)


def fetch(provider, sym: str, start: dt.date, end: dt.date) -> pd.DataFrame:
    inst = provider._symbol_to_instrument_token(sym)
    parts, cur = [], start
    while cur <= end:
        hi = min(end, cur + dt.timedelta(days=CHUNK_DAYS - 1))
        t0 = time.perf_counter()
        rows = provider._hist(inst, dt.datetime.combine(cur, dt.time(9, 0)), dt.datetime.combine(hi, dt.time(15, 30)), DECL["interval"])
        if rows:
            parts.append(pd.DataFrame(rows))
        time.sleep(max(0.0, MIN_GAP_S - (time.perf_counter() - t0)))
        cur = hi + dt.timedelta(days=1)
    return normalise(pd.concat(parts, ignore_index=True)) if parts else pd.DataFrame(columns=COLS)


def cmd_update(root: Path, symbols: List[str], start: dt.date, now: Optional[dt.datetime] = None, provider=None) -> pd.DataFrame:
    end = last_complete_day(now)
    provider = provider or get_provider()
    rows = []
    for k, sym in enumerate(symbols, 1):
        fp = path_for(root, sym)
        s0 = start
        if fp.exists():
            last = pd.read_parquet(fp, columns=["timestamp"])["timestamp"].max()
            s0 = max(start, (pd.Timestamp(last) + pd.Timedelta(days=1)).date()) if pd.notna(last) else start
        if s0 > end:
            rows.append({"symbol": sym, "added": 0, "error": ""})
            continue
        try:
            df = fetch(provider, sym, s0, end)
            df = df[df["timestamp"].dt.date <= end]
            rows.append({"symbol": sym, "added": merge_save(root, sym, df) if len(df) else 0, "error": ""})
        except Exception as e:
            if type(e).__name__ == "AuthExpired":
                raise PreconditionError("the Kite token has expired - refresh it, then run update again (finished stocks are kept)")
            rows.append({"symbol": sym, "added": 0, "error": f"{type(e).__name__}: {e}"})
        if k % 50 == 0:
            _log(f"  {k:,}/{len(symbols):,} stocks")
    R = pd.DataFrame(rows)
    _log(f"update to {end}: {len(symbols):,} stocks, {int(R['added'].sum()):,} bars added, "
         f"{int((R['error'] != '').sum())} failed")
    return R


# ----------------------------------------------------------------------
# reconciliation with the daily cache
# ----------------------------------------------------------------------
def reconcile_symbol(intra: pd.DataFrame, daily: pd.DataFrame, tol_p: float, tol_v: float) -> pd.DataFrame:
    if intra.empty or daily.empty:
        return pd.DataFrame()
    g = intra.assign(day=intra["timestamp"].dt.normalize()).groupby("day")
    agg = pd.DataFrame({"i_open": g["open"].first(), "i_high": g["high"].max(), "i_low": g["low"].min(),
                        "i_close": g["close"].last(), "i_volume": g["volume"].sum(), "bars": g.size()})
    d = daily.copy()
    d["day"] = pd.to_datetime(d["timestamp"]).dt.tz_localize(None).dt.normalize() if getattr(pd.to_datetime(d["timestamp"]).dt, "tz", None) is not None \
        else pd.to_datetime(d["timestamp"]).dt.normalize()
    J = agg.join(d.set_index("day")[["open", "high", "low", "close", "volume"]], how="left")
    rel = lambda a, b: (J[a] / J[b] - 1).abs()
    J["price_ok"] = (rel("i_open", "open") <= tol_p) & (rel("i_high", "high") <= tol_p) & (rel("i_low", "low") <= tol_p) & \
                    (rel("i_close", "close") <= tol_p)
    J["volume_ok"] = (J["volume"] <= 0) | ((J["i_volume"] / J["volume"] - 1).abs() <= tol_v)
    J["ratio"] = J["close"] / J["i_close"]
    J["basis_mismatch"] = J["ratio"].round(1).isin([2.0, 3.0, 5.0, 10.0, 0.5]) & ~J["price_ok"]
    J["full_session"] = J["bars"] == DECL["bars_per_session"]
    J["ok"] = J["price_ok"] & J["volume_ok"] & J["open"].notna()
    return J.reset_index()


def cmd_check(root: Path) -> pd.DataFrame:
    from data_quality import _paths
    files = sorted(store(root).glob(f"*_{BAR_MIN}m.parquet"))
    if not files:
        raise PreconditionError(f"no intraday files in {store(root)} - run import or update first")
    out = []
    for fp in files:
        sym = fp.name[: -len(f"_{BAR_MIN}m.parquet")]
        dp, _ = _paths(root, sym)
        daily = pd.read_parquet(dp, columns=["timestamp", "open", "high", "low", "close", "volume"]) if Path(dp).exists() else pd.DataFrame()
        J = reconcile_symbol(pd.read_parquet(fp), daily, DECL["reconcile_price_tol"], DECL["reconcile_volume_tol"])
        if len(J):
            out.append(J.assign(symbol=sym))
    Q = pd.concat(out, ignore_index=True) if out else pd.DataFrame()
    if len(Q):
        Q.to_csv(store(root) / "intraday_quality.csv", index=False)
        _log(f"check: {Q['symbol'].nunique():,} stocks, {len(Q):,} stock-days - reconcile OK {Q['ok'].mean():.1%}, "
             f"full {DECL['bars_per_session']}-bar sessions {Q['full_session'].mean():.1%}, split-basis mismatches {int(Q['basis_mismatch'].sum()):,}; "
             f"report: {store(root) / 'intraday_quality.csv'}")
    return Q


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="3-minute bars for the frozen engines' picks")
    ap.add_argument("cmd", choices=["import", "update", "check"])
    ap.add_argument("--root", required=True)
    ap.add_argument("--src", default=None, help="import: a folder or a file of 3-minute data")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--start", default="2021-10-01", help="update: earliest date to fetch for a stock with no file")
    ap.add_argument("--symbols-file", default=None, help="update: a symbol list instead of every picked stock")
    a = ap.parse_args(argv)
    root = Path(a.root)
    if a.cmd == "import":
        if not a.src:
            raise PreconditionError("import needs --src")
        R = cmd_import(root, Path(a.src), a.dry_run)
        bad = R[R["error"] != ""]
        for _, r in bad.head(10).iterrows():
            print(f"   {r['file']}: {r['error']}")
        return 0
    if a.cmd == "update":
        syms = RC.load_symbol_list(Path(a.symbols_file)) if a.symbols_file else picked_symbols(root)
        R = cmd_update(root, sorted(syms), dt.date.fromisoformat(a.start))
        for _, r in R[R["error"] != ""].head(10).iterrows():
            print(f"   {r['symbol']}: {r['error']}")
        return 0
    cmd_check(root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
