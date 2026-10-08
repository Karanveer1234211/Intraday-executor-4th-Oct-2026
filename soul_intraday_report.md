# Soul + intraday Soul

soul_intraday_study v1.1 | declaration 1c2ada8d487d68b3 | candidates 90f221ed218476e8 | exploration mode

**How to read this.** Every pick is bought at the next open; the baseline sells at the 5th close (honest circuit exits, 35 bp). bp = basis points per trade (100 bp = 1%). Intervals are 95%.

**Sections 1-7 are EXPLORATORY**: descriptions, correlations, hit rates and rankings, with no false-discovery control. Nothing in them is validated. Section 8 lists PROMISING rules (discovery lower bound above zero AND confirmation mean above zero, D only): candidates for a forward shadow lane - still not validated; only the forward test decides.

**Timing.** Every state is day T's completed state (its close and its 3-minute bars). Every memory is chosen on that state and reports what FOLLOWED the similar moments - the next session(s) - never day T itself. A similar moment counts only if it lies 6+ sessions before the pick; its 7th / 10th close counts only if that close was already known on day T.

## Coverage

- stock-days with a state: 2,788,582 (with 3-minute bars: 1,405,149)
- traded picks: 9,930 (D: 4,965); pick day with 3-minute bars: 6,957; entry session with bars: 6,942
- cross-memory pool: 26,735 earlier pick-moments; picks with a full cross memory: 9,888; median own-memory size 20 (daily), 20 (intraday)
- percentile universe: the 1,283 stocks in the frozen candidate set (every stock frozen D or the ensemble ever had in its top 10); per signal day 1156 stocks (minimum 956). The 3-minute dimensions rank among stocks with reconciled bars that day: median 1159 since 2021-10-01 (94.0% of stock-days). Note: the universe is defined by picks made up to 2026, so it is not point-in-time; it only sets the scale of the percentiles, the same for every pick.
- dropped: no state row 0, no next session 0, incomplete 0, plain-exit fallback 0

## 1. State identification (EXPLORATORY)

Daily regime stability (same regime the next session): 76.4% of 2,777,570 stock-days.

| daily regime | stock-days | same next session |
|---|---|---|
| DOWN-CALM | 342,638 | 80.3% |
| DOWN-NORMAL | 330,788 | 75.8% |
| DOWN-WILD | 250,734 | 79.9% |
| FLAT-CALM | 386,685 | 76.0% |
| FLAT-NORMAL | 327,690 | 66.5% |
| FLAT-WILD | 211,384 | 59.9% |
| UP-CALM | 194,820 | 78.6% |
| UP-NORMAL | 267,281 | 75.7% |
| UP-WILD | 465,550 | 86.4% |

Separation - do the states' average outcomes keep their order from the discovery to the confirmation window (rank agreement, +1 = same order, 0 = none):

- regime: -0.05
- iregime: -0.02
- shape: -0.37
- transition: -0.40
- seq3: 0.33

## 2. Behaviour by state - frozen D's traded picks (EXPLORATORY)

profit = 5th-close net; MFE / MAE = best / worst point over 5 sessions; hit = reached +2/+5/+10%; s1 = the entry session's intraday path (3-minute bars).

### daily regime

| state | n | profitable | mean bp [~95%] | disc / conf bp | MFE med | MAE med | hit +2/+5/+10 | OPEN_6 - CLOSE_5 | s1 first 30 min | s1 dip med | s1 low in 30 min | s1 low minute |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DOWN-WILD | 1416 | 50% | +69.1 [±53.4] | 102.2 / 12.9 | +6.34% | -5.08% | 81 / 58 / 30% | +50.2 | 26.2 bp | -2.02% | 50% | 30 |
| UP-WILD | 1137 | 53% | +135.6 [±53.3] | 143.7 / 100.0 | +6.17% | -4.93% | 81 / 59 / 30% | +57.5 | 2.2 bp | -2.22% | 45% | 51 |
| DOWN-NORMAL | 668 | 55% | +191.9 [±72.8] | 268.6 / 16.1 | +6.34% | -4.20% | 82 / 58 / 30% | +63.1 | 33.0 bp | -1.79% | 47% | 45 |
| FLAT-CALM | 547 | 42% | +53.0 [±38.9] | 53.3 / 51.9 | +1.91% | -1.62% | 49 / 23 / 6% | +25.4 | 5.9 bp | -0.66% | 50% | 27 |
| DOWN-CALM | 411 | 44% | +99.1 [±66.2] | 141.2 / -77.6 | +2.94% | -2.44% | 64 / 36 / 18% | +50.5 | 6.0 bp | -0.86% | 46% | 51 |
| UP-NORMAL | 246 | 57% | +202.8 [±119.1] | 178.4 / 306.1 | +6.10% | -3.58% | 77 / 57 / 26% | +79.9 | -9.3 bp | -1.30% | 42% | 45 |
| UP-CALM | 190 | 54% | +97.1 [±82.4] | 104.8 / 74.2 | +3.30% | -1.84% | 64 / 31 / 9% | +32.9 | -15.3 bp | -0.88% | 52% | 26 |
| FLAT-WILD | 184 | 50% | +54.4 [±111.3] | 78.0 / -49.9 | +5.99% | -4.72% | 79 / 58 / 29% | +53.8 | 25.3 bp | -1.60% | 49% | 44 |
| FLAT-NORMAL | 166 | 47% | +23.9 [±89.3] | -25.9 / 318.9 | +4.24% | -3.08% | 74 / 45 / 13% | +38.5 | 7.0 bp | -1.16% | 48% | 36 |

