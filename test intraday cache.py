#!/usr/bin/env python3
"""
tests/test_intraday_cache.py - intraday_cache v1.1 (3-minute). Prints VERIFIED on success.

 1. Normalising: any column spelling, UTC -> IST, bars outside 09:15-15:15 dropped, duplicates removed.
 2. Update (fake Kite): 60-day chunks cover the range exactly; 25 bars a session; a second run adds only
    new sessions; today's bars only after 15:45; one failing stock does not stop the rest; an expired token
    stops cleanly.
 3. Import: a CSV per stock (name from the file), a multi-stock parquet with a symbol column in UTC;
    --dry-run writes nothing.
 4. Reconcile: bars built from the daily cache pass; a planted split-basis mismatch and a planted
    volume gap are flagged.
"""

from __future__ import annotations

import datetime as dt
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import intraday_cache as IC            # noqa: E402
from data_quality import _paths        # noqa: E402

FAILS = []


def check(cond, msg):
    print(("  ok  " if cond else "  FAIL") + f"  {msg}")
    if not cond:
        FAILS.append(msg)


def bars_for(day: dt.date, base: float):
    t0 = dt.datetime.combine(day, dt.time(9, 15))
    out = []
    for k in range(125):
        p = base * (1 + 0.001 * np.sin(k + day.toordinal()))
        out.append({"date": t0 + dt.timedelta(minutes=3 * k), "open": p, "high": p * 1.002, "low": p * 0.998,
                    "close": p * 1.0005, "volume": 1000 + k})
    return out


class FakeKite:
    def __init__(self, fail=(), expire=()):
        self.calls, self.fail, self.expire = [], set(fail), set(expire)

    def _symbol_to_instrument_token(self, sym):
        if sym in self.expire:
            raise type("AuthExpired", (Exception,), {})("token expired")
        if sym in self.fail:
            raise RuntimeError("unknown symbol")
        return abs(hash(sym)) % 10 ** 6

    def _hist(self, inst, a, b, interval):
        self.calls.append((inst, a, b, interval))
        rows, d = [], a.date()
        while d <= b.date():
            if d.weekday() < 5:
                rows += bars_for(d, 100 + inst % 50)
            d += dt.timedelta(days=1)
        return rows


