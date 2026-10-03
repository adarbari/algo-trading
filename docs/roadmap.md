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
| 2b | Quant + rollups | **Done (2b.1):** `quant/` (Black-Scholes price + Greeks, IV solver with failure codes, close-to-close / Parkinson / Garman-Klass / Yang-Zhang realised vol, rate conventions; ADR 0021) and U.S. Treasury rates (`rates/treasury`, `rates` task in nightly, `data.rates.curve`). **Owner action:** `algotrade-ingest rates --from 2024-01-01 --to <last session>` once. Next: rollups `price_stats@v1`, `iv_history@v1` (from nightly `iv30`), `earnings@v1`, `liquidity_class@v1` (+ `config/site/rollups.toml`), `fundamentals@v1`; `rebalance_selection` for backtests | 2b.1 done |
| 3 | Screeners | VRP scanner ([spec](screeners/vrp-scanner.md)) with its 8–15 delta second stage; cash-secured puts / covered calls, IV rank, unusual activity, credit spreads; a screener results baseline | |
| 4 | API | FastAPI app over `services/`; authenticated users mapped to `user_id` with per-user access enforced in services; jobs endpoints; DB-backed `ConfigStore`; TypeScript client generated from the API schema | |
| 5a | Design system | Tokens → **owner approves mockups** → components + catalogue → lint enforcement | |
| 5b | Web app | Screener list, results table, contract detail, data freshness; L4 watchlists and preferences | |
| 6 | Expansion | Backtests from the UI on a queue-backed job runner; on-request pulls; futures (IBKR); intraday bars + `rollups/daily/*`; S3 storage backend and hosting; screener outcome tracking | |

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

## Phase 0 follow-ups (the architecture is the target; these close the gaps)

| # | Item | Lands in |
|---|---|---|
| F1 | Configured backtests save results (`results/backtest_equity`, `results/backtest_fills`) and record dataset versions on the run | **done** (1.1) |
| F2 | `ALGOTRADE_USER` env var as the default for `--user` | **done** (1.1) |
| F3 | A single `InstrumentView` reader (reference + selected rollups, as of a date) | **done** (1.1) |
| F4 | Job idempotency keyed by (kind, config hash, session), so editing a config and resubmitting runs again | **done** (1.1) |
| F5 | Reject secret-like keys in config files | **done** (1.1) |
| F6 | DuckDB as the query engine and catalog (storage is Parquet read with pyarrow today) | when queries need it |
| F7 | `rebalance_selection` (re-evaluate a backtest's selection at an interval) | phase 2b |

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