### intraday regime (gap x close)

| state | n | profitable | mean bp [~95%] | disc / conf bp | MFE med | MAE med | hit +2/+5/+10 | OPEN_6 - CLOSE_5 | s1 first 30 min | s1 dip med | s1 low in 30 min | s1 low minute |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| FLAT-WEAK | 1153 | 50% | +80.5 [±44.4] | 101.2 / 40.8 | +4.84% | -3.60% | 75 / 49 / 21% | +42.1 | 13.2 bp | -1.51% | 47% | 39 |
| GAPUP-WEAK | 930 | 52% | +164.4 [±60.2] | 195.6 / 44.6 | +5.99% | -4.05% | 77 / 55 / 29% | +62.1 | -2.5 bp | -2.01% | 45% | 51 |
| FLAT-MID | 687 | 46% | +74.9 [±51.8] | 109.5 / -18.3 | +3.96% | -2.50% | 67 / 42 / 18% | +39.1 | 20.4 bp | -1.11% | 49% | 33 |
| GAPDOWN-WEAK | 571 | 55% | +167.9 [±84.1] | 179.9 / 137.5 | +6.65% | -4.99% | 85 / 61 / 31% | +58.7 | 36.9 bp | -1.67% | 52% | 21 |
| GAPUP-MID | 512 | 52% | +149.2 [±83.8] | 192.2 / -6.3 | +5.43% | -3.88% | 75 / 53 / 26% | +60.8 | 12.1 bp | -1.72% | 42% | 60 |
| FLAT-STRONG | 366 | 49% | +62.1 [±68.0] | 86.2 / -11.8 | +3.58% | -2.55% | 66 / 39 / 18% | +54.2 | 11.6 bp | -1.10% | 47% | 39 |
| GAPUP-STRONG | 338 | 47% | +69.8 [±91.2] | 40.4 / 211.8 | +5.32% | -4.43% | 78 / 52 / 28% | +66.1 | 4.6 bp | -1.80% | 55% | 20 |
| GAPDOWN-MID | 263 | 48% | +41.7 [±150.0] | 51.9 / -12.3 | +6.03% | -4.93% | 73 / 55 / 33% | +43.1 | 42.4 bp | -1.14% | 54% | 16 |
| GAPDOWN-STRONG | 145 | 52% | +39.4 [±139.7] | 46.5 / 14.2 | +5.31% | -3.75% | 79 / 52 / 23% | +28.6 | -26.2 bp | -1.81% | 46% | 45 |

### intraday shape (3-minute bars)

| state | n | profitable | mean bp [~95%] | disc / conf bp | MFE med | MAE med | hit +2/+5/+10 | OPEN_6 - CLOSE_5 | s1 first 30 min | s1 dip med | s1 low in 30 min | s1 low minute |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LATE_LOW-WEAK | 1404 | 51% | +97.5 [±42.0] | 118.0 / 65.8 | +5.39% | -3.92% | 78 / 52 / 23% | +39.1 | 11.5 bp | -1.85% | 43% | 54 |
| EARLY_LOW-MID | 646 | 47% | +76.5 [±64.1] | 122.3 / -20.7 | +4.36% | -3.12% | 70 / 46 / 21% | +41.4 | 19.5 bp | -1.28% | 49% | 30 |
| EARLY_LOW-WEAK | 530 | 52% | +178.4 [±82.1] | 251.0 / 36.0 | +5.84% | -3.68% | 76 / 54 / 28% | +57.4 | 15.8 bp | -1.29% | 58% | 6 |
| EARLY_LOW-STRONG | 489 | 52% | +102.4 [±66.6] | 125.6 / 54.3 | +4.56% | -2.88% | 75 / 47 / 21% | +51.9 | 8.3 bp | -1.35% | 51% | 27 |
| LATE_LOW-MID | 341 | 49% | +48.4 [±77.6] | 68.4 / 11.6 | +4.37% | -3.10% | 72 / 44 / 21% | +47.2 | 27.8 bp | -1.31% | 43% | 63 |
| LATE_LOW-STRONG | 71 | 44% | +1.4 [±164.6] | -60.9 / 160.2 | +3.08% | -2.95% | 66 / 37 / 17% | +23.1 | -8.2 bp | -1.36% | 46% | 39 |

### regime changes (5 sessions ago > today, the 15 most common)

