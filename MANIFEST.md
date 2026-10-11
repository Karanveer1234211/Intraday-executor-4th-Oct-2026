# bigmove_deploy - bundle manifest (10 Oct 2026)

How to install: RUNBOOK.md section 6. In short - `daily_run.bat`, `RUNBOOK.md` and
`MANIFEST.md` go into `bigmove_deploy\`; the `open_close\` folder (with `tests\`)
goes over yours. Nothing else in the main folder changes. Keep your own
`env_daily.bat` and `watchlist.txt`.

## A. Nightly automation (main folder)
| file | version | what it does |
|---|---|---|
| run_now.bat | v1 | run the nightly job by hand: progress on screen, window stays open, RESULT at the end (use after 18:00 or before 09:00; never while the scheduled job runs) |
| daily_run.bat | v5.4 | weekdays after 18:00 IST; step 1 skips the old panel and report (--no-panel --no-report); step 1 gives the cache its 600-day window and sets aside stocks with old gaps (--allow-partial); the watchlist refuses a day whose entry session already opened; a progress line at every step: 1 Kite cache + quality gate + report (run_daily.py, as v4) -> 2 panel_live update -> 3 watchlist + Soul cards recorded in the paper ledger -> 4 settle + tracker + daily log + report. Replaces v4; v4's Soul v3 / signal_engine steps are retired. |

## B. Production: the paper test (`open_close\`)
| file | version | what it does |
|---|---|---|
| paper_pipeline.py | v1.6 | `init-live` (panel_live = copy of panel_oc, once) / `watchlist` (frozen production scores for D and ENS, ETFs out, top 10 each + Soul cards, appended to the hash-chained ledger; `--skip-if-recorded` for holidays; `--dry-run`) / `settle` (first 3 buyable per engine, honest exits, 35 bp, late flag, excess over every buyable non-ETF universe stock; rebuilds tracker.md/.csv and daily_log.md) / `report` (month-6 rule, sessions with no watchlist) / `verify-ledger`. The day's universe is hash-chained in the ledger |
| production_models.py | v1.1 | `train` once: the frozen recipe on all resolved history (D on its 205 frozen features, ENS's C member on its 123), SHA-256 fingerprinted in `panel_oc\frozen\production\`; records library versions and refuses to load under different ones; `verify` |
| preflight.py | v1.8 | run before day 1 (and whenever in doubt): environment, files and versions, declaration fingerprints, daily_run.bat v5, freeze, production models and their wiring against the walk-forward runs, panel_live vs panel_oc, ledger, Task Scheduler, dry-run watchlist; ends READY FOR DAY 1 or lists what to fix |
| soul_v4.py | v1.1 | Soul cards: per stock-day honest 5-session outcome (MFE, MAE, locked exit, days to +5%, overnight vs in-session); card = state percentiles, personality (1-year half-life, shrunk to the market, K = 30), memory (20 own + 50 cross nearest moments), the engines' past record with the stock, circuit flags; the stage C profile (12 research-backed features with their measured oc_5 IC, t and favoured side) and the stock's own tug of war; only finished trades |
| freeze_engines.py | v1 | freezes D (primary) and ENS (challenger): SHA-256 of their runs, code, declarations and panel metadata in `panel_oc\frozen\FROZEN_ENGINES.json`; every production and research tool re-verifies |
| PAPER_DECLARATION.json | oc_v1 paper (f75aa3de0dc4278f) | the paper test: roles, recording, settlement, late rule, month-6 rule for D, month-12 rule for ENS, Soul settings - fixed before day 1 |

## C. Research: how the engines were found (`open_close\`, frozen history)
| file | version | what it did |
|---|---|---|
| panel_build.py | v32 | model-ready panel with open-to-close targets, buyable flag, ETFs out (also builds panel_live nightly) |
| label_audit.py | - | independent re-computation of every label |
| research_common.py | - | shared research code (ledger, state, market state, guards) |
| stage_b_screen.py | v1.2 | stage B: every existing feature screened one at a time (606 of 684 cells) |
| stage_d_gate.py | v1 | stage D: the walk-forward model on all 205 clean features - engine D |
| stage_d_forensics.py | v1 | honest exits: locked lower-circuit closes sold at the first sellable open; tick sizes; ISIN rules |
| stage_d2_nested.py | v1.1 | D2: nested feature selection - kept baseline D |
| stage_c_features.py | v1 | stage C: 123 new features (overnight/intraday, market model, lottery, liquidity, circuits, ...) |
| stage_c_screen.py | v1 | stage C screen + leak checks (364 of 452 cells, no leak suspects) |
| stage_dc_model.py | v1.1 | D_C: D plus all C features (and the C-only arm) - kept baseline D |
| stage_dx_ensemble.py | v1 | the C-only model and the 50/50 rank ensemble - ENS |
| compare_d_variants.py | v1.2 | scores every variant with corrected exits; paired decisions; pick agreement |
| stage_e_execution.py | v1.2 | execution backtest (Zerodha costs, impact, capacity, grids, stops, benchmarks). v1.1: optional per-trade exit planner and a `held` column. v1.2: optional minimum order (off by default, so every earlier result is unchanged; the re-ranker test uses 25%) |
| stage_e_paths.py | v1 | inside the trades: MFE/MAE, time to target, stops, 39 exit rules vs the plain exit |

## C2. Research pipeline 2 and tools (`open_close\`, run by hand, write only to `<root>\research2\`)
| file | version | what it does |
|---|---|---|
| soul_meta.py | v1 | the Soul re-ranker on frozen D: D's top 10 each day, point-in-time Soul / circuit / C-profile / tug / market inputs, targets for H3 H5 H7 H10 and the 3/2 ATR bracket, walk-forward 2022-2026 with a 30-session embargo, veto 0.30, 30 bp hurdle; scored in the execution simulator against D on the same days (25% minimum order); PASS only if the paired 98.75% lower bound > 0 |
| tests\test_soul_meta.py | - | planted trap-prone stocks -> PASS; the same traps at random -> KEEP D; bracket and personality exact; point in time; rule; embargo |
| INTRADAY_DECLARATION.json | intraday_v1 (ec9b1952035f6080) | the intraday study of the frozen picks on 3-minute bars: core entry/exit menus, a broad catalogue under a discovery (2021-10 to 2024) -> confirmation (2025 on, used once) -> forward protocol, a register of earlier findings to re-test, reconciliation rules - declared before any intraday data was examined |
| intraday_cache.py | v1.6 | --full-history fetches every session of every picked stock (for the Soul study); reconciles the close against the 15:00-15:30 VWAP (NSE official close); symbols files keep names with spaces, NIFTY 50 fetched by its Kite token, empty runs safe; fetches only the picks' windows (T..T+10, missing sessions only, resumable), 100-day requests, 3 in flight under the daily cache's 3-a-second limiter, progress with ETA; 3-minute bars (15-minute and coarser derived by resample); 15-minute bars for every stock D or the ensemble ever had in its top 10 plus paper picks: import (existing files, --dry-run), update (Kite, the daily cache's login, completed sessions only), check (reconcile with the daily cache; flags split-basis mismatches). Writes only <root>\intraday_15m\ |
| tests\test_intraday_cache.py | - | chunked fetch, incremental updates, session-complete rule, failure isolation, expired token, imports (file-name and symbol-column layouts, UTC), dry run, reconciliation with planted split-basis and volume faults |
| intraday_features.py | v1 | the declared intraday descriptors of one stock-day from 3-minute bars (opening, trend, volume, path, relative, circuit; VWAP on typical price, VPOC = busiest 15-minute bar); uses only that day plus earlier days' volume |
| intraday_study.py | v1.4 | TIME rules fill at the first later trade when nothing traded by minute k; tested on gappy sessions; only reconciled entry sessions, intraday exits only on reconciled sessions, both counted; 20-session volume from the daily cache (works with windowed intraday data); D and the ensemble x traded top 3 / ranks 4-10; VWAP_DAY and oracles benchmark-only; only D's confirmations become forward lanes; entry gap reported; frozen candidate set; the frozen picks inside each session: core entry/exit menus vs open -> 5th close (honest circuit exits, unfilled limits hold cash), the full catalogue under discovery (BH q 0.10, to 2024) -> confirmation (2025 on, once), the session path and findings F2 / F6 / F7, descriptors vs outcome by window. Writes only <root>\research2\intraday\IS_* |
| tests\test_intraday_study.py | - | VWAP / VPOC / fills / breakout / descriptors by hand; frozen-circuit exit fallback; 3-minute bracket ordering; PLANTED 30-minute dip -> discovered and confirmed; ABSENT noise -> no always-filled rule survives |
| CONFIRM_DECLARATION.json | confirm_v1 (2b57e1b3e925d107) | confirmation entries: 19 signals (price, VWAP/VPOC levels, RSI, MACD, volume, NIFTY, gap) at minutes 3/6/15/30 plus a wait-to-30 form = 95 rules; RETURN or PAIN winners (MAE + worst 10% on trades taken, >= 50% kept, no significant return loss), discovery -> confirmation -> forward |
| confirmation_study.py | v1 | runs confirm_v1 on frozen D's and the ensemble's traded top 3 (intraday_v1's frozen candidates, reconciled entry sessions). Writes only <root>\research2\confirm\CS_* |
| tests\test_confirmation_study.py | - | RSI/MACD/signal timing by hand; planted DIPS CONTINUE -> HOLD_OPEN wins; DIPS RECOVER -> discarded; NOISE -> nothing wins |
| SOUL_INTRADAY_DECLARATION.json | soul_intraday_v1 (1c2ada8d487d68b3) | amended before any real run (8 Oct, review): horizon embargo, thin-bar guard, universe and timing stated, EXPLORATORY / PROMISING labels;  Soul + intraday Soul, exploration mode: daily state (10) + transitions (3) + pick-day state (4 daily-bar, 6 three-minute-bar), labels (regime, intraday regime, shape, regime change, 3-day sequence), cross / own / own-intraday memories with a 6-session lag, normal / state / stock targets, PROMISING = discovery lower bound > 0 and confirmation mean > 0 |
| soul_intraday_study.py | v1.1 | v1.1: a memory's 7th/10th-close average counts a similar moment only if that exit was known on the pick day (found by the future-perturbation test); refuses thin 3-minute coverage unless --allow-partial-bars; reports the percentile universe per day; runs soul_intraday_v1 on frozen D's and the ensemble's traded top 3 (intraday_v1's frozen candidates, fingerprint checked): state stability and separation, behaviour by state incl. the entry session's intraday path, memory accuracy and what the 3-minute state adds, three target families with win rates and calibration, stock table. Writes only <root>\research2\soul_intraday\SI_* |
| tests\test_soul_intraday_study.py | - | the reviewer's checks: brute-force outcome alignment, independent re-implementation of ranks / neighbours / memory / targets / fills / nets, FUTURE PERTURBATION on 3 dates (fails without the embargo), missing bars, C5 / O6 fallback, later-open fills, thin-bar guard, universe = candidates only; by hand (dimensions, outcomes, 3-minute sessions, percentiles, distance, target fills); no look-ahead; PLANTED (regime-dependent peaks + bar-only entry-session dip) -> memory skill, calibrated targets, PROMISING state target, intraday adds; NULL -> none; main() end to end with stand-ins (reconciliation filter, locked 6th open, edited candidates refused). Verified on pandas 3.0 and 2.2 |
| stock_analyzer.py | v1 | one stock (or several, comma-separated), one date (`--date` = that close, `--entry` = that open, default = the last close): an HTML page + console summary. State vs its own history; NIFTY context (returns, regime, beta, relative strength); its 20 most similar earlier days (the tested own-memory measures) and what followed; the MEASURED track record of that swing forecast on this stock (forecasts remade every 5 sessions from past data only, judged against luck by time-shifted outcomes, calibrated on null stocks); personality; frozen D / ENS top-10 history with honest-exit outcomes (known-by-the-date via the real exit day; episode-based t intervals), rank history from raw scores, paper-ledger records (read-only), Soul study rows; what happened next. Deliberately no profit-confidence score. Read-only; writes only <root>\research2\analyzer\ |
| tests\test_stock_analyzer.py | - | by hand (inputs, resolve, locks, ETF names, outcomes, known flag incl. execution-model exit days, episode CR1 interval, ranks, NIFTY, beta, ledger layouts and dates, shift test, ticks); PLANTED setups -> similar days find them, NULL -> no edge; PLANTED volatility spells -> 'works', 80 NULL stocks -> false calls at the promised 5% (4/80, 3/80); FUTURE PERTURBATION (every future field and 3-minute bar regenerated, locked open on the date, next-day ledger record) + planted leaks caught; TRUNCATION SWEEP at 25 dates (full data = data cut at the date) + planted leaks caught; pages and ASCII console; main() end to end with stand-ins. Independent review twice (11 findings + 5, all fixed). Verified on pandas 3.0 and 2.2 (with and without scipy) |
| BIGMOVE_DECLARATION.json | bigmove_v1 (1d330078e15751b7) | BIGMOVE intraday breakout family, declared 8 Oct 2026 and amended five times before any real-data run (last 10 Oct: q - a ranked cell's lead over buying everything must also survive the search, max-t p below 0.025 over the side's 36 ranked cells, because in 20 synthetic no-skill markets a ranked pick reached PROMISING / CHAMPION in 7, now 1; r - reporting only): stocks-in-play opening-range breakout ranked by relative opening volume (RV), the similar-day memory of next-session range (MFE) or both (RVxMFE), plus PLAIN (every candidate); long and short books judged separately; F1 grid (84 cells), F2 gates (NIFTY, sector, RS, NIFTY+RS; a gate that cannot judge lets the order through), F3 exits (VWAP trail, breakeven), F4 NIFTY noise-boundary sleeve; a ranked cell must beat the EXPOSURE-MATCHED PLAIN book, judged against the search; discovery 2021-10 to 2024 selects, confirmation 2025-01 to 2026-07 used once, after-CAS reported; current Zerodha costs + assumed slippage, stressed 1.5x / 2x; DSR, Reality Check, BH per family; coverage counted in days (90% rule) |
| bigmove_study.py | v1.1 | v1.1: a ranked cell's excess judged against the search (max-t p, amendment q; shown as 'p (search)'); fill audit (trades stopped inside their entry bar, trades with a missing bar inside them); unreadable files and triggered trades without an exit price counted; usable share by month (universe_by_month.csv) and by stock; provenance in summary.json (code / declaration / data hashes, config, seeds, library versions, warnings) and outputs.sha256; a repeat run of the declaration is stamped RERUN (report, console, ledger); the Reality Check gives n/a, not a false p = 1/(B+1), when no book differs from its base. Runs bigmove_v1: --coverage-only (liquid stock-days with a 3-minute session, missing_liquid.txt, coverage_by_stock.csv), then pass 0 (sector paths), pass 1 (per stock: reconciled usable sessions, RV, memory, every variant's fills), pass 2 (books, matched benchmarks, statistics, verdicts, combined L+S book, regimes). Reads NSE sector and ETF lists from <root>\sectors\ if present. Writes only <root>\research2\bigmove\ (BM_<date>_<n>\: report.md, cells, selected, gates, exits, comparison, sleeve, thin days, regimes, daily returns, trades, coverage, summary, outputs.sha256; universe_by_month.csv beside them) and appends one line to <root>\panel\research_ledger.jsonl |
| tests\test_bigmove_study.py | - | by hand (costs to the rupee, fills incl. gaps and same-bar stops, VWAP trail, breakeven, gate wiring long and short, pass-through, matched benchmark and its trap, memory spacing / minimum, usable sessions, UTC slotting, verdicts incl. the search check, DSR, BH, Reality Check, max-t p by hand in plain loops, audit flags); STATISTICS BY SIMULATION (bootstrap coverage 93.0% and one-sided p < 0.05 in 6.8% on autocorrelated fat-tailed nulls; Reality Check false alarms 9.0% at 5%; DSR 0.0% on noise, 90.3% power; SELECTION: the best of 36 no-skill rankings passes on its own excess lower bound in 28.5%, against the search in 3.0%, a real ranking still in 99.5%); the synthetic world (reproducible from its seed; switching one mechanism leaves every other random number identical); FILL FAIRNESS on 200,000 sessions of a continuous driftless path; PLANTED worlds (stocks in play, state days, payoff-needs-both, short-only, NIFTY / sector trend with hidden openings, NIFTY and sectors disagreeing; flipping every confirmation outcome leaves selection unchanged; a ranked cell's variants must beat the same variant on matched PLAIN) and NULL worlds (no edge; stock-only trends with half the stocks unmapped; thin counter-trend days where full PLAIN would crown a random ranking); LOOK-AHEAD sweep (12 days x 2 ranges) with planted leaks caught; main() end to end (days-based coverage, refusals, ETFs by ISIN and by list, partial files, zone-aware files, an unreadable file, ledger, provenance and output hashes, universe by month, RERUN stamp). Verified on pandas 3.0 and 2.2 |
| tests\bigmove_world.py | - | the synthetic NSE-like market for those tests: bars of a continuous path (Brownian-bridge highs and lows, so a fill at a level is fair), with switches that plant one effect at a time; every mechanism draws from its own random stream (switching one on leaves every other draw identical); sectors can trend with or against NIFTY |
| tests\selection_worlds.py | - | optional, slow (about 15 minutes): reproduces amendment q's numbers - ranked PROMISING / CHAMPION picks in 20 no-skill markets before and after the search check, and the planted markets' verdicts |

## D. Declarations (fixed before their runs)
| file | fingerprint | covers |
|---|---|---|
| EXPERIMENT_OC_FAMILY.json | 1f5c13384e36e759 | the open-to-close target family |
| STAGE_D_DECLARATION.json | dcfab6eccc05fcb9 | engine D's model and gate |
| FORENSICS_DECLARATION.json | 410278b832f2aa90 | honest-exit rules |
| STAGE_D2_DECLARATION.json | 1de7aa2028f1c21a | nested selection |
| STAGE_C_DECLARATION.json | e945f62dd321625c | the 123 C features |
| STAGE_DX_DECLARATION.json | 8a0cf3feaf3b5979 | C-only arm, ensemble, closure rule |
| EXECUTION_DECLARATION.json | 5ba73cc0687eb482 | execution backtest |
| PATHS_DECLARATION.json | f14e6e968b12a73b | path study |
| PAPER_DECLARATION.json | f75aa3de0dc4278f | the paper test (amended before day 1: Soul C profile) |
| SOUL_META_DECLARATION.json | 2cb4d8a4b416fd7c | the Soul re-ranker (amended before any real-data run: C profile and tug inputs; 25% minimum order, approved 1 Oct 2026) |

## E. Tests (`open_close\tests\`) - each prints VERIFIED
test_panel_oc, test_stage_b, test_stage_d, test_stage_d_forensics, test_stage_d2,
test_compare_d, test_stage_c_features, test_stage_c_screen_dc, test_stage_dx,
test_stage_e, test_stage_e_paths, test_paper (production models and library pinning, Soul
point in time, watchlist, ledger and universe integrity, settlement and its benchmark,
tracker and log, missing days), test_preflight (wiring planted vs absent, tampering, missing setup).

## F. Main folder - unchanged, not in this bundle
Daily_cache_v27.py (history anchor 2015-01-01 - never change), run_daily.py,
data_quality.py, features_daily.py, daily_report.py, panel_build.py (v31, the old
panel), research_common.py (main copy), tradability_audit.py, requirements.txt,
setup_once.bat, env_daily.bat and watchlist.txt (yours).

## G. Retired - keep the files, never schedule them
signal_engine.py, meta_label_test.py, soul.py, soul_v3.py, soul_test.py,
challenger_test.py, monthly_retrain.bat (disable its task: nothing is retrained
during the paper test), open_close\paper_daily.bat (replaced by daily_run.bat v5 -
delete it if you copied it).

## H. Note on an interrupted attempt
An interrupted attempt (1 Oct 2026) changed the re-ranker declaration, preflight and the simulator without approval.
All were restored to the approved versions, the code was reviewed line by line, and the one change it introduced
(a 25% minimum order) was approved explicitly before any real-data run. soul_meta.py ships only after VERIFIED.
