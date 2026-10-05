# Intraday study of the frozen picks

intraday_study v1.4 | declaration ec9b1952035f6080 | 1,221 signal days | 3-minute bars | candidates 90f221ed218476e8

**Descriptive.** Baseline = buy at the 09:15 open, sell at the 5th close (honest exits), 35 bp; entry rules keep the same calendar exit. Differences are per signal day with 95% intervals. Rows marked BENCHMARK and the oracles are never rules.

## Core menus - D, traded top 3

| rule | vs baseline bp [95%] | fill rate |
|---|---|---|
| entry OPEN (BENCHMARK) | +0.0 [+0.0, +0.0] | 100% |
| entry VWAP_15 | -14.0 [-19.7, -8.3] | 100% |
| entry VWAP_30 | -16.1 [-22.6, -9.8] | 100% |
| entry VWAP_60 | -19.0 [-26.2, -12.1] | 100% |
| entry VWAP_DAY (BENCHMARK) | -30.1 [-39.9, -20.9] | 100% |
| entry CLOSE_T1 | -31.2 [-43.5, -19.5] | 100% |
| entry LIMIT_PREV_VWAP | -14.5 [-28.4, -1.2] | 85% |
| entry LIMIT_PREV_VPOC | -18.6 [-32.5, -5.5] | 84% |
| entry ORB_HIGH_15 | -37.8 [-62.0, -13.1] | 57% |
| entry ORACLE_LOW (BENCHMARK) | +225.1 [+210.0, +240.4] | 100% |
| exit CLOSE_5 (BENCHMARK) | +0.0 [+0.0, +0.0] | 100% |
| exit OPEN_5 | +22.9 [+10.8, +35.2] | 100% |
| exit OPEN_6 | +44.7 [+36.3, +53.0] | 100% |
| exit VWAP_15_6 | +36.6 [+28.6, +44.4] | 100% |
| exit VWAP_DAY_5 | +20.7 [+15.1, +26.8] | 100% |
| exit CLOSE_3 | -51.4 [-75.5, -27.7] | 100% |
| exit CLOSE_7 | +33.9 [+6.8, +60.3] | 100% |
| exit CLOSE_10 | +81.5 [+28.5, +133.9] | 100% |
| exit ORACLE_HIGH (BENCHMARK) | +552.5 [+514.7, +591.9] | 100% |

## Core menus - D, ranks 4-10 (not traded)

| rule | vs baseline bp [95%] | fill rate |
|---|---|---|
| entry OPEN (BENCHMARK) | +0.0 [+0.0, +0.0] | 100% |
| entry VWAP_15 | -13.6 [-17.9, -9.3] | 100% |
| entry VWAP_30 | -15.8 [-20.7, -10.7] | 100% |
| entry VWAP_60 | -18.7 [-24.2, -13.2] | 100% |
| entry VWAP_DAY (BENCHMARK) | -25.4 [-33.0, -17.7] | 100% |
| entry CLOSE_T1 | -15.5 [-25.4, -5.9] | 100% |
| entry LIMIT_PREV_VWAP | -6.1 [-16.0, +3.3] | 86% |
| entry LIMIT_PREV_VPOC | -6.5 [-16.8, +3.3] | 85% |
| entry ORB_HIGH_15 | -19.7 [-43.1, +4.3] | 57% |
| entry ORACLE_LOW (BENCHMARK) | +211.5 [+199.1, +224.5] | 100% |
| exit CLOSE_5 (BENCHMARK) | +0.0 [+0.0, +0.0] | 100% |
| exit OPEN_5 | +20.8 [+11.4, +30.3] | 100% |
| exit OPEN_6 | +38.1 [+32.5, +43.8] | 100% |
| exit VWAP_15_6 | +37.3 [+30.9, +44.0] | 100% |
| exit VWAP_DAY_5 | +18.4 [+14.5, +22.3] | 100% |
| exit CLOSE_3 | -29.1 [-51.8, -6.8] | 100% |
| exit CLOSE_7 | +36.1 [+15.3, +56.8] | 100% |
| exit CLOSE_10 | +67.6 [+22.0, +112.6] | 100% |
| exit ORACLE_HIGH (BENCHMARK) | +525.4 [+491.0, +561.9] | 100% |

## Core menus - ENS, traded top 3

| rule | vs baseline bp [95%] | fill rate |
|---|---|---|
| entry OPEN (BENCHMARK) | +0.0 [+0.0, +0.0] | 100% |
| entry VWAP_15 | -18.4 [-24.1, -12.8] | 100% |
| entry VWAP_30 | -22.0 [-28.6, -15.5] | 100% |
| entry VWAP_60 | -25.5 [-32.8, -18.0] | 100% |
| entry VWAP_DAY (BENCHMARK) | -38.9 [-50.2, -27.9] | 100% |
| entry CLOSE_T1 | -38.8 [-53.8, -24.2] | 100% |
| entry LIMIT_PREV_VWAP | -19.2 [-33.0, -6.2] | 87% |
| entry LIMIT_PREV_VPOC | -16.4 [-30.3, -2.9] | 86% |
| entry ORB_HIGH_15 | -50.9 [-77.3, -23.6] | 59% |
| entry ORACLE_LOW (BENCHMARK) | +221.6 [+208.4, +235.2] | 100% |
| exit CLOSE_5 (BENCHMARK) | +0.0 [+0.0, +0.0] | 100% |
| exit OPEN_5 | +27.5 [+16.1, +39.0] | 100% |
| exit OPEN_6 | +44.0 [+35.6, +52.4] | 100% |
| exit VWAP_15_6 | +38.9 [+30.8, +47.0] | 100% |
| exit VWAP_DAY_5 | +22.4 [+17.1, +28.1] | 100% |
| exit CLOSE_3 | -45.1 [-72.3, -18.5] | 100% |
| exit CLOSE_7 | +29.8 [+3.4, +56.4] | 100% |
| exit CLOSE_10 | +67.3 [+12.8, +121.8] | 100% |
| exit ORACLE_HIGH (BENCHMARK) | +568.0 [+530.8, +608.4] | 100% |