| state | n | profitable | mean bp [~95%] | disc / conf bp | MFE med | MAE med | hit +2/+5/+10 | OPEN_6 - CLOSE_5 | s1 first 30 min | s1 dip med | s1 low in 30 min | s1 low minute |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DOWN-NORMAL > DOWN-WILD | 189 | 52% | +146.3 [±142.4] | 199.8 / 48.8 | +6.26% | -4.80% | 84 / 60 / 30% | +17.1 | 20.9 bp | -1.98% | 43% | 60 |
| UP-WILD > DOWN-WILD | 151 | 50% | +119.0 [±168.3] | 123.2 / 107.3 | +6.37% | -4.35% | 81 / 60 / 32% | +55.3 | 59.2 bp | -1.83% | 50% | 18 |
| FLAT-WILD > DOWN-WILD | 122 | 53% | +68.1 [±162.2] | 56.1 / 102.0 | +7.43% | -4.89% | 88 / 70 / 33% | +38.9 | 51.4 bp | -1.85% | 56% | 20 |
| DOWN-WILD > DOWN-NORMAL | 122 | 61% | +158.4 [±187.7] | 270.3 / -169.8 | +6.77% | -4.32% | 86 / 61 / 35% | +66.3 | 33.6 bp | -1.67% | 59% | 12 |
| UP-CALM > FLAT-CALM | 111 | 43% | +144.4 [±137.2] | 135.2 / 179.8 | +2.08% | -1.79% | 50 / 23 / 6% | +33.1 | 22.1 bp | -0.58% | 59% | 0 |
| DOWN-CALM > DOWN-NORMAL | 99 | 51% | +201.3 [±214.0] | 419.8 / -134.9 | +6.39% | -5.02% | 76 / 55 / 28% | +67.0 | 2.4 bp | -2.08% | 42% | 48 |
| UP-WILD > FLAT-WILD | 95 | 53% | +42.5 [±166.3] | 42.6 / 41.9 | +5.94% | -4.84% | 79 / 59 / 28% | +74.3 | 24.2 bp | -1.67% | 49% | 42 |
| FLAT-CALM > DOWN-CALM | 90 | 38% | +79.6 [±120.1] | 93.9 / 18.5 | +1.61% | -1.85% | 48 / 20 / 10% | +50.2 | -8.4 bp | -0.79% | 37% | 84 |
| DOWN-CALM > FLAT-CALM | 89 | 45% | +96.9 [±90.1] | 114.4 / -5.3 | +2.24% | -1.77% | 53 / 31 / 9% | +20.2 | 26.2 bp | -0.50% | 56% | 16 |
| UP-NORMAL > UP-WILD | 76 | 49% | +28.6 [±219.0] | 224.6 / -452.5 | +6.27% | -5.62% | 84 / 58 / 30% | +51.4 | 9.6 bp | -3.13% | 40% | 150 |
| DOWN-NORMAL > DOWN-CALM | 67 | 45% | +262.1 [±261.4] | 351.0 / -190.7 | +4.84% | -4.81% | 81 / 48 / 31% | +94.4 | 29.6 bp | -1.87% | 38% | 74 |
| FLAT-WILD > UP-WILD | 60 | 53% | +123.2 [±206.6] | 138.5 / 23.9 | +5.77% | -4.39% | 83 / 57 / 30% | +51.1 | 37.3 bp | -2.00% | 30% | 114 |
| UP-WILD > UP-NORMAL | 55 | 55% | +81.7 [±193.8] | 109.6 / -109.4 | +4.83% | -3.72% | 73 / 47 / 16% | +51.4 | -8.5 bp | -1.69% | 30% | 168 |
| FLAT-NORMAL > DOWN-NORMAL | 51 | 63% | +193.0 [±171.1] | 175.8 / 248.8 | +5.95% | -3.23% | 84 / 59 / 24% | +35.4 | -15.4 bp | -2.02% | 43% | 74 |
| FLAT-CALM > UP-CALM | 47 | 47% | +67.9 [±112.1] | 80.1 / -111.0 | +2.93% | -2.25% | 57 / 28 / 9% | +26.0 | -16.3 bp | -0.89% | 38% | 86 |

### 3-day close sequence (top 15)

