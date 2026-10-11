# BIGMOVE v1 - intraday breakout study

bigmove_study v1.1 | declaration 1d330078e15751b7 | 2026-10-11 14:36 | cash-intraday costs 4.49 bp a round trip at Rs 500,000 plus slippage (entry 5 bp, stop 5 bp, time 3 bp)

Days: discovery 796, confirmation 392, after the closing auction 48 (3-minute data 2021-10-01 to 2026-10-09; books from 2021-10-18). Liquid stock-days with a 3-minute session: 99.3% of 438,100; usable after reconciliation and the 80% rule: 97.3%.

Data checks (they look at the whole session: hygiene, not signal): of 1,072,795 stock sessions with bars, 30,838 (2.87%) failed reconciliation with the daily bar and 4,123 (0.38%) had no first bar or under 80% of bars; both are dropped. Unreadable 3-minute files: 0. Triggered trades without a valid exit price: 0 (they would otherwise vanish as 'no trade'; expected 0). If any of these is large, read the results with care.

Usable share of liquid stock-days by month (universe_by_month.csv): lowest 54.2% (2026-10); months under 90%: 2025-02, 2026-08, 2026-09, 2026-10 - results in those months rest on a thinner universe.

Candidates dropped from every book for lack of a memory score (a stock's first months after listing, declared): 1-bar range 1,458 of 127,489 (1.14%); 2-bar range 1,505 of 127,399 (1.18%).

## Verdicts (discovery selects; confirmation used once)

Daily return of the book in bp of its capital per day, [95% block-bootstrap interval]; Sharpe annualised; DSR = deflated Sharpe over 84 trials; FDR = passes Benjamini-Hochberg q 0.1 within its side. 'Excess' = minus PLAIN with the same capital in use (every candidate, min(count, N)/N of the book), paired by day: a ranked cell must beat it to be PROMISING or CHAMPION. 'p (search)' judges that excess against the search: how often the BEST of the side's 36 ranked cells shows as much excess when no ranking has any (max-t); a ranked cell also needs it below 0.025.

| side | pick | score | range bars | top N | stop | discovery bp/day | Sharpe | DSR | FDR | x1.5 slip | excess | p (search) | confirmation bp/day | Sharpe | x1.5 slip | excess | after CAS bp/day | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L | best | rvxmfe | 1 | 10 | a50 | -12.3 [-19.1, -5.6] | -1.85 | +0.00 | no | -15.7 | -0.1 [-4.5, +4.3] | 0.987 | -12.4 [-19.7, -4.8] | -2.17 | -15.7 | -1.2 | -26.7 | **DEAD** |
| L | best rv | rv | 1 | 10 | range | -13.4 [-18.9, -8.4] | -2.50 | +0.00 | no | -16.9 | -2.6 [-6.5, +1.0] | 1.000 | -11.4 [-18.6, -4.0] | -2.33 | -14.7 | -0.9 | -13.0 | **DEAD** |
| L | median rv | rv | 2 | 10 | a50 | -16.2 [-21.2, -11.3] | -3.58 | +0.00 | no | -19.5 | -2.7 [-6.3, +1.0] | 1.000 | -11.7 [-18.6, -4.7] | -2.61 | -14.9 | -0.1 | +0.7 | **(reported)** |
| L | best mfe | mfe | 1 | 10 | a50 | -16.8 [-23.8, -9.7] | -2.38 | +0.00 | no | -20.3 | -4.6 [-9.5, +0.3] | 1.000 | -18.7 [-27.6, -9.2] | -3.01 | -22.0 | -7.5 | -25.4 | **DEAD** |
| L | median mfe | mfe | 2 | 20 | range | -14.0 [-18.6, -9.3] | -2.95 | +0.00 | no | -17.3 | -2.1 [-4.4, +0.2] | 1.000 | -14.9 [-21.2, -8.8] | -3.15 | -18.1 | -3.6 | -5.0 | **(reported)** |
| L | best rvxmfe | rvxmfe | 1 | 10 | a50 | -12.3 [-19.1, -5.6] | -1.85 | +0.00 | no | -15.7 | -0.1 [-4.5, +4.3] | 0.987 | -12.4 [-19.7, -4.8] | -2.17 | -15.7 | -1.2 | -26.7 | **DEAD** |
| L | median rvxmfe | rvxmfe | 2 | 10 | a50 | -17.7 [-23.2, -12.2] | -3.11 | +0.00 | no | -20.9 | -4.2 [-8.0, -0.6] | 1.000 | -13.7 [-21.0, -6.6] | -2.56 | -16.9 | -2.1 | -13.3 | **(reported)** |
| L | best plain | plain | 1 | all | range | -10.8 [-14.3, -7.5] | -3.11 | +0.00 | no | -14.4 | (is plain) | - | -7.8 [-14.1, +0.4] | -1.57 | -11.3 | (is plain) | -16.7 | **DEAD** |
| L | median plain | plain | 2 | all | a50 | -13.5 [-17.0, -10.2] | -4.00 | +0.00 | no | -16.9 | (is plain) | - | -11.4 [-15.6, -6.9] | -3.38 | -14.7 | (is plain) | -11.2 | **(reported)** |
| S | best | rv | 1 | 10 | a50 | +2.7 [-2.6, +7.9] | +0.53 | +0.00 | no | -0.9 | +4.3 [+0.9, +7.6] | 0.090 | -2.4 [-8.8, +4.1] | -0.58 | -5.8 | +3.8 | -6.7 | **WATCH** |
| S | best rv | rv | 1 | 10 | a50 | +2.7 [-2.6, +7.9] | +0.53 | +0.00 | no | -0.9 | +4.3 [+0.9, +7.6] | 0.090 | -2.4 [-8.8, +4.1] | -0.58 | -5.8 | +3.8 | -6.7 | **WATCH** |
| S | median rv | rv | 1 | 20 | a50 | -0.3 [-4.4, +4.0] | -0.08 | +0.00 | no | -3.9 | +1.3 [-0.6, +3.1] | 0.592 | -5.4 [-11.0, +0.1] | -1.47 | -8.8 | +0.8 | -7.4 | **(reported)** |
| S | best mfe | mfe | 2 | 10 | range | +0.7 [-6.4, +8.0] | +0.10 | +0.00 | no | -2.8 | +1.5 [-2.5, +5.5] | 0.872 | -1.1 [-8.9, +6.6] | -0.19 | -4.4 | +4.7 | -18.1 | **WATCH** |
| S | median mfe | mfe | 1 | 20 | range | -1.2 [-6.6, +4.4] | -0.21 | +0.00 | no | -4.9 | +0.6 [-1.6, +2.7] | 0.925 | -5.7 [-12.1, +0.5] | -1.22 | -9.2 | +0.2 | -12.2 | **(reported)** |
| S | best rvxmfe | rvxmfe | 1 | 10 | a50 | +1.6 [-4.0, +7.6] | +0.27 | +0.00 | no | -2.0 | +3.3 [+0.2, +6.1] | 0.203 | -1.2 [-9.1, +7.0] | -0.22 | -4.6 | +5.0 | -17.1 | **WATCH** |
| S | median rvxmfe | rvxmfe | 1 | 20 | range | +0.4 [-4.9, +5.7] | +0.07 | +0.00 | no | -3.3 | +2.1 [+0.4, +4.0] | 0.164 | -2.6 [-9.3, +4.1] | -0.60 | -6.1 | +3.3 | -11.4 | **(reported)** |
| S | best plain | plain | 2 | all | range | -0.8 [-5.4, +3.6] | -0.18 | +0.00 | no | -4.3 | (is plain) | - | -5.7 [-10.0, -1.6] | -1.69 | -9.1 | (is plain) | -9.2 | **DEAD** |
| S | median plain | plain | 1 | all | range | -1.8 [-6.0, +2.5] | -0.42 | +0.00 | no | -5.5 | (is plain) | - | -5.9 [-10.8, -1.3] | -1.72 | -9.4 | (is plain) | -11.1 | **(reported)** |

'best' = the highest discovery Sharpe among cells that meet the discovery half of their own rule (lower bound > 0; a ranked cell's excess too: lower bound > 0 and p (search) below 0.025); it is the cell the gates, exits, combined book and regimes use (L none met the discovery rule: highest Sharpe; S none met the discovery rule: highest Sharpe).

White's Reality Check (the best of the 42 F1 cells per side vs zero, discovery): L p = +1.000, S p = +0.452.

Fill audit of the selected cells (discovery): trades stopped inside their entry bar (booked at the worst order: entry, then the full stop) and trades with a missing bar between entry and exit (a hidden bar could hide a stop):

| side | pick | stopped in the entry bar | missing bar inside the trade |
|---|---|---|---|
| L | best | 1.2% | 0.10% |
| L | best rv | 1.8% | 0.05% |
| L | best mfe | 0.7% | 0.11% |
| L | best rvxmfe | 1.2% | 0.10% |
| L | best plain | 2.1% | 0.06% |
| S | best | 2.1% | 0.20% |
| S | best rv | 2.1% | 0.20% |
| S | best mfe | 0.7% | 0.14% |
| S | best rvxmfe | 1.2% | 0.18% |
| S | best plain | 0.6% | 0.14% |

Is the memory more than volatility? Each memory pick minus the ATR control with the same range, N and stop, paired by day (reported; not a verdict rule):

| side | pick | discovery | confirmation | after CAS |
|---|---|---|---|---|
| L | best | +3.5 [-1.1, +8.1] | +5.9 [-1.2, +12.8] | -0.6 |
| L | best mfe | -0.9 [-4.2, +2.3] | -0.4 [-4.7, +4.0] | +0.7 |
| L | best rvxmfe | +3.5 [-1.1, +8.1] | +5.9 [-1.2, +12.8] | -0.6 |
| S | best mfe | -0.0 [-2.4, +2.4] | +1.4 [-2.5, +5.4] | -1.1 |
| S | best rvxmfe | +1.3 [-2.5, +5.3] | +0.7 [-6.7, +7.9] | +8.3 |

Combined book (half the capital in each side's selected cell: L rvxmfe|1|10|a50, S rv|1|10|a50; reported, no verdict): discovery -4.8 [-8.3, -1.0] bp/day, Sharpe -1.36, drawdown -41.91%; confirmation -7.4 [-11.7, -3.0], Sharpe -2.38; after CAS -16.7.

Days on which a side had fewer than N candidates (part of an N-slot book sits in cash; the excess benchmark holds the same cash, so this is not counted as skill):

| side | range bars | top N | discovery | confirmation | after CAS |
|---|---|---|---|---|---|
| L | 1 | 10 | 9 of 796 | 3 of 392 | 2 of 48 |
| L | 1 | 20 | 54 of 796 | 10 of 392 | 3 of 48 |
| S | 1 | 10 | 8 of 796 | 2 of 392 | 2 of 48 |
| S | 1 | 20 | 39 of 796 | 11 of 392 | 5 of 48 |
| L | 2 | 10 | 9 of 796 | 2 of 392 | 2 of 48 |
| L | 2 | 20 | 42 of 796 | 9 of 392 | 3 of 48 |
| S | 2 | 10 | 6 of 796 | 4 of 392 | 2 of 48 |
| S | 2 | 20 | 42 of 796 | 15 of 392 | 4 of 48 |

## RV x MFE: does the memory add to opening volume (and the reverse)?

Paired daily difference in bp of book capital, pooled over the 12 (range, N, stop) combinations.

| side | RVxMFE minus | discovery | confirmation | after CAS | adds |
|---|---|---|---|---|---|
| L | rv | -0.3 [-2.4, +1.9] | -0.4 [-3.7, +2.7] | -6.1 | no |
| L | mfe | +0.4 [-1.8, +2.4] | +3.1 [-0.0, +6.2] | -0.0 | no |
| S | rv | +0.0 [-1.8, +1.8] | +1.7 [-1.1, +4.6] | -5.9 | no |
| S | mfe | +1.0 [-0.9, +2.8] | -0.5 [-3.4, +2.5] | +2.6 | no |

## Direction gates (F2) and path management (F3), on each side's selected cell

'adds' = paired discovery lower bound > 0 and paired confirmation mean > 0; a gate can only add to a cell that makes money in discovery (on a losing cell, trading less always looks better). A gate that cannot judge a stock-day (no NIFTY bars, no sector or liquid peer, no beta) lets it through; 'judged' is the share of the cell's discovery picks it could judge. A variant of a ranked cell must also beat the same variant on the matched PLAIN book ('excess'), and its base cell's ranking must survive the search (the base's p (search) above).

| side | variant | judged | discovery bp/day | vs base (paired) | excess | confirmation bp/day | vs base | FDR | verdict | adds |
|---|---|---|---|---|---|---|---|---|---|---|
| L | g_nifty | 100% | -10.2 [-15.0, -5.5] | +2.1 [-1.9, +6.1] | -0.7 [-4.0, +2.7] | -9.5 [-15.6, -3.7] | +2.9 [-1.5, +7.3] | no | DEAD | no |
| L | g_sector | 0% | -12.3 [-19.1, -5.6] | +0.0 [+0.0, +0.0] | -0.1 [-4.5, +4.3] | -12.4 [-19.7, -4.8] | +0.0 [+0.0, +0.0] | no | NOT RUN (no data for this gate) | no |
| L | g_rs | 100% | -12.6 [-19.2, -6.0] | -0.3 [-0.6, +0.1] | -0.2 [-4.5, +4.3] | -12.9 [-20.3, -5.4] | -0.6 [-1.3, +0.1] | no | DEAD | no |
| L | g_nifty_rs | 100% | -10.2 [-14.8, -5.6] | +2.1 [-1.9, +6.2] | -0.5 [-3.7, +2.8] | -10.1 [-16.1, -4.4] | +2.3 [-2.2, +6.8] | no | DEAD | no |
| L | x_vwap | - | -3.1 [-7.2, +0.8] | +9.2 [+4.8, +13.5] | +1.2 [-1.5, +3.8] | -5.4 [-10.8, -0.2] | +7.0 [+1.5, +12.6] | YES | DEAD | YES |
| L | x_be | - | -10.6 [-17.0, -4.4] | +1.7 [+0.2, +3.1] | +0.9 [-3.2, +5.1] | -12.0 [-19.7, -4.8] | +0.4 [-1.6, +2.4] | YES | DEAD | YES |
| S | g_nifty | 100% | -1.0 [-5.4, +3.5] | -3.7 [-6.2, -1.2] | +1.8 [-0.9, +4.4] | -2.7 [-8.0, +2.5] | -0.3 [-4.4, +3.6] | no | DEAD | no |
| S | g_sector | 0% | +2.7 [-2.6, +7.9] | +0.0 [+0.0, +0.0] | +4.3 [+0.9, +7.6] | -2.4 [-8.8, +4.1] | +0.0 [+0.0, +0.0] | no | NOT RUN (no data for this gate) | no |
| S | g_rs | 100% | +2.9 [-2.5, +8.2] | +0.2 [-0.1, +0.7] | +4.4 [+1.0, +7.6] | -1.3 [-7.6, +5.2] | +1.1 [+0.1, +2.4] | no | WATCH | no |
| S | g_nifty_rs | 100% | -0.9 [-5.4, +3.6] | -3.6 [-6.0, -1.1] | +1.8 [-0.9, +4.3] | -2.9 [-8.1, +2.2] | -0.5 [-4.8, +3.6] | no | DEAD | no |
| S | x_vwap | - | -1.6 [-5.7, +2.5] | -4.3 [-7.3, -1.2] | +4.7 [+1.9, +7.3] | -3.4 [-8.2, +1.5] | -1.0 [-5.1, +3.4] | no | DEAD | no |
| S | x_be | - | +3.0 [-2.1, +8.3] | +0.4 [-0.5, +1.3] | +5.2 [+1.7, +8.4] | -2.6 [-8.5, +3.2] | -0.2 [-2.0, +1.5] | no | WATCH | no |

White's Reality Check on the best improvement over the base cell, within each family and side: F2 L p = +0.249, F3 L p = +0.000, F2 S p = +0.249, F3 S p = +0.358. FDR here is on the paired improvement.

## NIFTY noise-boundary sleeve (F4, futures costs, spot index as stand-in)

| cell | discovery bp/day | Sharpe | trades | per trade bp | FDR | confirmation bp/day | Sharpe | after CAS | verdict |
|---|---|---|---|---|---|---|---|---|---|
| time|all | +0.2 [-2.5, +3.0] | +0.06 | 418 | +0.3 | no | -4.5 [-8.3, -1.1] | -1.91 | -3.1 | (reported) |
| time|nr47 | +0.5 [-0.9, +1.9] | +0.43 | 105 | +4.1 | no | -1.0 [-3.3, +1.1] | -0.70 | -0.9 | WATCH |
| time|highvol | -0.4 [-2.7, +2.1] | -0.17 | 200 | -1.4 | no | -3.4 [-6.9, -0.5] | -1.70 | +0.4 | (reported) |
| trail|all | -0.5 [-2.4, +1.6] | -0.24 | 418 | -1.0 | no | -3.2 [-5.5, -1.0] | -1.99 | -2.9 | (reported) |
| trail|nr47 | +0.3 [-0.6, +1.4] | +0.34 | 105 | +2.6 | no | -0.7 [-2.1, +0.8] | -0.71 | -0.6 | (reported) |
| trail|highvol | -0.5 [-2.1, +1.3] | -0.29 | 200 | -1.9 | no | -2.0 [-4.0, -0.2] | -1.46 | +0.1 | (reported) |

White's Reality Check over the 6 sleeve cells: p = +0.472.

## Controls (never selected): is the ranking worth anything?

A random ranking must show no excess over the matched PLAIN book (if it does, the benchmark is broken); ATR alone asks whether the memory is more than volatility.

| side | control | range bars | top N | stop | discovery bp/day | excess | per trade bp | confirmation bp/day |
|---|---|---|---|---|---|---|---|---|
| L | random | 1 | 10 | range | -13.1 [-18.1, -8.2] | -2.3 [-5.3, +0.8] | -16.2 | -11.0 |
| L | random | 1 | 10 | a25 | -14.4 [-18.3, -10.3] | -1.7 [-4.1, +0.9] | -17.8 | -11.5 |
| L | random | 1 | 10 | a50 | -14.1 [-19.3, -8.8] | -1.9 [-5.1, +1.4] | -17.4 | -12.3 |
| L | random | 1 | 20 | range | -12.0 [-15.8, -8.2] | -1.3 [-2.8, +0.2] | -15.1 | -10.7 |
| L | random | 1 | 20 | a25 | -13.9 [-17.1, -10.7] | -1.4 [-2.9, +0.0] | -17.5 | -12.1 |
| L | random | 1 | 20 | a50 | -13.2 [-17.4, -9.2] | -1.3 [-2.9, +0.2] | -16.7 | -12.1 |
| L | atr | 1 | 10 | range | -15.6 [-22.3, -9.3] | -4.8 [-9.5, -0.3] | -19.7 | -16.3 |
| L | atr | 1 | 10 | a25 | -13.5 [-18.8, -8.3] | -0.8 [-4.2, +2.7] | -17.1 | -16.8 |
| L | atr | 1 | 10 | a50 | -15.8 [-22.6, -9.1] | -3.7 [-8.3, +0.8] | -20.0 | -18.2 |
| L | atr | 1 | 20 | range | -13.5 [-18.5, -8.7] | -2.8 [-5.3, -0.4] | -17.2 | -14.1 |
| L | atr | 1 | 20 | a25 | -14.3 [-18.2, -10.3] | -1.9 [-3.6, +0.1] | -18.2 | -13.3 |
| L | atr | 1 | 20 | a50 | -15.0 [-20.1, -10.1] | -3.1 [-5.4, -0.7] | -19.1 | -15.2 |
| S | random | 1 | 10 | range | -2.9 [-7.5, +1.8] | -1.1 [-3.7, +1.6] | -3.5 | -5.9 |
| S | random | 1 | 10 | a25 | -5.6 [-9.6, -1.2] | -0.4 [-2.6, +1.8] | -6.7 | -6.5 |
| S | random | 1 | 10 | a50 | -2.1 [-7.2, +3.2] | -0.4 [-3.2, +2.4] | -2.5 | -5.9 |
| S | random | 1 | 20 | range | -2.2 [-6.3, +2.0] | -0.4 [-1.8, +1.0] | -2.7 | -6.1 |
| S | random | 1 | 20 | a25 | -5.2 [-8.6, -1.5] | -0.0 [-1.2, +1.1] | -6.3 | -7.1 |
| S | random | 1 | 20 | a50 | -1.8 [-6.1, +2.6] | -0.2 [-1.7, +1.4] | -2.2 | -6.1 |
| S | atr | 1 | 10 | range | -1.1 [-7.9, +6.0] | +0.8 [-3.2, +4.6] | -1.3 | -2.4 |
| S | atr | 1 | 10 | a25 | -4.2 [-9.9, +1.8] | +1.0 [-2.6, +4.4] | -5.0 | -3.5 |
| S | atr | 1 | 10 | a50 | +0.3 [-6.9, +7.5] | +1.9 [-2.1, +6.0] | +0.3 | -1.9 |
| S | atr | 1 | 20 | range | -1.3 [-6.7, +4.3] | +0.5 [-1.7, +2.7] | -1.6 | -4.7 |
| S | atr | 1 | 20 | a25 | -4.6 [-9.0, +0.1] | +0.6 [-1.3, +2.4] | -5.5 | -4.1 |
| S | atr | 1 | 20 | a50 | -0.6 [-6.1, +5.3] | +1.0 [-1.2, +3.3] | -0.7 | -4.5 |
| L | random | 2 | 10 | range | -12.1 [-17.3, -6.8] | +0.2 [-3.0, +3.4] | -15.7 | -10.7 |
| L | random | 2 | 10 | a25 | -12.5 [-16.3, -8.6] | +0.4 [-2.2, +3.0] | -16.2 | -11.2 |
| L | random | 2 | 10 | a50 | -12.9 [-17.8, -8.0] | +0.6 [-2.5, +3.8] | -16.8 | -11.5 |
| L | random | 2 | 20 | range | -12.4 [-16.3, -8.4] | -0.4 [-2.1, +1.2] | -16.2 | -12.4 |
| L | random | 2 | 20 | a25 | -12.7 [-15.7, -9.7] | -0.1 [-1.7, +1.4] | -16.7 | -12.8 |
| L | random | 2 | 20 | a50 | -13.2 [-17.1, -9.3] | -0.0 [-1.7, +1.7] | -17.3 | -13.1 |
| L | atr | 2 | 10 | range | -18.6 [-25.1, -12.4] | -6.3 [-10.7, -2.0] | -24.8 | -19.8 |
| L | atr | 2 | 10 | a25 | -15.2 [-20.2, -10.0] | -2.3 [-5.6, +1.1] | -20.2 | -16.5 |
| L | atr | 2 | 10 | a50 | -19.8 [-26.6, -13.4] | -6.3 [-10.7, -1.8] | -26.4 | -20.0 |
| L | atr | 2 | 20 | range | -14.4 [-19.1, -9.9] | -2.5 [-4.7, -0.3] | -19.3 | -15.6 |
| L | atr | 2 | 20 | a25 | -14.1 [-17.6, -10.5] | -1.5 [-3.2, +0.3] | -18.9 | -13.8 |
| L | atr | 2 | 20 | a50 | -15.4 [-20.1, -10.8] | -2.2 [-4.4, +0.1] | -20.6 | -15.7 |
| S | random | 2 | 10 | range | -1.2 [-6.4, +3.8] | -0.4 [-2.9, +2.1] | -1.5 | -9.8 |
| S | random | 2 | 10 | a25 | -4.4 [-8.4, -0.2] | +0.2 [-2.0, +2.3] | -5.5 | -9.4 |
| S | random | 2 | 10 | a50 | -1.0 [-6.0, +4.0] | +0.0 [-2.4, +2.5] | -1.2 | -10.2 |
| S | random | 2 | 20 | range | -1.7 [-6.1, +2.6] | -0.9 [-2.1, +0.4] | -2.1 | -5.9 |
| S | random | 2 | 20 | a25 | -4.4 [-7.9, -0.7] | +0.1 [-1.0, +1.4] | -5.5 | -6.2 |
| S | random | 2 | 20 | a50 | -1.2 [-5.6, +3.1] | -0.2 [-1.5, +1.1] | -1.6 | -6.1 |
| S | atr | 2 | 10 | range | +0.7 [-6.2, +8.3] | +1.5 [-2.2, +5.6] | +0.9 | -2.5 |
| S | atr | 2 | 10 | a25 | -3.2 [-9.0, +3.0] | +1.3 [-2.0, +5.0] | -4.0 | -4.4 |
| S | atr | 2 | 10 | a50 | -0.1 [-7.1, +7.1] | +0.9 [-2.9, +4.8] | -0.1 | -3.8 |
| S | atr | 2 | 20 | range | -0.8 [-6.4, +5.0] | -0.0 [-2.2, +2.1] | -1.0 | -6.1 |
| S | atr | 2 | 20 | a25 | -5.3 [-9.7, -0.6] | -0.7 [-2.4, +0.9] | -6.6 | -6.3 |
| S | atr | 2 | 20 | a50 | -0.9 [-6.5, +4.7] | +0.1 [-2.0, +2.1] | -1.1 | -7.3 |

## Regimes (bp/day between the declared dates; reported, never used for selection)

| from | to | days | best L | best S | combined | NIFTY sleeve |
|---|---|---|---|---|---|---|
| 2021-10-18 | 2024-11-19 | 768 | -12.2 | +3.4 | -4.4 | +0.3 |
| 2024-11-20 | 2025-07-02 | 153 | -18.3 | -9.3 | -13.8 | +1.3 |
| 2025-07-03 | 2025-08-29 | 40 | -16.9 | +10.3 | -3.3 | -2.8 |
| 2025-09-01 | 2026-03-30 | 144 | -14.2 | -0.3 | -7.2 | +0.2 |
| 2026-04-01 | 2026-07-31 | 83 | +3.1 | -5.0 | -1.0 | -3.9 |
| 2026-08-03 | 2026-09-04 | 25 | -26.9 | -14.4 | -20.6 | -2.5 |
| 2026-09-07 | 2026-10-09 | 23 | -26.5 | +1.6 | -12.4 | +0.8 |

## Limits (from the declaration)

- the published evidence for this strategy is from the US (Zarattini, Barbon and Aziz 2024: Sharpe 2.81 with no clean out-of-sample period); no published after-cost NSE result exists
- slippage is assumed, not measured; the edge sits in the highest-volume opening moves, where impact is largest
- historical MIS eligibility, short availability, F&O ban lists and price-band halts are not in the data
- 3-minute coverage was fetched for stocks the D / ENS engines ever ranked in their top 10; liquid stocks never ranked are missing unless fetched (coverage rule)
- the NIFTY sleeve trades the spot index as a stand-in for futures
- the closing-auction regime (from 3 Aug 2026) and the revised pre-open (from 7 Sep 2026) change the open and the close; only about two months of data exist for them
- two data checks look at the whole session (reconciliation with the daily bar; at least 80% of bars present): they remove broken downloads but would also remove a session halted for most of the day; the report counts both
- sector membership comes from today's index lists: stocks that have left the indices have no sector (the sector gate lets them through) and the peer averages are made of today's members
- the design drew on earlier studies (Soul, intraday Soul) whose data overlap the confirmation window: the confirmation is clean of BIGMOVE's own results only
- PROMISING is the best of 42 cells per side and its daily mean has no multiplicity control (the FDR flag is shown beside it; a ranked cell's lead over buying everything does, amendment q); only a forward paper test can confirm it
- the bootstrap statistics are somewhat optimistic: in the test suite's simulations the 95% interval held the true mean in 93.0% of autocorrelated fat-tailed series and the Reality Check flagged 9.0% of no-edge sets at p < 0.05; read borderline p-values with that in mind

Every cell with all statistics is in cells.csv; daily book returns in daily_returns.parquet; trades of the selected cells in trades_selected.parquet; gates.csv, exits.csv, comparison.csv, nifty_sleeve.csv, thin_days.csv, regimes.csv.