## Core menus - ENS, ranks 4-10 (not traded)

| rule | vs baseline bp [95%] | fill rate |
|---|---|---|
| entry OPEN (BENCHMARK) | +0.0 [+0.0, +0.0] | 100% |
| entry VWAP_15 | -15.8 [-20.0, -11.6] | 100% |
| entry VWAP_30 | -19.5 [-24.4, -14.8] | 100% |
| entry VWAP_60 | -22.7 [-28.1, -17.4] | 100% |
| entry VWAP_DAY (BENCHMARK) | -28.9 [-36.9, -21.1] | 100% |
| entry CLOSE_T1 | -21.0 [-31.1, -11.1] | 100% |
| entry LIMIT_PREV_VWAP | -5.4 [-15.4, +3.7] | 88% |
| entry LIMIT_PREV_VPOC | -8.9 [-20.3, +1.8] | 86% |
| entry ORB_HIGH_15 | -24.8 [-47.1, -2.3] | 58% |
| entry ORACLE_LOW (BENCHMARK) | +207.3 [+195.4, +219.6] | 100% |
| exit CLOSE_5 (BENCHMARK) | +0.0 [+0.0, +0.0] | 100% |
| exit OPEN_5 | +18.5 [+9.1, +28.3] | 100% |
| exit OPEN_6 | +33.1 [+27.7, +38.5] | 100% |
| exit VWAP_15_6 | +30.9 [+25.2, +36.7] | 100% |
| exit VWAP_DAY_5 | +18.7 [+15.0, +22.4] | 100% |
| exit CLOSE_3 | -35.2 [-56.7, -13.7] | 100% |
| exit CLOSE_7 | +24.9 [+6.1, +43.7] | 100% |
| exit CLOSE_10 | +53.4 [+10.6, +95.5] | 100% |
| exit ORACLE_HIGH (BENCHMARK) | +518.6 [+485.8, +553.8] | 100% |

## Catalogue protocol - D traded top 3 (48 rules, BH q = 0.1)

| rule | discovery bp [95%] | p | confirmation bp [95%] | verdict |
|---|---|---|---|---|
| X:OPEN_6 | +54.0 [+44.1, +63.8] | 0.001 | +27.1 [+12.4, +40.1] | CONFIRMED -> forward lane |
| X:OPEN_7 | +73.8 [+50.8, +96.3] | 0.001 | +36.0 [+6.0, +66.7] | CONFIRMED -> forward lane |
| X:VWAP_15_6 | +46.1 [+37.2, +55.0] | 0.001 | +18.9 [+3.7, +33.2] | CONFIRMED -> forward lane |
| X:VWAP_30_6 | +43.2 [+33.4, +52.9] | 0.001 | +21.5 [+6.2, +36.0] | CONFIRMED -> forward lane |
| X:VWAP_DAY_5 | +21.2 [+13.7, +29.5] | 0.001 | +19.8 [+11.9, +27.4] | CONFIRMED -> forward lane |
| X:VWAP_DAY_6 | +38.8 [+25.5, +51.9] | 0.001 | +29.7 [+7.9, +51.7] | CONFIRMED -> forward lane |
| X:TIME5_240 | +7.5 [-1.7, +17.3] | 0.086 | +14.2 [+5.1, +23.1] | CONFIRMED -> forward lane |
| E:CLOSE_T1 | -34.1 [-49.3, -19.2] | 0.001 | -25.6 [-46.7, -5.0] | failed confirmation - discarded |
| E:VWAP_120 | -18.9 [-29.1, -8.7] | 0.001 | -27.9 [-40.1, -15.9] | failed confirmation - discarded |
| E:VWAP_15 | -12.6 [-19.9, -5.5] | 0.001 | -16.6 [-25.7, -7.7] | failed confirmation - discarded |
| E:VWAP_30 | -14.6 [-22.7, -6.3] | 0.001 | -19.1 [-29.1, -9.2] | failed confirmation - discarded |
| E:VWAP_45 | -17.0 [-25.8, -8.3] | 0.001 | -22.1 [-32.7, -11.7] | failed confirmation - discarded |
| E:VWAP_60 | -16.9 [-25.9, -7.9] | 0.001 | -22.9 [-34.2, -11.9] | failed confirmation - discarded |
| E:VWAP_90 | -17.5 [-27.1, -7.7] | 0.001 | -26.4 [-38.6, -14.6] | failed confirmation - discarded |
| X:CLOSE_3 | -63.3 [-94.0, -32.3] | 0.001 | -29.0 [-69.9, +9.6] | failed confirmation - discarded |
| X:CLOSE_4 | -29.5 [-46.7, -12.2] | 0.001 | -22.2 [-45.4, -0.2] | failed confirmation - discarded |
| X:OPEN_5 | +26.6 [+11.3, +42.2] | 0.002 | +16.0 [-3.9, +35.0] | failed confirmation - discarded |
| E:ORB_HIGH_30 | -59.7 [-97.4, -21.9] | 0.003 | -35.7 [-80.8, +8.5] | failed confirmation - discarded |
| E:TIME_15 | -14.3 [-24.1, -4.8] | 0.003 | -17.0 [-28.4, -5.7] | failed confirmation - discarded |
| E:VWAP_6 | -8.9 [-14.6, -2.9] | 0.003 | -12.5 [-20.5, -4.5] | failed confirmation - discarded |
| X:TIME5_15 | +19.9 [+6.1, +33.9] | 0.003 | +8.2 [-7.8, +23.9] | failed confirmation - discarded |
| E:ORB_HIGH_15 | -46.3 [-76.7, -14.3] | 0.004 | -21.9 [-60.2, +17.0] | failed confirmation - discarded |
| E:VWAP_9 | -9.6 [-15.8, -3.3] | 0.004 | -14.3 [-22.8, -5.9] | failed confirmation - discarded |
| E:TIME_240 | -18.2 [-32.2, -4.7] | 0.005 | -22.1 [-39.9, -4.5] | failed confirmation - discarded |
| X:CLOSE_10 | +91.7 [+25.1, +159.0] | 0.005 | +62.2 [-24.8, +153.2] | failed confirmation - discarded |
| E:PULLBACK_1 | -42.2 [-73.0, -13.6] | 0.007 | -13.2 [-47.9, +19.6] | failed confirmation - discarded |
| E:PULLBACK_3 | -62.5 [-110.2, -15.2] | 0.009 | -20.7 [-81.5, +38.4] | failed confirmation - discarded |
| E:TIME_120 | -16.6 [-29.5, -3.5] | 0.009 | -21.7 [-37.5, -5.5] | failed confirmation - discarded |
| E:GAPUP2_VWAP30_ELSE_OPEN | +2.6 [+0.6, +4.7] | 0.009 | +0.2 [-3.7, +4.0] | failed confirmation - discarded |
| E:PULLBACK_0.5 | -32.4 [-58.2, -8.8] | 0.009 | -17.0 [-42.5, +6.9] | failed confirmation - discarded |
| E:TIME_9 | -10.0 [-18.3, -1.7] | 0.011 | -16.6 [-27.7, -6.0] | failed confirmation - discarded |
| E:PULLBACK_1.5 | -43.4 [-78.3, -8.9] | 0.013 | -12.3 [-53.3, +27.1] | failed confirmation - discarded |
| E:PULLBACK_0.25 | -26.9 [-50.3, -6.1] | 0.015 | -21.8 [-43.7, -1.5] | failed confirmation - discarded |
| E:TIME_6 | -9.5 [-17.2, -1.9] | 0.017 | -13.9 [-23.8, -4.0] | failed confirmation - discarded |
| E:TIME_30 | -11.7 [-22.0, -1.4] | 0.022 | -15.8 [-28.1, -3.8] | failed confirmation - discarded |
| X:CLOSE_7 | +38.0 [+5.0, +70.2] | 0.025 | +26.3 [-19.9, +74.4] | failed confirmation - discarded |
| E:GAPDN2_OPEN_ELSE_VWAP30 | -8.4 [-16.0, -0.8] | 0.026 | -13.2 [-22.6, -3.8] | failed confirmation - discarded |
| E:PULLBACK_2 | -46.7 [-87.9, -6.7] | 0.029 | -14.4 [-63.5, +34.2] | failed confirmation - discarded |
| X:TIME5_30 | +15.2 [+1.4, +29.3] | 0.033 | +8.0 [-7.8, +22.9] | failed confirmation - discarded |
| E:TIME_60 | -11.9 [-22.9, -0.6] | 0.035 | -22.0 [-36.2, -7.8] | failed confirmation - discarded |
| X:CLOSE_6 | +18.3 [+0.8, +35.2] | 0.042 | +6.5 [-18.9, +32.6] | failed confirmation - discarded |
| E:TIME_3 | -6.6 [-13.0, +0.2] | 0.046 | -9.5 [-18.7, +0.0] | failed confirmation - discarded |
| E:ORB_HIGH_6 | -25.8 [-51.3, -0.1] | 0.049 | -24.8 [-58.8, +10.7] | failed confirmation - discarded |
| E:LIMIT_PREV_CLOSE | -20.4 [-43.3, -0.0] | 0.053 | -25.4 [-54.0, -0.2] | failed confirmation - discarded |
| E:LIMIT_PREV_VPOC | -17.8 [-36.6, -0.7] | 0.053 | -20.2 [-42.0, -0.0] | failed confirmation - discarded |
| X:TIME5_60 | +10.9 [-2.0, +24.0] | 0.087 | +10.1 [-6.2, +25.6] | failed confirmation - discarded |
| X:TIME5_120 | +9.9 [-1.9, +21.9] | 0.098 | +10.0 [-2.8, +22.6] | failed confirmation - discarded |
| E:LIMIT_PREV_VWAP | -12.9 [-30.7, +3.5] | 0.148 | -17.5 [-41.5, +3.6] | failed discovery - discarded |