| state | n | profitable | mean bp [~95%] | disc / conf bp | MFE med | MAE med | hit +2/+5/+10 | OPEN_6 - CLOSE_5 | s1 first 30 min | s1 dip med | s1 low in 30 min | s1 low minute |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| WWW | 937 | 55% | +174.1 [±57.9] | 192.3 / 135.4 | +6.64% | -3.96% | 82 / 60 / 31% | +54.6 | 39.3 bp | -1.76% | 50% | 30 |
| MWW | 391 | 55% | +220.7 [±90.7] | 293.8 / 31.8 | +6.07% | -3.79% | 79 / 56 / 28% | +61.6 | 17.6 bp | -1.82% | 48% | 38 |
| WMW | 341 | 50% | +94.7 [±95.6] | 146.7 / -34.1 | +4.91% | -4.45% | 74 / 50 / 27% | +52.2 | -4.7 bp | -2.08% | 41% | 68 |
| WWM | 338 | 50% | +180.2 [±99.4] | 242.2 / 36.7 | +6.62% | -3.64% | 79 / 58 / 33% | +49.7 | 58.3 bp | -1.59% | 49% | 33 |
| SWW | 238 | 49% | +135.1 [±120.8] | 132.9 / 140.1 | +5.55% | -4.39% | 79 / 55 / 26% | +58.1 | -1.0 bp | -1.85% | 48% | 32 |
| MMW | 218 | 48% | +97.9 [±117.3] | 124.5 / 20.9 | +4.65% | -3.61% | 76 / 48 / 23% | +33.7 | 9.5 bp | -1.36% | 54% | 14 |
| MWM | 201 | 51% | +148.7 [±156.0] | 229.4 / -147.8 | +5.11% | -3.15% | 76 / 51 / 25% | +48.8 | 25.2 bp | -1.44% | 47% | 72 |
| MMM | 178 | 39% | -53.6 [±141.3] | -42.2 / -88.5 | +2.95% | -3.53% | 54 / 40 / 22% | +39.1 | 6.0 bp | -0.88% | 55% | 6 |
| WMM | 174 | 47% | +52.3 [±120.6] | 49.4 / 62.7 | +5.03% | -3.29% | 74 / 50 / 22% | +47.1 | 32.7 bp | -1.03% | 55% | 21 |
| WSW | 166 | 48% | +12.3 [±125.2] | 17.1 / -1.0 | +4.33% | -4.31% | 76 / 45 / 17% | +53.5 | -11.3 bp | -1.85% | 40% | 78 |
| WWS | 161 | 45% | -8.3 [±129.0] | -14.4 / 12.1 | +4.89% | -3.41% | 72 / 50 / 24% | +30.8 | 4.3 bp | -1.58% | 47% | 45 |
| SMW | 152 | 48% | +11.7 [±137.1] | -0.5 / 68.3 | +3.86% | -3.35% | 69 / 45 / 20% | +37.6 | -19.2 bp | -1.47% | 43% | 42 |
| SWM | 127 | 46% | +68.2 [±163.2] | 111.4 / -60.0 | +4.10% | -3.87% | 66 / 38 / 20% | +38.5 | 7.2 bp | -1.38% | 40% | 93 |
| WSM | 125 | 59% | +189.0 [±141.3] | 228.0 / 65.6 | +5.45% | -2.40% | 75 / 52 / 24% | +62.5 | 0.0 bp | -1.22% | 41% | 45 |
| MSW | 116 | 41% | -77.9 [±122.5] | -59.7 / -151.9 | +3.98% | -3.48% | 70 / 43 / 13% | +39.7 | -11.5 bp | -1.35% | 47% | 45 |

## 3. Does the Soul know anything? Memory accuracy (EXPLORATORY)

Spearman correlation between what similar earlier moments did and what this pick then did (0 = no information).

