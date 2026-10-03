# Roadmap

Each phase is one or more PRs, merged only with CI green. Update the status column as work
lands. The target state of every item is described in [architecture.md](architecture.md).

| # | Phase | Delivers | Status |
|---|---|---|---|
| — | Harness | Layered library, tests, golden datasets, baseline, CI, auto-merge | done |
| — | Decisions | Docs, ADRs 0004–0017, workflows (skills) | done |
| 0 | Restructure | Target layout; instrument ids + multipliers; storage-backed backtests and the four data layers; source interface; configs, selections and users; jobs; uv workspace. Baseline identical throughout. | done |
| 1 | Ingestion: universe, reference, bars, events | **Done (1.1–1.7):** phase 0 follow-ups F1–F5; Nasdaq earnings → `events/earnings` (nightly 60-day calendar snapshot, past-date backfill); Massive daily bars (unadjusted) + splits/dividends with read-time adjustment, resumable backfill; FIGI / CIK / vendor security types from Massive, `instruments/symbol_history` and `ticker_changed` events; universe builder from Nasdaq Trader + SPY holdings (stocks, ADRs, ETFs incl. leveraged/inverse) driven by `config/site/universe.toml`, leveraged-ETF overrides + review file (leverage parsed from fund names incl. ProShares Ultra / UltraShort / UltraPro conventions, bond / buffer / option-income false positives excluded: review file 958 → 21 names), `events/reference_change` and `events/index_change`; `config/site/sources.toml`; nightly data-quality checks; local launchd scheduler (`algotrade-ingest schedule`); company details from SEC EDGAR → `instruments/company` (SIC, sector/industry, state, fiscal year end; incremental, `instrument.sector` in selections); **1.8** FIGI-based `instrument_id` (`EQ:<FIGI>`, symbol-id fallback), one `SymbolResolver` for every ticker → id, `instruments/id_map` + `id_changed` events, `algotrade-ingest migrate-ids` (ADR 0018). **Owner action:** after the backfill, rebuild the universe with the Massive key set (`universe-build`), then `migrate-ids --dry-run` and `migrate-ids`; curate the ~21 ETFs left in the leverage review file into `config/site/overrides/leveraged_etfs.csv` | **done** |
| 2a | Options liquidity slice | Cboe chains, `option_liquidity@v1`, `short_premium_liquidity`, screening engine with coverage audit, legacy CSV exports | done |
| 2b | Quant + rollups | **Done (2b.1):** `quant/` (Black-Scholes price + Greeks, IV solver with failure codes, close-to-close / Parkinson / Garman-Klass / Yang-Zhang realised vol, rate conventions; ADR 0021) and U.S. Treasury rates (`rates/treasury`, `rates` task in nightly, `data.rates.curve`). **Owner action:** `algotrade-ingest rates --from 2024-01-01 --to <last session>` once. **Done (2b.2):** rollup framework (`features/framework/`: `Rollup` declaration with inputs + lookback, params from `config/site/rollups.toml` through the one settings loader, typed columns, inputs read through `algotrade.data`, point in time per session, chunked backfills), the `rollups` task (replaces `features`, kept as an alias; `--from/--to`, `--only`; nightly for every session), `option_liquidity@v1` moved onto it, `price_stats@v1` (split-adjusted as of each session: SMAs, returns, 52-week range, HV20/30, Yang-Zhang HV20, ADV) and `earnings@v1` (next / last date as known on the session, report time, sessions to it); rollup columns selectable as `rollup.<name>@v<N>.<column>`. **Owner action:** `algotrade-ingest rollups --from 2024-10-03 --to <last session>` once (~3 min). **Done (2b.3):** rollups read rollups (inputs name `rollups/instrument/<name>@v<N>`; dependency order in the registry, cycles fail at import; dependents of a failed rollup are skipped), `dividends@v1` (trailing-12-month cash dividends split-adjusted to the session, yield), `iv30@v1` (our own 30-day ATM IV beside Cboe's, with status codes; ADR 0021 "IV30"), `iv_history@v1` (IV rank / percentile over 252 sessions, PROVISIONAL after 60, IV - HV30), `liquidity_class@v1` (HIGH / MEDIUM / LOW / UNKNOWN from `rollups.toml` thresholds, `rule_hash`). **Owner action:** `algotrade-ingest rollups --from 2025-10-01 --to <last session> --only dividends@v1,liquidity_class@v1` once (iv30 / iv_history start with the first stored chain). **Done (2b.4):** shares outstanding from SEC company facts (`sec_company_facts` source: cover-page `dei` count, weighted average basic as fallback; `instruments/shares`, incremental `shares` task after company details in nightly, refreshes spread over 30 days by CIK for both SEC tasks) and `fundamentals@v1` (`shares_outstanding` point in time by filing date and split-adjusted, `market_cap` = shares x close, `market_cap_status` OK / NO_SHARES / STALE / NO_PRICE); `rollup.fundamentals@v1.market_cap` selectable. **Owner action:** `algotrade-ingest shares` once (~6k CIKs, ~30-40 min), then `algotrade-ingest rollups --from 2024-10-03 --to <last session> --only fundamentals@v1`. Deferred: class-specific share counts (companyfacts has none; BRK.A / BRK.B are STALE). **Done (2b.5):** `[backtest] rebalance_selection` (`none` / `monthly` / `weekly` / `<N>d`) + `selection_lag_sessions` (default 1): the selection is re-evaluated point in time on each rebalance session, the set takes effect `lag` bars later, removed instruments are closed at the next open, prices load once for the union, and the run records each evaluation (added / removed, funnel, survivorship flag); see configuration.md "Rebalancing selections". Phase 2b complete | **done** (2b.1–2b.5) |
| 3 | Screeners | VRP scanner ([spec](screeners/vrp-scanner.md)) with its 8–15 delta second stage; cash-secured puts / covered calls, IV rank, unusual activity, credit spreads; a screener results baseline | |
| 4 | API | FastAPI app over `services/`; authenticated users mapped to `user_id` with per-user access enforced in services; jobs endpoints; DB-backed `ConfigStore`; TypeScript client generated from the API schema | |
| 5a | Design system | Tokens → **owner approves mockups** → components + catalogue → lint enforcement | |
| 5b | Web app | Screener list, results table, contract detail, data freshness; L4 watchlists and preferences | |
| 6 | Expansion | Backtests from the UI on a queue-backed job runner; on-request pulls; futures (IBKR); intraday bars + `rollups/daily/*`; S3 storage backend and hosting; screener outcome tracking | |

## Live verification (LV): our data against IBKR, read-only (ADR 0026)

| # | Delivers | Status |
|---|---|---|
| LV1 | IB Gateway session source (`sources/vendors/ibkr/`, read-only facade over `ib_async`; session sources in the framework; IBKR pacing), the `verify` task (`tasks/verification/`: sample, checks with the reconciliation tolerances, `verification/ibkr`), nightly step (SKIPPED when the gateway is down), quality check `verification`, email section, read-only fitness test + import contract. **Owner action:** set up IB Gateway (README, "Live verification") and set `[ibkr] enabled = true` | **done** |
| LV2 | A trend of verification failures per check in the email; IBKR as the source of `option_symbols` IV history once a subscription is in place | later |

## Restructure (R): one owner per responsibility (ADR 0019)

Each PR moved code to its target owner in `architecture/ownership.toml`, shrank
`architecture/known_violations.toml` and enabled its `pending_contract`s in `pyproject.toml`.
Baseline identical throughout. **The track is complete:** the ratchet is empty, every planned
contract is enforced, and a fitness test keeps it so (new exceptions need an ADR).

| # | Delivers | Status |
|---|---|---|
| R1 | Ownership registry, shrink-only ratchets (`make ownership`, `make dupes`), fitness tests, ADR 0019 | **done** |
| R2 | `algotrade/data/` read layer + one snapshot rule (`reference`, `prices`, `events`, `chains`); fixes backtests before the first snapshot (flagged `survivorship_bias`) and reads events by event date; backtests pin `as_of` = launch time (ADR 0007 amended); contracts R1, R2 | **done** |
| R3 | `IngestRun` (the ingest loop, written once) + task registry (`jobs/` → `tasks/`); CLI (`run <task>` + the named commands) and nightly dispatch through the registry; settings defaults applied once; `cboe.workers` honoured | **done** |
| R4 | Source registry from `sources.toml` + shared cross-process rate limiter (retry cap, circuit breaker) + run lock (`--wait`, exit 3, job recovery) + index lock; vendor helpers out of tasks; contract R3 | **done** |
| R5 | Nightly workflow (`workflows/`): isolated steps with status + duration, hard dependencies vs data preconditions, quality + purge always last, COMPLETE / PARTIAL / FAILED rule in one place; exchange calendar `core/time/calendar.py` (NYSE holidays, early closes, `last_closed_session`); catch-up of missed sessions (capped, chains latest only); screens submitted as `screen` jobs (`universe_pre_snapshot` in the audit); failure notification + `var/logs/nightly-latest.json` (`config/site/nightly.toml`); launchd `RunAtLoad` false; apps run jobs through `services.jobs.run_job`, contract R5 | **done** |
| R6 | Typed site settings: one loader (`config/site/settings.py`) for every `config/site/*.toml`, frozen dataclasses, unknown keys and bad values fail with their path; environment read only in `config/env.py` (the storage factory takes the URL); screens and backtests open / close run records through `storage.runs` (`start_run`, `RunRecord.finish`); golden CSVs are a registered fixture source; OHLCV checks in `core/validation/bars.py`, contract R4 in full; typed table schemas (declared column types, cast on write, `schema_version` stamped, older files cast on read, ~64k-row groups + page index); known violations 11 → 0, no pending contracts | **done** |

## Feature store (FS): features as named, documented columns (ADR 0023)

Pure refactors for stored data unless a step says otherwise (FS3 re-versions four groups). The
catalogue of every feature is [data/features.md](data/features.md).

| # | Delivers | Status |
|---|---|---|
| FS1 | Per-feature definitions (`Feature`: entity, kind, dtype, unit, description, null meaning, valid range, categories, inputs, version) declared in feature groups (`FeatureGroup`, the eight rollups, byte-identical output); one registry (`GROUPS`, `FEATURES`, `feature(name)` lookups); generated catalogue `docs/data/features.md` (`make features-doc`) with fitness tests | **done** |
| FS2 | Inputs through `data/`: features ask `data.feature_inputs` by table name (each table's read in its owner; generic stored-group reader); `features/` never imports storage or a domain reader (import-linter); ownership `feature-input-loading` | **done** |
| FS3 | Expression features, virtual by default (owner decisions: TOML definitions, `materialise = true` opt-in, per-feature versions, float32 when re-versioning): a typed formula language (`features/expressions/`, never Python `eval`), `config/site/features/*.toml` through the one settings loader, `feature.<name>` selection fields and `FeatureView` columns computed on read from only the stored columns needed, materialised expressions stored by the `rollups` task (`div_yield@v1`, read by `iv30@v1`); liquidity class, `div_yield`, `market_cap`, `pct_from_high/low_52w`, `iv_hv_spread/ratio` moved to expressions, new `near_52w`; `price_stats@v2`, `dividends@v2`, `fundamentals@v2`, `iv_history@v2` with float32 columns (`liquidity_class@v1` dropped); `algotrade-ingest retire-features`. Exact on real data (116k rows, 10 sessions: every class and tier identical; numbers within float32 rounding). **Owner action:** `algotrade-ingest rollups --from 2024-10-03 --to <last session>` (backfills the v2 groups and `div_yield@v1`), then `retire-features --group <name>@v1 --dry-run` and without `--dry-run` for `price_stats`, `dividends`, `fundamentals`, `iv_history`, `liquidity_class` | **done** |
| FS4 | User expression features (L4, `config/users/<id>/features/*.toml`): the site schema through the one loader, always virtual (`materialise` rejected); `feature.<name>` resolves user-first in the user's catalogue, never shadowing a site feature; selections / configs of that user may name them and the definitions they read join the config hash; `GET /features` returns the caller's catalogue with `scope` / `owner`; Explore tickers / compare accept them; `algotrade-backtest config validate-features` | **done** |
| FS5 | Features by name for group features: unique group-independent names, copies become references | next |
| FS6 | `cross_section` features (ranks, z-scores within the universe or a sector) | later |
| FS7 | Feature quality: null rates and `valid_range` checks in nightly (out-of-range values reported, never clipped) | later |
| FS8 | New grains (`market`, `contract`, `sector`) when a feature needs one | later |

## Phase 0 follow-ups (the architecture is the target; these close the gaps)

| # | Item | Lands in |
|---|---|---|
| F1 | Configured backtests save results (`results/backtest_equity`, `results/backtest_fills`) and record dataset versions on the run | **done** (1.1) |
| F2 | `ALGOTRADE_USER` env var as the default for `--user` | **done** (1.1) |
| F3 | A single `InstrumentView` reader (reference + selected rollups, as of a date) | **done** (1.1) |
| F4 | Job idempotency keyed by (kind, config hash, session), so editing a config and resubmitting runs again | **done** (1.1) |
| F5 | Reject secret-like keys in config files | **done** (1.1) |
| F6 | DuckDB as the query engine and catalog (storage is Parquet read with pyarrow today) | when queries need it |
| F7 | `rebalance_selection` (re-evaluate a backtest's selection at an interval) | **done** (2b.5) |

## Fixes

| Date | Fix | Owner action |
|---|---|---|
| 2026-10-03 | **Event runs merge.** A later window run in the same session (nightly corporate actions, -7..+30 days) hid the 26-month backfill in `events/dividend` / `events/split` / `events/earnings` (AAPL / KO showed no trailing dividends), because reads picked one run per partition. Tables now declare how runs combine (`TableSpec.runs`: `snapshot` or `merge`); `events/*` merge (union, latest run per key); `migrate_ids` rewrites merge partitions as restating runs so old ids stay gone (ADR 0007 "How runs combine", [storage.md](data/storage.md#how-runs-combine)) | re-run `algotrade-ingest migrate-ids` once a full `instruments/id_map` is stored (see the PR), to restate the 2026-10-02 event partitions without their old-id rows |
| 2026-10-03 | **Universe re-runs keep cumulative state; `id_map` merges.** A same-session re-run of `universe_build` started from the latest snapshot *before* the session, i.e. from nothing on the first session: the 09:30Z nightly re-run of 2026-10-02 wrote an `instruments/id_map` run of 3 upgrades that hid the 10,817 recorded at 05:05Z, so `migrate-ids` mapped 3 ids and 112,928 symbol-id dividend rows (plus splits / earnings) stayed. The build now starts ids, `first_seen`, delistings, `symbol_history` and `id_map` from the latest snapshot known (the session's own earlier run first); events diff against the previous session. `instruments/id_map` (key `old_id` + `new_id`) and `instruments/symbol_history` (key `figi` + `symbol` + `valid_from`) are `merge` tables (`TableSpec.key`), so a partial run can never hide history (ADR 0018 note, [instruments.md](data/instruments.md#identifiers-and-vendor-types-implemented-phase-15)) | `algotrade-ingest universe-build --date 2026-10-02`, then `migrate-ids --dry-run` (expect `mapped_ids` 10,820), `migrate-ids`, `migrate-ids --dry-run` (no tables) |
| 2026-10-03 | **Storage hygiene.** Raw retention is per source: a `sources.toml` vendor section may set `raw_retention_days` (over the global 90); `[sec_edgar]` keeps 7 days (submissions, company tickers, company facts: ~30 MB a night, plus ~0.8 GB from the first full load), so the raw area settles at ~6 GB, Cboe-dominated. `purge-raw` maps raw sources to sections through the source registry and reports removals per source. A run's staging is dropped as soon as it finishes with nothing to retry (COMPLETE, or PARTIAL without FETCH_ERROR items); runs with retryable items and FAILED runs keep it for the resume ([storage.md](data/storage.md#retention), [nightly-footprint.md](data/nightly-footprint.md)) | none: the next nightly applies it; `algotrade-ingest purge-raw` applies SEC retention at once |

## Open decisions

| Decision | Options | Status |
|---|---|---|
| Earnings-calendar source | Nasdaq public calendar (free, no key, all US, tested) | **decided: Nasdaq**; cross-check source optional |
| Massive API key | Free tier account | **done** (in `.env`; rotate it, it was shared in chat) |
| SEC EDGAR contact | A contact email in the user agent (SEC policy) | **done** (`ALGOTRADE_SEC_CONTACT` in `.env`) |
| FIGI-based `instrument_id` | Keep symbol ids, or migrate to FIGI ids | **decided: FIGI ids** (ADR 0018); owner runs `migrate-ids` on the local store |
| Cboe terms | Confirm acceptable use of the delayed feed | owner to confirm |
| User identity scheme | Labels now; auth provider in phase 4 | decide in phase 4 |
| Production job queue | Redis/RQ, Postgres-backed, cloud queue | local runner until hosting |
| Hosting target | VM + docker-compose, a container platform | local only |