## Catalogue protocol - ENS traded top 3 (48 rules, BH q = 0.1) - forward lanes come only from D

| rule | discovery bp [95%] | p | confirmation bp [95%] | verdict |
|---|---|---|---|---|
| X:OPEN_6 | +51.1 [+41.3, +61.1] | 0.001 | +30.5 [+15.9, +44.1] | confirmed (ensemble - reported, not a forward lane) |
| X:OPEN_7 | +76.1 [+49.3, +102.5] | 0.001 | +50.3 [+18.5, +82.6] | confirmed (ensemble - reported, not a forward lane) |
| X:TIME5_240 | +14.5 [+6.5, +23.5] | 0.001 | +9.3 [+0.7, +17.8] | confirmed (ensemble - reported, not a forward lane) |
| X:VWAP_15_6 | +47.6 [+37.8, +57.4] | 0.001 | +22.5 [+8.6, +35.1] | confirmed (ensemble - reported, not a forward lane) |
| X:VWAP_30_6 | +47.9 [+37.5, +58.4] | 0.001 | +24.8 [+11.1, +38.1] | confirmed (ensemble - reported, not a forward lane) |
| X:VWAP_DAY_5 | +25.5 [+18.2, +33.3] | 0.001 | +16.6 [+8.9, +24.0] | confirmed (ensemble - reported, not a forward lane) |
| X:VWAP_DAY_6 | +45.6 [+32.3, +58.6] | 0.001 | +37.8 [+16.2, +60.2] | confirmed (ensemble - reported, not a forward lane) |
| E:CLOSE_T1 | -51.9 [-70.4, -34.1] | 0.001 | -13.9 [-36.4, +9.2] | failed confirmation - discarded |
| E:GAPDN2_OPEN_ELSE_VWAP30 | -21.5 [-28.6, -14.4] | 0.001 | -5.0 [-14.7, +4.7] | failed confirmation - discarded |
| E:ORB_HIGH_15 | -72.8 [-103.9, -39.9] | 0.001 | -9.4 [-55.4, +36.1] | failed confirmation - discarded |
| E:ORB_HIGH_30 | -86.9 [-124.4, -47.7] | 0.001 | -19.6 [-71.3, +30.5] | failed confirmation - discarded |
| E:ORB_HIGH_6 | -53.7 [-81.2, -24.6] | 0.001 | -9.9 [-47.2, +28.3] | failed confirmation - discarded |
| E:TIME_120 | -39.1 [-53.9, -24.2] | 0.001 | -14.2 [-32.0, +4.0] | failed confirmation - discarded |
| E:TIME_15 | -28.7 [-37.6, -19.8] | 0.001 | -5.4 [-17.5, +6.8] | failed confirmation - discarded |
| E:TIME_240 | -40.3 [-56.2, -24.6] | 0.001 | -12.9 [-32.4, +6.7] | failed confirmation - discarded |
| E:TIME_3 | -15.4 [-21.6, -9.2] | 0.001 | -4.1 [-13.3, +4.8] | failed confirmation - discarded |
| E:TIME_30 | -30.6 [-41.6, -19.3] | 0.001 | -4.5 [-19.0, +10.1] | failed confirmation - discarded |
| E:TIME_6 | -20.0 [-27.4, -12.6] | 0.001 | -6.3 [-16.7, +3.9] | failed confirmation - discarded |
| E:TIME_60 | -29.9 [-41.7, -18.0] | 0.001 | -10.6 [-28.1, +7.3] | failed confirmation - discarded |
| E:TIME_9 | -26.0 [-33.4, -18.8] | 0.001 | -9.8 [-20.6, +0.6] | failed confirmation - discarded |
| E:VWAP_120 | -38.0 [-48.7, -27.1] | 0.001 | -18.2 [-32.3, -3.9] | failed confirmation - discarded |
| E:VWAP_15 | -24.4 [-31.2, -17.6] | 0.001 | -7.3 [-16.5, +1.7] | failed confirmation - discarded |
| E:VWAP_30 | -29.3 [-37.3, -21.2] | 0.001 | -8.4 [-19.2, +2.5] | failed confirmation - discarded |
| E:VWAP_45 | -32.7 [-41.4, -23.8] | 0.001 | -10.7 [-22.7, +1.4] | failed confirmation - discarded |
| E:VWAP_6 | -18.7 [-24.2, -12.9] | 0.001 | -5.5 [-13.3, +2.2] | failed confirmation - discarded |
| E:VWAP_60 | -32.6 [-41.4, -23.6] | 0.001 | -12.0 [-24.5, +1.0] | failed confirmation - discarded |
| E:VWAP_9 | -20.9 [-27.0, -14.7] | 0.001 | -7.0 [-15.4, +1.0] | failed confirmation - discarded |
| E:VWAP_90 | -35.5 [-45.3, -25.5] | 0.001 | -16.0 [-29.7, -2.0] | failed confirmation - discarded |
| X:OPEN_5 | +32.1 [+18.3, +46.3] | 0.001 | +18.8 [-1.0, +37.9] | failed confirmation - discarded |
| X:TIME5_120 | +19.2 [+10.9, +27.6] | 0.001 | +8.2 [-4.6, +21.1] | failed confirmation - discarded |
| X:TIME5_15 | +25.6 [+14.0, +37.4] | 0.001 | +4.3 [-11.5, +19.6] | failed confirmation - discarded |
| X:TIME5_30 | +22.0 [+11.2, +33.0] | 0.001 | +4.5 [-10.7, +18.9] | failed confirmation - discarded |
| X:TIME5_60 | +20.1 [+10.1, +30.2] | 0.001 | +6.0 [-9.4, +20.5] | failed confirmation - discarded |
| X:CLOSE_3 | -54.8 [-87.8, -22.3] | 0.002 | -26.5 [-73.3, +18.8] | failed confirmation - discarded |
| E:PULLBACK_3 | -73.3 [-124.0, -23.4] | 0.003 | -4.4 [-74.0, +64.3] | failed confirmation - discarded |
| X:CLOSE_4 | -23.5 [-40.2, -7.2] | 0.003 | -16.3 [-41.8, +8.3] | failed confirmation - discarded |
| E:PULLBACK_1 | -44.7 [-77.9, -11.0] | 0.005 | -13.8 [-51.4, +21.4] | failed confirmation - discarded |
| E:PULLBACK_0.5 | -35.7 [-63.6, -8.1] | 0.007 | -16.5 [-45.3, +11.2] | failed confirmation - discarded |
| E:PULLBACK_0.25 | -33.0 [-59.3, -7.6] | 0.009 | -24.0 [-50.7, +1.3] | failed confirmation - discarded |
| E:PULLBACK_1.5 | -49.5 [-87.6, -10.8] | 0.009 | -4.4 [-49.6, +39.1] | failed confirmation - discarded |
| E:LIMIT_PREV_VWAP | -20.7 [-37.8, -4.8] | 0.011 | -16.4 [-40.4, +4.8] | failed confirmation - discarded |
| E:LIMIT_PREV_VPOC | -20.4 [-38.3, -3.6] | 0.018 | -8.7 [-32.2, +12.9] | failed confirmation - discarded |
| X:CLOSE_6 | +21.5 [+2.5, +40.1] | 0.019 | +19.8 [-6.5, +47.2] | failed confirmation - discarded |
| E:PULLBACK_2 | -48.7 [-91.0, -6.6] | 0.026 | +0.6 [-53.2, +52.6] | failed confirmation - discarded |
| X:CLOSE_10 | +65.9 [-0.1, +132.8] | 0.048 | +69.9 [-23.9, +168.5] | failed confirmation - discarded |
| E:LIMIT_PREV_CLOSE | -17.9 [-38.9, +1.4] | 0.069 | -24.4 [-51.9, -0.5] | failed confirmation - discarded |
| X:CLOSE_7 | +28.1 [-3.1, +59.4] | 0.074 | +33.1 [-13.9, +82.6] | failed confirmation - discarded |
| E:GAPUP2_VWAP30_ELSE_OPEN | +1.4 [-1.0, +3.9] | 0.255 | -1.8 [-5.3, +1.4] | failed discovery - discarded |