| engine | memory -> outcome | whole | discovery | confirmation | picks |
|---|---|---|---|---|---|
| D | cross memory: mean 5-session net -> 5-session net | +0.0 [-0.0, +0.1] | +0.0 [-0.0, +0.1] | +0.0 [-0.0, +0.1] | 4,944 |
| D | own daily memory (the stock's own similar days): mean 5-session net -> 5-session net | -0.0 [-0.0, +0.0] | +0.0 [-0.0, +0.0] | -0.0 [-0.1, +0.0] | 4,965 |
| D | cross memory: median MFE -> MFE | +0.2 [+0.2, +0.3] | +0.2 [+0.2, +0.3] | +0.3 [+0.2, +0.4] | 4,944 |
| D | own daily memory: median MFE -> MFE | +0.2 [+0.1, +0.2] | +0.2 [+0.1, +0.2] | +0.3 [+0.2, +0.4] | 4,965 |
| D | cross memory: chance of +5% -> reached +5% | +0.2 [+0.2, +0.3] | +0.2 [+0.2, +0.3] | +0.2 [+0.2, +0.3] | 4,944 |
| D | cross memory: session-1 dip -> session-1 dip | +0.3 [+0.2, +0.3] | +0.2 [+0.2, +0.3] | +0.3 [+0.2, +0.4] | 3,361 |
| D | own intraday memory (what this stock did the session AFTER days like T): entry-session dip -> entry-session dip | +0.3 [+0.2, +0.3] | +0.3 [+0.2, +0.3] | +0.3 [+0.2, +0.4] | 3,436 |
| D | cross memory: first-30-min return -> first-30-min return | +0.0 [-0.0, +0.1] | +0.0 [-0.0, +0.1] | +0.0 [-0.0, +0.1] | 3,360 |
| D | own intraday memory (the session AFTER days like T): first-30-min return -> first-30-min return | +0.1 [+0.0, +0.1] | +0.1 [+0.0, +0.1] | +0.0 [-0.0, +0.1] | 3,435 |
| D | cross memory: low in first 30 min -> low in first 30 min | +0.1 [+0.0, +0.1] | +0.0 [-0.0, +0.1] | +0.1 [+0.1, +0.2] | 3,361 |
| ENS | cross memory: mean 5-session net -> 5-session net | -0.0 [-0.0, +0.0] | +0.0 [-0.0, +0.1] | -0.0 [-0.1, +0.0] | 4,944 |
| ENS | own daily memory (the stock's own similar days): mean 5-session net -> 5-session net | -0.0 [-0.1, +0.0] | -0.0 [-0.1, +0.0] | -0.0 [-0.1, +0.0] | 4,965 |
| ENS | cross memory: median MFE -> MFE | +0.2 [+0.2, +0.3] | +0.2 [+0.2, +0.3] | +0.2 [+0.2, +0.3] | 4,944 |
| ENS | own daily memory: median MFE -> MFE | +0.1 [+0.1, +0.2] | +0.1 [+0.1, +0.2] | +0.2 [+0.1, +0.2] | 4,965 |
| ENS | cross memory: chance of +5% -> reached +5% | +0.2 [+0.2, +0.2] | +0.2 [+0.2, +0.3] | +0.2 [+0.1, +0.2] | 4,944 |
| ENS | cross memory: session-1 dip -> session-1 dip | +0.2 [+0.1, +0.2] | +0.1 [+0.1, +0.2] | +0.2 [+0.2, +0.3] | 3,378 |
| ENS | own intraday memory (what this stock did the session AFTER days like T): entry-session dip -> entry-session dip | +0.2 [+0.1, +0.2] | +0.2 [+0.1, +0.2] | +0.2 [+0.1, +0.3] | 3,462 |
| ENS | cross memory: first-30-min return -> first-30-min return | +0.0 [-0.0, +0.0] | +0.0 [-0.0, +0.0] | +0.0 [-0.0, +0.1] | 3,374 |
| ENS | own intraday memory (the session AFTER days like T): first-30-min return -> first-30-min return | +0.0 [-0.0, +0.1] | +0.0 [-0.0, +0.1] | +0.0 [-0.0, +0.1] | 3,458 |
| ENS | cross memory: low in first 30 min -> low in first 30 min | +0.1 [+0.0, +0.1] | +0.1 [+0.0, +0.1] | +0.1 [+0.1, +0.2] | 3,378 |

**Does the intraday state help?** Difference in Spearman, full memory minus a memory without the 3-minute dimensions, on picks whose day T has bars (above 0 = the intraday state adds information).

| engine | comparison | whole | discovery | confirmation | picks |
|---|---|---|---|---|---|
| D | 5-session net: full minus daily-only | +0.0 [-0.0, +0.1] | +0.0 [-0.0, +0.1] | +0.0 [-0.0, +0.1] | 3,481 |
| D | 5-session net: full minus daily + daily-bar pick day | +0.0 [-0.0, +0.0] | +0.0 [-0.0, +0.0] | +0.0 [-0.0, +0.1] | 3,481 |
| D | MFE: full minus daily-only | +0.0 [+0.0, +0.1] | +0.0 [-0.0, +0.1] | +0.0 [-0.0, +0.1] | 3,481 |
| D | session-1 dip: full minus daily-only | -0.0 [-0.1, +0.0] | -0.0 [-0.1, -0.0] | +0.0 [-0.0, +0.1] | 3,224 |
| D | session-1 dip: full minus daily + daily-bar pick day | -0.0 [-0.0, +0.0] | -0.0 [-0.0, +0.0] | +0.0 [-0.0, +0.1] | 3,225 |
| D | first-30-min return: full minus daily-only | +0.0 [-0.0, +0.0] | -0.0 [-0.1, +0.0] | +0.0 [-0.0, +0.1] | 3,224 |
| ENS | 5-session net: full minus daily-only | +0.0 [-0.0, +0.1] | +0.0 [-0.0, +0.1] | -0.0 [-0.1, +0.1] | 3,476 |
| ENS | 5-session net: full minus daily + daily-bar pick day | -0.0 [-0.0, +0.0] | -0.0 [-0.0, +0.0] | +0.0 [-0.0, +0.0] | 3,476 |
| ENS | MFE: full minus daily-only | +0.1 [+0.0, +0.1] | +0.0 [+0.0, +0.1] | +0.1 [-0.0, +0.1] | 3,476 |
| ENS | session-1 dip: full minus daily-only | -0.0 [-0.0, +0.0] | -0.0 [-0.0, +0.0] | -0.0 [-0.1, +0.0] | 3,223 |
| ENS | session-1 dip: full minus daily + daily-bar pick day | -0.0 [-0.0, +0.0] | -0.0 [-0.0, +0.0] | -0.0 [-0.1, +0.0] | 3,222 |
| ENS | first-30-min return: full minus daily-only | -0.0 [-0.1, +0.0] | -0.0 [-0.1, +0.0] | -0.0 [-0.1, +0.0] | 3,221 |

## 4. Targets - win rates and profit, D's traded top 3 (EXPLORATORY)

win = target reached within 5 sessions; profitable = net above 0; vs 5th close = paired difference per signal day (bp a trade). C5 / O6 = the exit when the target is not reached: the 5th close / the 6th open.

### Normal targets

| rule | win | profitable | mean net bp | vs 5th close: whole | discovery | confirmation | verdict |
|---|---|---|---|---|---|---|---|
| T2|C5 | 75% | 76% | -1.6 | -108.8 [-150.0, -68.0] | -129.0 [-178.6, -81.8] | -49.9 [-109.7, +9.9] | - |
| T2|O6 | 75% | 78% | +7.6 | -99.6 [-140.5, -58.9] | -118.2 [-168.3, -71.4] | -45.4 [-104.0, +12.8] | - |
| T5|C5 | 51% | 60% | +53.4 | -53.8 [-83.8, -24.8] | -69.9 [-107.8, -35.9] | -6.9 [-49.7, +36.9] | - |
| T5|O6 | 51% | 63% | +71.2 | -36.1 [-65.9, -7.6] | -49.8 [-88.6, -15.5] | +3.9 [-36.5, +44.8] | - |
| T10|C5 | 25% | 52% | +89.7 | -17.5 [-39.2, +1.5] | -26.6 [-52.2, -4.0] | +9.0 [-16.1, +32.8] | - |
| T10|O6 | 25% | 55% | +120.1 | +12.9 [-7.7, +31.6] | +8.9 [-17.7, +31.6] | +24.6 [-1.5, +48.8] | - |
| T3ATR|C5 | 12% | 51% | +107.8 | +0.6 [-8.8, +8.7] | -1.2 [-12.3, +8.9] | +5.7 [-5.4, +17.6] | - |
| T3ATR|O6 | 12% | 54% | +147.6 | +40.4 [+29.5, +51.3] | +45.5 [+32.6, +58.3] | +25.5 [+9.0, +40.5] | PROMISING |

### State-specific targets

| rule | win | profitable | mean net bp | vs 5th close: whole | discovery | confirmation | verdict |
|---|---|---|---|---|---|---|---|
| SQ30|C5 | 68% | 70% | +23.1 | -84.2 [-120.7, -48.3] | -105.3 [-151.4, -63.5] | -22.7 [-72.1, +28.2] | - |
| SQ30|O6 | 68% | 72% | +35.6 | -71.7 [-108.0, -37.5] | -91.3 [-137.2, -49.7] | -14.5 [-62.7, +34.0] | - |
| SQ50|C5 | 49% | 59% | +62.8 | -44.4 [-74.5, -16.6] | -59.8 [-96.3, -26.0] | +0.6 [-37.2, +38.8] | - |
| SQ50|O6 | 49% | 62% | +82.7 | -24.5 [-54.1, +2.6] | -37.2 [-74.8, -3.8] | +12.6 [-22.3, +46.9] | - |
| SQ70|C5 | 29% | 53% | +86.2 | -21.1 [-43.2, -1.4] | -31.5 [-59.5, -7.5] | +9.2 [-16.0, +34.0] | - |
| SQ70|O6 | 29% | 56% | +115.1 | +7.9 [-14.0, +26.7] | +2.2 [-27.3, +26.1] | +24.7 [-0.7, +49.7] | - |
| RQ50|C5 | 50% | 59% | +58.1 | -49.1 [-80.0, -21.0] | -65.2 [-103.1, -31.1] | -2.1 [-44.4, +38.0] | - |
| RQ50|O6 | 50% | 62% | +76.8 | -30.4 [-61.1, -2.0] | -44.2 [-82.4, -10.5] | +9.9 [-28.8, +47.0] | - |
| IQ50|C5 | 52% | 61% | +52.1 | -55.1 [-85.4, -27.0] | -70.6 [-109.4, -36.1] | -9.8 [-49.5, +31.4] | - |
| IQ50|O6 | 52% | 64% | +69.6 | -37.6 [-67.6, -9.0] | -50.4 [-89.8, -15.7] | -0.4 [-38.8, +37.6] | - |

### Stock-specific targets

| rule | win | profitable | mean net bp | vs 5th close: whole | discovery | confirmation | verdict |
|---|---|---|---|---|---|---|---|
| OQ30|C5 | 73% | 75% | +2.0 | -105.2 [-142.9, -68.6] | -126.1 [-172.6, -83.1] | -44.6 [-99.3, +10.2] | - |
| OQ30|O6 | 73% | 76% | +12.6 | -94.6 [-131.4, -58.1] | -113.9 [-160.2, -71.2] | -38.6 [-92.6, +15.3] | - |
| OQ50|C5 | 59% | 65% | +39.3 | -68.0 [-99.5, -38.5] | -84.6 [-123.9, -48.8] | -19.6 [-63.5, +25.1] | - |
| OQ50|O6 | 59% | 67% | +55.2 | -52.0 [-83.0, -22.7] | -66.5 [-106.1, -30.4] | -9.7 [-53.8, +33.3] | - |
| OQ70|C5 | 41% | 57% | +76.3 | -30.9 [-55.3, -8.1] | -44.0 [-74.7, -17.0] | +7.1 [-26.5, +41.5] | - |
| OQ70|O6 | 41% | 60% | +101.0 | -6.2 [-30.1, +16.1] | -15.7 [-46.8, +12.2] | +21.3 [-11.2, +53.2] | - |
| OQ50S|C5 | 52% | 60% | +54.0 | -53.2 [-82.9, -25.1] | -69.3 [-106.0, -36.2] | -6.5 [-46.3, +32.5] | - |
| OQ50S|O6 | 52% | 63% | +72.4 | -34.8 [-64.4, -7.2] | -48.3 [-85.7, -15.3] | +4.4 [-33.3, +38.8] | - |

Baseline (5th close) on these picks: +107.2 bp a trade.

### Are the state and stock targets calibrated?

A 30th-percentile target should be reached about 70% of the time, a median one about 50%, a 70th-percentile one about 30%.

| engine | target | expected | whole | discovery | confirmation | picks with a target |
|---|---|---|---|---|---|---|
| D | SQ30 | 70% | 68% | 70% | 65% | 4,944 |
| D | SQ50 | 50% | 49% | 51% | 45% | 4,944 |
| D | SQ70 | 30% | 29% | 30% | 24% | 4,944 |
| D | RQ50 | 50% | 50% | 50% | 49% | 4,903 |
| D | IQ50 | 50% | 52% | 52% | 52% | 4,898 |
| D | OQ30 | 70% | 73% | 74% | 73% | 4,965 |
| D | OQ50 | 50% | 59% | 59% | 59% | 4,965 |
| D | OQ70 | 30% | 41% | 42% | 41% | 4,965 |
| D | OQ50S | 50% | 52% | 53% | 49% | 4,965 |
| ENS | SQ30 | 70% | 69% | 71% | 62% | 4,944 |
| ENS | SQ50 | 50% | 49% | 51% | 43% | 4,944 |
| ENS | SQ70 | 30% | 28% | 30% | 24% | 4,944 |
| ENS | RQ50 | 50% | 50% | 51% | 46% | 4,902 |
| ENS | IQ50 | 50% | 52% | 53% | 51% | 4,901 |
| ENS | OQ30 | 70% | 74% | 75% | 70% | 4,965 |
| ENS | OQ50 | 50% | 58% | 59% | 55% | 4,965 |
| ENS | OQ70 | 30% | 41% | 42% | 38% | 4,965 |
| ENS | OQ50S | 50% | 52% | 53% | 47% | 4,965 |

### Targets by daily regime (D)

| state | n | 5th close bp | +2%: win / bp | +5%: win / bp | +10%: win / bp | state median: win / bp | stock median: win / bp |
|---|---|---|---|---|---|---|---|
| DOWN-WILD | 1416 | +69.1 | 81% / -18.4 | 58% / +35.6 | 30% / +63.7 | 48% / +55.6 | 62% / +18.0 |
| UP-WILD | 1137 | +135.6 | 81% / -2.4 | 59% / +65.6 | 30% / +112.2 | 54% / +71.3 | 59% / +48.6 |
| DOWN-NORMAL | 668 | +191.9 | 82% / +16.2 | 58% / +74.3 | 30% / +141.8 | 51% / +109.3 | 64% / +82.6 |
| FLAT-CALM | 547 | +53.0 | 49% / -5.4 | 23% / +35.5 | 6% / +45.8 | 41% / +11.2 | 48% / +14.4 |
| DOWN-CALM | 411 | +99.1 | 64% / +22.3 | 36% / +53.9 | 18% / +82.3 | 44% / +64.3 | 55% / +37.5 |
| UP-NORMAL | 246 | +202.8 | 77% / -15.2 | 57% / +69.5 | 26% / +146.3 | 52% / +63.4 | 58% / +73.5 |
| UP-CALM | 190 | +97.1 | 64% / +28.1 | 31% / +68.5 | 9% / +79.1 | 48% / +53.3 | 54% / +40.3 |
| FLAT-WILD | 184 | +54.4 | 79% / -4.4 | 58% / +58.6 | 29% / +107.2 | 55% / +76.4 | 64% / +39.3 |
| FLAT-NORMAL | 166 | +23.9 | 74% / +19.4 | 45% / +48.0 | 13% / +20.6 | 50% / +40.8 | 54% / +16.3 |

## 5. Other rules, D (EXPLORATORY)

| rule | taken | mean net bp | vs 5th close: whole | discovery | confirmation | verdict |
|---|---|---|---|---|---|---|
| SH | 100% | +160.3 | +53.1 [+21.7, +83.9] | +59.1 [+21.7, +96.1] | +35.4 [-13.2, +83.1] | PROMISING |
| OH | 100% | +158.8 | +51.6 [+28.1, +77.1] | +50.7 [+23.0, +79.8] | +54.1 [+5.5, +106.4] | PROMISING |
| VETO_CROSS_NEG | 77% | +121.0 | -14.5 [-45.7, +16.5] | -20.1 [-60.3, +16.9] | +1.6 [-20.9, +25.3] | - |
| VETO_OWN_NEG | 42% | +100.9 | -64.7 [-96.8, -34.3] | -77.1 [-115.8, -41.4] | -28.9 [-81.3, +22.7] | - |
| VETO_BOTH_NEG | 86% | +113.4 | -10.2 [-30.2, +8.2] | -12.9 [-38.9, +9.4] | -2.2 [-20.5, +17.6] | - |
| OPEN_6 | 100% | +158.7 | +51.5 [+43.3, +60.1] | +59.9 [+50.3, +69.4] | +26.8 [+11.6, +39.5] | PROMISING |
| CLOSE_3 | 100% | +48.8 | -58.4 [-82.5, -36.2] | -69.8 [-98.4, -42.1] | -25.4 [-63.6, +14.5] | - |
| CLOSE_7 | 100% | +139.6 | +32.3 [+8.1, +58.4] | +34.4 [+6.7, +62.8] | +26.4 [-21.1, +70.8] | PROMISING |
| CLOSE_10 | 100% | +187.3 | +80.1 [+27.6, +134.7] | +87.5 [+23.1, +154.2] | +58.4 [-24.9, +146.2] | PROMISING |

## 6. The ensemble (reported)

Rules promising for the ensemble too: T3ATR|O6, SH, OH, OPEN_6, CLOSE_7, CLOSE_10.

## 7. Stocks most often picked, D (EXPLORATORY)

| stock | picks | 5th close bp | own target | own target win | own target vs 5th close | +5% win | MFE med | s1 dip med |
|---|---|---|---|---|---|---|---|---|
| NDL | 92 | +109.6 | 5.59% | 59% | -76.9 | 63% | 7.03% | -2.82% |
| PCJEWELLER | 84 | +451.7 | 5.97% | 60% | -183.5 | 67% | 7.68% | -1.92% |
| FCL | 54 | +130.0 | 6.32% | 43% | -77.9 | 56% | 5.83% | -1.39% |
| CUPID | 53 | +470.1 | 5.03% | 64% | -326.0 | 62% | 7.46% | -2.25% |
| VAKRANGEE | 42 | -356.7 | 3.52% | 50% | -71.1 | 38% | 4.55% | -2.50% |
| GTLINFRA | 41 | +168.2 | 5.08% | 59% | -167.0 | 61% | 7.43% | -1.06% |
| SILVERADD | 41 | +9.9 | 2.31% | 61% | -39.2 | 37% | 3.79% | -0.86% |
| RUSHIL | 37 | +294.1 | 4.74% | 76% | -38.7 | 81% | 7.15% | -1.86% |
| STEELXIND | 36 | +101.4 | 5.85% | 44% | -353.9 | 47% | 4.23% | -3.40% |
| WEBELSOLAR | 36 | +379.8 | 7.38% | 56% | -338.8 | 64% | 7.50% | -1.84% |
| SALASAR | 36 | +358.6 | 5.25% | 69% | -191.5 | 61% | 7.50% | -2.17% |
| LIQUIDCASE | 33 | -38.5 | 0.20% | 3% | 8.8 | 0% | 0.09% | -0.02% |
| GOLDADD | 33 | +62.4 | 2.09% | 61% | 28.2 | 12% | 2.68% | -0.76% |
| SILVER1 | 32 | +43.5 | 2.96% | 69% | -44.1 | 38% | 3.95% | -0.22% |
| RTNPOWER | 32 | +495.3 | 5.28% | 72% | -243.6 | 69% | 8.71% | -2.21% |
| RPOWER | 30 | -275.3 | 4.82% | 57% | 93.8 | 50% | 4.74% | -1.62% |
| V2RETAIL | 29 | +341.4 | 4.84% | 69% | -410.4 | 66% | 9.70% | -2.59% |
| JPPOWER | 28 | +26.5 | 4.77% | 61% | -87.9 | 54% | 5.96% | -2.21% |
| SAREGAMA | 27 | +116.8 | 5.32% | 56% | -31.9 | 59% | 6.15% | -4.36% |
| IDEA | 26 | +127.0 | 4.79% | 54% | -89.9 | 58% | 5.72% | -2.09% |

## 8. Shadow-lane candidates (PROMISING - not validated; the forward test decides)

- T3ATR|O6: +40.4 [+29.5, +51.3] bp vs the 5th close (confirmation +25.5)
- SH: +53.1 [+21.7, +83.9] bp vs the 5th close (confirmation +35.4)
- OH: +51.6 [+28.1, +77.1] bp vs the 5th close (confirmation +54.1)
- OPEN_6: +51.5 [+43.3, +60.1] bp vs the 5th close (confirmation +26.8)
- CLOSE_7: +32.3 [+8.1, +58.4] bp vs the 5th close (confirmation +26.4)
- CLOSE_10: +80.1 [+27.6, +134.7] bp vs the 5th close (confirmation +58.4)

Exploration only: nothing here changes the engines or the paper test.