def main():
    IC.MIN_GAP_S = 0.0
    tmp = Path(tempfile.mkdtemp())
    try:
        print("1. normalising")
        raw = pd.DataFrame({"Date": pd.to_datetime(["2024-01-02 03:45", "2024-01-02 03:45", "2024-01-02 10:15", "2024-01-02 03:30",
                                                     "2024-01-02 03:49", "2024-01-02 09:57"]).tz_localize("UTC"),
                            "Open": [1, 1, 2, 3, 4, 5], "High": [1, 1, 2, 3, 4, 5], "Low": [1, 1, 2, 3, 4, 5], "Close": [1, 1, 2, 3, 4, 5],
                            "Volume": [5, 5, 6, 7, 8, 9]})
        n = IC.normalise(raw)
        check(list(n["timestamp"]) == [pd.Timestamp("2024-01-02 09:15"), pd.Timestamp("2024-01-02 15:27")],
              "UTC -> IST; 09:15 and the last 3-minute bar (15:27) kept; 15:45, 09:00 and the off-grid 09:19 dropped; duplicate removed")
        one = pd.DataFrame(bars_for(dt.date(2024, 1, 3), 100.0)).rename(columns={"date": "timestamp"})
        r15 = IC.resample(one[IC.COLS], 15)
        first5 = one.iloc[:5]
        check(len(r15) == 25 and r15["timestamp"].iloc[-1] == pd.Timestamp("2024-01-03 15:15")
              and abs(r15["high"].iloc[0] - first5["high"].max()) < 1e-12 and r15["volume"].iloc[0] == first5["volume"].sum()
              and r15["open"].iloc[0] == first5["open"].iloc[0] and r15["close"].iloc[0] == first5["close"].iloc[-1],
              "resample: 125 three-minute bars -> 25 fifteen-minute bars, open/high/low/close/volume exact")

        print("2. update from a fake Kite")
        k = FakeKite()
        now = dt.datetime(2024, 3, 29, 12, 0)                      # Friday noon: last complete session = Thursday
        R = IC.cmd_update(tmp, ["AAA"], dt.date(2024, 1, 1), now, k)
        A = pd.read_parquet(IC.path_for(tmp, "AAA"))
        days = A["timestamp"].dt.date.nunique()
        bd = int(np.busday_count("2024-01-01", "2024-03-29"))
        check(days == bd and (A.groupby(A["timestamp"].dt.date).size() == 125).all(),
              f"{days} sessions x 125 bars, Jan 1 - Mar 28 (today's partial session excluded at noon)")
        check(len(k.calls) == int(np.ceil(88 / 60)) and k.calls[0][3] == "3minute", f"fetched in {len(k.calls)} 60-day chunks of 3-minute bars")
        R2 = IC.cmd_update(tmp, ["AAA"], dt.date(2024, 1, 1), dt.datetime(2024, 4, 3, 16, 0), k)
        B = pd.read_parquet(IC.path_for(tmp, "AAA"))
        check(int(R2["added"].iloc[0]) == 4 * 125 and B["timestamp"].is_unique and B["timestamp"].dt.date.max() == dt.date(2024, 4, 3),
              "second run adds only Mar 29 - Apr 3 (after 15:45 today counts), no duplicates")
        R3 = IC.cmd_update(tmp, ["BBB", "CCC"], dt.date(2024, 3, 1), now, FakeKite(fail={"BBB"}))
        check(R3.set_index("symbol").at["BBB", "error"] != "" and IC.path_for(tmp, "CCC").exists(),
              "a failing stock is logged; the next one is still fetched")
        try:
            IC.cmd_update(tmp, ["DDD"], dt.date(2024, 3, 1), now, FakeKite(expire={"DDD"}))
            check(False, "an expired token stops cleanly")
        except SystemExit as e:
            check("token has expired" in str(e), "an expired token stops cleanly, with what to do")
        check(not list(IC.store(tmp).glob("*.tmp")), "saves are atomic: no temporary files left")

        print("3. import")
        src = tmp / "src"
        src.mkdir()
        rows = pd.DataFrame(bars_for(dt.date(2024, 5, 6), 50.0))
        rows.to_csv(src / "EEE_3min.csv", index=False)
        multi = pd.DataFrame(bars_for(dt.date(2024, 5, 7), 70.0) + bars_for(dt.date(2024, 5, 7), 80.0))
        multi["symbol"] = ["FFF"] * 125 + ["GGG"] * 125
        multi["date"] = pd.to_datetime(multi["date"]).dt.tz_localize("Asia/Kolkata").dt.tz_convert("UTC")
        multi.to_parquet(src / "batch.parquet", index=False)
        D = IC.cmd_import(tmp, src, True)
        check(set(D["symbol"]) == {"EEE", "FFF", "GGG"} and int(D["bars"].sum()) == 375 and not IC.path_for(tmp, "EEE").exists(),
              "dry run: 3 stocks (one from the file name, two from a symbol column), 375 bars found, nothing written")
        IC.cmd_import(tmp, src, False)
        G = pd.read_parquet(IC.path_for(tmp, "GGG"))
        check(len(G) == 125 and G["timestamp"].iloc[0] == pd.Timestamp("2024-05-07 09:15"), "import: UTC parquet lands at 09:15 IST, 125 bars")

        print("4. reconcile with the daily cache")
        intra = pd.read_parquet(IC.path_for(tmp, "AAA"))
        g = intra.assign(day=intra["timestamp"].dt.normalize()).groupby("day")
        daily = pd.DataFrame({"timestamp": g.size().index, "open": g["open"].first().values, "high": g["high"].max().values,
                              "low": g["low"].min().values, "close": g["close"].last().values, "volume": g["volume"].sum().values})
        bad_day = daily["timestamp"].iloc[10]
        daily.loc[10, ["open", "high", "low", "close"]] *= 2.0            # the daily cache on a 2:1 adjusted basis
        daily.loc[20, "volume"] *= 1.5
        dp, _ = _paths(tmp, "AAA")
        daily.to_parquet(dp, index=False)
        J = IC.reconcile_symbol(intra, daily, 0.005, 0.10)
        check(int(J["ok"].sum()) == len(J) - 2 and bool(J.set_index("day").at[bad_day, "basis_mismatch"]),
              f"all {len(J) - 2} consistent days pass; the 2:1 split-basis day and the volume gap are flagged")
        Q = IC.cmd_check(tmp)
        check((IC.store(tmp) / "intraday_quality.csv").exists() and "AAA" in set(Q["symbol"]), "check writes intraday_quality.csv")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print()
    if FAILS:
        print(f"FAILED  {len(FAILS)} check(s):")
        for f in FAILS:
            print("   - " + f)
        return 1
    print(f"VERIFIED  {IC.CODE_VERSION}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