## Findings register (F2, F6, F7 here; F1, F3, F4, F5 in the next step)

```
{
 "D_top3": {
  "F2_tug_of_war": {
   "entry_gap_bp_not_earned": 16.0,
   "by_session": {
    "gap": {
     "1": 0.0,
     "2": 32.1,
     "3": 36.8,
     "4": 39.4,
     "5": 39.9
    },
    "session_ret": {
     "1": 34.4,
     "2": 9.0,
     "3": -9.1,
     "4": -6.8,
     "5": -12.2
    }
   },
   "confirmation_by_session": {
    "gap": {
     "1": 0.0,
     "2": 29.2,
     "3": 32.2,
     "4": 28.9,
     "5": 33.3
    },
    "session_ret": {
     "1": 26.8,
     "2": -2.7,
     "3": -12.1,
     "4": -11.6,
     "5": -13.7
    }
   },
   "where_in_session_bp": {
    "min_0_15": 0.4,
    "min_15_60": -1.8,
    "min_60_240": 0.3,
    "min_240_315": -0.5,
    "min_315_375": 4.8
   }
  },
  "F6_bracket_3min": {
   "trades": 3672,
   "bracket_net_bp": 72.86376506338257,
   "plain_exit_net_bp": 98.36362757140995,
   "bracket_still_loses": true
  },
  "F7_opening_execution_bp": {
   "first_bar_vwap_vs_open_bp": {
    "<20": 0.0,
    "20-100": 0.0,
    "100-500": 0.8,
    "500-2000": 0.0,
    ">2000": 4.6
   },
   "first_bar_range_bp": {
    "<20": 154.3,
    "20-100": 148.0,
    "100-500": 150.6,
    "500-2000": 114.7,
    ">2000": 83.4
   }
  }
 },
 "D_ranks4_10": {
  "F2_tug_of_war": {
   "entry_gap_bp_not_earned": 22.2,
   "by_session": {
    "gap": {
     "1": 0.0,
     "2": 33.3,
     "3": 32.9,
     "4": 30.3,
     "5": 30.7
    },
    "session_ret": {
     "1": 16.8,
     "2": -4.8,
     "3": -6.8,
     "4": -13.5,
     "5": -12.2
    }
   },
   "confirmation_by_session": {
    "gap": {
     "1": 0.0,
     "2": 29.3,
     "3": 23.1,
     "4": 22.8,
     "5": 21.4
    },
    "session_ret": {
     "1": 13.0,
     "2": -8.2,
     "3": -5.7,
     "4": -10.9,
     "5": -10.3
    }
   },
   "where_in_session_bp": {
    "min_0_15": 1.3,
    "min_15_60": -1.9,
    "min_60_240": -2.6,
    "min_240_315": -2.7,
    "min_315_375": 1.7
   }
  },
  "F6_bracket_3min": {
   "trades": 8511,
   "bracket_net_bp": 25.815988588800103,
   "plain_exit_net_bp": 48.37451037731788,
   "bracket_still_loses": true
  },
  "F7_opening_execution_bp": {
   "first_bar_vwap_vs_open_bp": {
    "<20": 3.8,
    "20-100": 5.6,
    "100-500": 0.8,
    "500-2000": 0.0,
    ">2000": 0.0
   },
   "first_bar_range_bp": {
    "<20": 151.6,
    "20-100": 133.8,
    "100-500": 130.7,
    "500-2000": 105.5,
    ">2000": 78.2
   }
  }
 },
 "ENS_top3": {
  "F2_tug_of_war": {
   "entry_gap_bp_not_earned": 6.8,
   "by_session": {
    "gap": {
     "1": 0.0,
     "2": 30.6,
     "3": 35.3,
     "4": 38.2,
     "5": 36.3
    },
    "session_ret": {
     "1": 39.4,
     "2": -1.9,
     "3": -6.4,
     "4": -13.8,
     "5": -14.1
    }
   },
   "confirmation_by_session": {
    "gap": {
     "1": 0.0,
     "2": 26.0,
     "3": 29.4,
     "4": 30.7,
     "5": 28.3
    },
    "session_ret": {
     "1": 17.6,
     "2": -9.4,
     "3": -6.6,
     "4": -13.7,
     "5": -13.7
    }
   },
   "where_in_session_bp": {
    "min_0_15": 1.4,
    "min_15_60": -0.9,
    "min_60_240": -0.2,
    "min_240_315": -1.7,
    "min_315_375": 2.2
   }
  },
  "F6_bracket_3min": {
   "trades": 3672,
   "bracket_net_bp": 56.258736036897645,
   "plain_exit_net_bp": 78.35561087016374,
   "bracket_still_loses": true
  },
  "F7_opening_execution_bp": {
   "first_bar_vwap_vs_open_bp": {
    "<20": 0.0,
    "20-100": 6.9,
    "100-500": 3.7,
    "500-2000": 3.5,
    ">2000": 2.4
   },
   "first_bar_range_bp": {
    "<20": 157.6,
    "20-100": 139.9,
    "100-500": 144.1,
    "500-2000": 119.6,
    ">2000": 97.5
   }
  }
 },
 "ENS_ranks4_10": {
  "F2_tug_of_war": {
   "entry_gap_bp_not_earned": 20.4,
   "by_session": {
    "gap": {
     "1": 0.0,
     "2": 29.9,
     "3": 30.4,
     "4": 31.1,
     "5": 29.1
    },
    "session_ret": {
     "1": 21.1,
     "2": -2.2,
     "3": -10.0,
     "4": -11.2,
     "5": -11.8
    }
   },
   "confirmation_by_session": {
    "gap": {
     "1": 0.0,
     "2": 25.2,
     "3": 21.9,
     "4": 21.0,
     "5": 20.0
    },
    "session_ret": {
     "1": 17.9,
     "2": -3.1,
     "3": -7.6,
     "4": -1.7,
     "5": -10.8
    }
   },
   "where_in_session_bp": {
    "min_0_15": 1.5,
    "min_15_60": -0.8,
    "min_60_240": -2.6,
    "min_240_315": -2.2,
    "min_315_375": 1.3
   }
  },
  "F6_bracket_3min": {
   "trades": 8514,
   "bracket_net_bp": 29.374067073618793,
   "plain_exit_net_bp": 52.7484380995321,
   "bracket_still_loses": true
  },
  "F7_opening_execution_bp": {
   "first_bar_vwap_vs_open_bp": {
    "<20": 0.0,
    "20-100": 6.8,
    "100-500": 4.8,
    "500-2000": 0.0,
    ">2000": -0.2
   },
   "first_bar_range_bp": {
    "<20": 144.0,
    "20-100": 129.6,
    "100-500": 125.8,
    "500-2000": 111.0,
    ">2000": 90.2
   }
  }
 },
 "reconciliation_exclusions": {
  "exit_sessions_not_reconciled": 7788,
  "entry_not_reconciled": 1120
 }
}
```

## Descriptors vs the 5-session outcome (rank correlation by window; a sign flip means noise)

| engine | group | descriptor | when | discovery | confirmation |
|---|---|---|---|---|---|
| D | ranks4_10 | gap | session 1 | -0.019 | -0.035 |
| D | ranks4_10 | ret_15 | session 1 | +0.223 | +0.217 |
| D | ranks4_10 | ret_30 | session 1 | +0.244 | +0.238 |
| D | ranks4_10 | range_15 | session 1 | +0.055 | +0.041 |
| D | ranks4_10 | open_vol_share_15 | session 1 | -0.069 | -0.068 |
| D | ranks4_10 | session_ret | session 1 | +0.391 | +0.421 |
| D | ranks4_10 | close_vs_vwap | session 1 | +0.276 | +0.310 |
| D | ranks4_10 | vwap_crossings | session 1 | +0.027 | +0.042 |
| D | ranks4_10 | close_location | session 1 | +0.310 | +0.336 |
| D | ranks4_10 | afternoon_ret | session 1 | +0.163 | +0.222 |
| D | ranks4_10 | slope | session 1 | +0.307 | +0.344 |
| D | ranks4_10 | rel_volume_20 | session 1 | +0.112 | +0.081 |
| D | ranks4_10 | vol_accel | session 1 | +0.022 | +0.057 |
| D | ranks4_10 | last_hour_share | session 1 | -0.015 | +0.013 |
| D | ranks4_10 | close_vs_vpoc | session 1 | +0.201 | +0.218 |
| D | ranks4_10 | mfe_open | session 1 | +0.297 | +0.301 |
| D | ranks4_10 | mae_open | session 1 | +0.273 | +0.278 |
| D | ranks4_10 | minute_of_high | session 1 | +0.272 | +0.301 |
| D | ranks4_10 | minute_of_low | session 1 | -0.267 | -0.293 |
| D | ranks4_10 | recovery_from_low | session 1 | +0.333 | +0.375 |
| D | ranks4_10 | reversals_15 | session 1 | -0.009 | -0.007 |
| D | ranks4_10 | vs_nifty | session 1 | +0.364 | +0.395 |
| D | ranks4_10 | near_lower_band | session 1 | +0.180 | +0.166 |
| D | ranks4_10 | near_upper_band | session 1 | -0.079 | -0.034 |
| D | ranks4_10 | frozen_bars | session 1 | -0.003 | +0.030 |
| D | ranks4_10 | gap | pick day | -0.006 | -0.019 |
| D | ranks4_10 | ret_15 | pick day | -0.010 | -0.011 |
| D | ranks4_10 | ret_30 | pick day | -0.026 | -0.026 |
| D | ranks4_10 | range_15 | pick day | +0.016 | +0.026 |
| D | ranks4_10 | open_vol_share_15 | pick day | -0.038 | -0.022 |
| D | ranks4_10 | session_ret | pick day | -0.046 | -0.010 |
| D | ranks4_10 | close_vs_vwap | pick day | -0.022 | +0.002 |
| D | ranks4_10 | vwap_crossings | pick day | +0.005 | -0.000 |
| D | ranks4_10 | close_location | pick day | -0.018 | -0.000 |
| D | ranks4_10 | afternoon_ret | pick day | -0.025 | -0.026 |
| D | ranks4_10 | slope | pick day | -0.039 | +0.007 |
| D | ranks4_10 | rel_volume_20 | pick day | +0.043 | +0.005 |
| D | ranks4_10 | vol_accel | pick day | +0.017 | +0.062 |
| D | ranks4_10 | last_hour_share | pick day | +0.005 | +0.047 |
| D | ranks4_10 | close_vs_vpoc | pick day | -0.014 | +0.012 |
| D | ranks4_10 | mfe_open | pick day | -0.004 | +0.002 |
| D | ranks4_10 | mae_open | pick day | -0.052 | -0.013 |
| D | ranks4_10 | minute_of_high | pick day | -0.016 | -0.010 |
| D | ranks4_10 | minute_of_low | pick day | +0.034 | +0.002 |
| D | ranks4_10 | recovery_from_low | pick day | -0.024 | -0.010 |
| D | ranks4_10 | reversals_15 | pick day | +0.004 | -0.037 |
| D | ranks4_10 | vs_nifty | pick day | -0.053 | -0.024 |
| D | ranks4_10 | near_lower_band | pick day | +0.019 | +0.034 |
| D | ranks4_10 | near_upper_band | pick day | +0.005 | -0.003 |
| D | ranks4_10 | frozen_bars | pick day | -0.011 | +0.052 |
| D | top3 | gap | session 1 | +0.021 | -0.007 |
| D | top3 | ret_15 | session 1 | +0.199 | +0.183 |
| D | top3 | ret_30 | session 1 | +0.200 | +0.236 |
| D | top3 | range_15 | session 1 | +0.069 | +0.076 |
| D | top3 | open_vol_share_15 | session 1 | -0.055 | -0.035 |
| D | top3 | session_ret | session 1 | +0.395 | +0.369 |
| D | top3 | close_vs_vwap | session 1 | +0.302 | +0.281 |
| D | top3 | vwap_crossings | session 1 | +0.025 | +0.051 |
| D | top3 | close_location | session 1 | +0.331 | +0.302 |
| D | top3 | afternoon_ret | session 1 | +0.165 | +0.181 |
| D | top3 | slope | session 1 | +0.322 | +0.301 |
| D | top3 | rel_volume_20 | session 1 | +0.115 | +0.081 |
| D | top3 | vol_accel | session 1 | +0.008 | -0.010 |
| D | top3 | last_hour_share | session 1 | -0.015 | -0.031 |
| D | top3 | close_vs_vpoc | session 1 | +0.239 | +0.212 |
| D | top3 | mfe_open | session 1 | +0.304 | +0.278 |
| D | top3 | mae_open | session 1 | +0.204 | +0.204 |
| D | top3 | minute_of_high | session 1 | +0.267 | +0.266 |
| D | top3 | minute_of_low | session 1 | -0.255 | -0.231 |
| D | top3 | recovery_from_low | session 1 | +0.370 | +0.315 |
| D | top3 | reversals_15 | session 1 | -0.027 | +0.032 |
| D | top3 | vs_nifty | session 1 | +0.379 | +0.351 |
| D | top3 | near_lower_band | session 1 | +0.179 | +0.104 |
| D | top3 | near_upper_band | session 1 | -0.133 | -0.074 |
| D | top3 | frozen_bars | session 1 | +0.043 | +0.056 |
| D | top3 | gap | pick day | +0.026 | -0.030 |
| D | top3 | ret_15 | pick day | +0.015 | -0.008 |
| D | top3 | ret_30 | pick day | -0.015 | -0.014 |
| D | top3 | range_15 | pick day | +0.065 | +0.047 |
| D | top3 | open_vol_share_15 | pick day | -0.022 | -0.018 |
| D | top3 | session_ret | pick day | -0.035 | -0.039 |
| D | top3 | close_vs_vwap | pick day | -0.034 | -0.030 |
| D | top3 | vwap_crossings | pick day | -0.004 | -0.011 |
| D | top3 | close_location | pick day | -0.018 | -0.014 |
| D | top3 | afternoon_ret | pick day | -0.049 | -0.008 |
| D | top3 | slope | pick day | -0.038 | -0.052 |
| D | top3 | rel_volume_20 | pick day | +0.052 | +0.017 |
| D | top3 | vol_accel | pick day | +0.029 | +0.032 |
| D | top3 | last_hour_share | pick day | +0.017 | +0.036 |
| D | top3 | close_vs_vpoc | pick day | -0.008 | +0.002 |
| D | top3 | mfe_open | pick day | +0.006 | +0.002 |
| D | top3 | mae_open | pick day | -0.048 | -0.045 |
| D | top3 | minute_of_high | pick day | -0.024 | +0.009 |
| D | top3 | minute_of_low | pick day | -0.014 | +0.033 |
| D | top3 | recovery_from_low | pick day | -0.025 | -0.028 |
| D | top3 | reversals_15 | pick day | -0.057 | +0.015 |
| D | top3 | vs_nifty | pick day | -0.041 | -0.050 |
| D | top3 | near_lower_band | pick day | +0.026 | -0.009 |
| D | top3 | near_upper_band | pick day | +0.007 | +0.012 |
| D | top3 | frozen_bars | pick day | +0.028 | +0.045 |
| ENS | ranks4_10 | gap | session 1 | -0.009 | -0.060 |
| ENS | ranks4_10 | ret_15 | session 1 | +0.209 | +0.203 |
| ENS | ranks4_10 | ret_30 | session 1 | +0.228 | +0.238 |
| ENS | ranks4_10 | range_15 | session 1 | +0.052 | +0.083 |
| ENS | ranks4_10 | open_vol_share_15 | session 1 | -0.053 | +0.014 |
| ENS | ranks4_10 | session_ret | session 1 | +0.392 | +0.392 |
| ENS | ranks4_10 | close_vs_vwap | session 1 | +0.294 | +0.291 |
| ENS | ranks4_10 | vwap_crossings | session 1 | +0.003 | +0.020 |
| ENS | ranks4_10 | close_location | session 1 | +0.330 | +0.317 |
| ENS | ranks4_10 | afternoon_ret | session 1 | +0.192 | +0.184 |
| ENS | ranks4_10 | slope | session 1 | +0.319 | +0.314 |
| ENS | ranks4_10 | rel_volume_20 | session 1 | +0.138 | +0.066 |
| ENS | ranks4_10 | vol_accel | session 1 | +0.017 | +0.006 |
| ENS | ranks4_10 | last_hour_share | session 1 | -0.008 | -0.021 |
| ENS | ranks4_10 | close_vs_vpoc | session 1 | +0.219 | +0.218 |
| ENS | ranks4_10 | mfe_open | session 1 | +0.298 | +0.306 |
| ENS | ranks4_10 | mae_open | session 1 | +0.253 | +0.241 |
| ENS | ranks4_10 | minute_of_high | session 1 | +0.272 | +0.272 |
| ENS | ranks4_10 | minute_of_low | session 1 | -0.263 | -0.271 |
| ENS | ranks4_10 | recovery_from_low | session 1 | +0.358 | +0.347 |
| ENS | ranks4_10 | reversals_15 | session 1 | -0.018 | -0.025 |
| ENS | ranks4_10 | vs_nifty | session 1 | +0.362 | +0.366 |
| ENS | ranks4_10 | near_lower_band | session 1 | +0.180 | +0.127 |
| ENS | ranks4_10 | near_upper_band | session 1 | -0.065 | -0.048 |
| ENS | ranks4_10 | frozen_bars | session 1 | +0.025 | -0.023 |
| ENS | ranks4_10 | gap | pick day | +0.001 | -0.015 |
| ENS | ranks4_10 | ret_15 | pick day | +0.013 | +0.016 |
| ENS | ranks4_10 | ret_30 | pick day | -0.014 | -0.007 |
| ENS | ranks4_10 | range_15 | pick day | +0.051 | +0.045 |
| ENS | ranks4_10 | open_vol_share_15 | pick day | -0.022 | -0.012 |
| ENS | ranks4_10 | session_ret | pick day | -0.048 | -0.066 |
| ENS | ranks4_10 | close_vs_vwap | pick day | -0.036 | -0.053 |
| ENS | ranks4_10 | vwap_crossings | pick day | -0.035 | -0.022 |
| ENS | ranks4_10 | close_location | pick day | -0.031 | -0.055 |
| ENS | ranks4_10 | afternoon_ret | pick day | -0.039 | -0.052 |
| ENS | ranks4_10 | slope | pick day | -0.055 | -0.086 |
| ENS | ranks4_10 | rel_volume_20 | pick day | +0.070 | +0.014 |
| ENS | ranks4_10 | vol_accel | pick day | +0.004 | +0.034 |
| ENS | ranks4_10 | last_hour_share | pick day | +0.021 | +0.005 |
| ENS | ranks4_10 | close_vs_vpoc | pick day | -0.010 | -0.024 |
| ENS | ranks4_10 | mfe_open | pick day | +0.025 | -0.002 |
| ENS | ranks4_10 | mae_open | pick day | -0.052 | -0.062 |
| ENS | ranks4_10 | minute_of_high | pick day | -0.022 | -0.017 |
| ENS | ranks4_10 | minute_of_low | pick day | +0.025 | +0.021 |
| ENS | ranks4_10 | recovery_from_low | pick day | -0.045 | -0.053 |
| ENS | ranks4_10 | reversals_15 | pick day | -0.005 | -0.043 |
| ENS | ranks4_10 | vs_nifty | pick day | -0.046 | -0.073 |
| ENS | ranks4_10 | near_lower_band | pick day | +0.023 | +0.010 |
| ENS | ranks4_10 | near_upper_band | pick day | -0.002 | +0.048 |
| ENS | ranks4_10 | frozen_bars | pick day | +0.030 | -0.019 |
| ENS | top3 | gap | session 1 | +0.016 | +0.001 |
| ENS | top3 | ret_15 | session 1 | +0.186 | +0.202 |
| ENS | top3 | ret_30 | session 1 | +0.203 | +0.260 |
| ENS | top3 | range_15 | session 1 | +0.105 | +0.090 |
| ENS | top3 | open_vol_share_15 | session 1 | -0.068 | -0.035 |
| ENS | top3 | session_ret | session 1 | +0.358 | +0.380 |
| ENS | top3 | close_vs_vwap | session 1 | +0.278 | +0.247 |
| ENS | top3 | vwap_crossings | session 1 | +0.022 | +0.071 |
| ENS | top3 | close_location | session 1 | +0.297 | +0.287 |
| ENS | top3 | afternoon_ret | session 1 | +0.154 | +0.136 |
| ENS | top3 | slope | session 1 | +0.298 | +0.294 |
| ENS | top3 | rel_volume_20 | session 1 | +0.116 | +0.124 |
| ENS | top3 | vol_accel | session 1 | +0.035 | -0.016 |
| ENS | top3 | last_hour_share | session 1 | -0.020 | -0.025 |
| ENS | top3 | close_vs_vpoc | session 1 | +0.215 | +0.196 |
| ENS | top3 | mfe_open | session 1 | +0.292 | +0.321 |
| ENS | top3 | mae_open | session 1 | +0.183 | +0.233 |
| ENS | top3 | minute_of_high | session 1 | +0.216 | +0.268 |
| ENS | top3 | minute_of_low | session 1 | -0.237 | -0.248 |
| ENS | top3 | recovery_from_low | session 1 | +0.320 | +0.333 |
| ENS | top3 | reversals_15 | session 1 | -0.032 | -0.003 |
| ENS | top3 | vs_nifty | session 1 | +0.336 | +0.357 |
| ENS | top3 | near_lower_band | session 1 | +0.148 | +0.144 |
| ENS | top3 | near_upper_band | session 1 | -0.126 | -0.108 |
| ENS | top3 | frozen_bars | session 1 | +0.042 | +0.030 |
| ENS | top3 | gap | pick day | +0.009 | -0.001 |
| ENS | top3 | ret_15 | pick day | -0.027 | -0.020 |
| ENS | top3 | ret_30 | pick day | -0.043 | -0.033 |
| ENS | top3 | range_15 | pick day | +0.041 | +0.056 |
| ENS | top3 | open_vol_share_15 | pick day | -0.083 | +0.046 |
| ENS | top3 | session_ret | pick day | -0.044 | -0.014 |
| ENS | top3 | close_vs_vwap | pick day | -0.010 | +0.000 |
| ENS | top3 | vwap_crossings | pick day | +0.013 | +0.015 |
| ENS | top3 | close_location | pick day | -0.004 | +0.002 |
| ENS | top3 | afternoon_ret | pick day | -0.030 | -0.022 |
| ENS | top3 | slope | pick day | -0.028 | +0.003 |
| ENS | top3 | rel_volume_20 | pick day | +0.049 | +0.010 |
| ENS | top3 | vol_accel | pick day | +0.056 | +0.001 |
| ENS | top3 | last_hour_share | pick day | +0.017 | +0.039 |
| ENS | top3 | close_vs_vpoc | pick day | +0.020 | +0.023 |
| ENS | top3 | mfe_open | pick day | -0.009 | +0.001 |
| ENS | top3 | mae_open | pick day | -0.065 | -0.028 |
| ENS | top3 | minute_of_high | pick day | -0.000 | -0.022 |
| ENS | top3 | minute_of_low | pick day | -0.010 | +0.019 |
| ENS | top3 | recovery_from_low | pick day | -0.015 | -0.013 |
| ENS | top3 | reversals_15 | pick day | -0.033 | -0.010 |
| ENS | top3 | vs_nifty | pick day | -0.067 | -0.026 |
| ENS | top3 | near_lower_band | pick day | -0.008 | +0.014 |
| ENS | top3 | near_upper_band | pick day | -0.023 | -0.019 |
| ENS | top3 | frozen_bars | pick day | +0.012 | +0.046 |

Nothing here changes the engines or the paper test; a confirmed D rule becomes its own forward lane.
