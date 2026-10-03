# Roadmap

Each phase is one or more PRs, merged only with CI green. Update the status column as work
lands. The target state of every item is described in [architecture.md](architecture.md).

| # | Phase | Delivers | Status |
|---|---|---|---|
| — | Harness | Layered library, tests, golden datasets, baseline, CI, auto-merge | done |
| — | Decisions | Docs, ADRs 0004–0017, workflows (skills) | done |
| 0 | Restructure | Target layout; instrument ids + multipliers; storage-backed backtests and the four data layers; source interface; configs, selections and users; jobs; uv workspace. Baseline identical throughout. | done |
| 1 | Ingestion: universe, reference, bars, events | **Done (1.1–1.7):** phase 0 follow-ups F1–F5; Nasdaq earnings → `events/earnings` (nightly 60-day calendar snapshot, past-date backfill); Massive daily bars (unadjusted) + splits/dividends with read-time adjustment, resumable backfill; FIGI / CIK / vendor security types from Massive, `instruments/symbol_history` and `ticker_changed` events; universe builder from Nasdaq Trader + SPY holdings (stocks, ADRs, ETFs incl. leveraged/inverse) driven by `config/site/universe.toml`, leveraged-ETF overrides + review file, `events/reference_change` and `events/index_change`; `config/site/sources.toml`; nightly data-quality checks; local launchd scheduler (`algotrade-ingest schedule`); company details from SEC EDGAR → `instruments/company` (SIC, sector/industry, state, fiscal year end; incremental, `instrument.sector` in selections); **1.8** FIGI-based `instrument_id` (`EQ:<FIGI>`, symbol-id fallback), one `SymbolResolver` for every ticker → id, `instruments/id_map` + `id_changed` events, `algotrade-ingest migrate-ids` (ADR 0018). **Owner action:** after the backfill, rebuild the universe with the Massive key set (`universe-build`), then `migrate-ids --dry-run` and `migrate-ids` | **done** |
| 2a | Options liquidity slice | Cboe chains, `option_liquidity@v1`, `short_premium_liquidity`, screening engine with coverage audit, legacy CSV exports | done |
| 2b | Quant + rollups | `quant/` (Black-Scholes, our own IV and Greeks, realised-vol estimators); rollups `price_stats@v1`, `iv_history@v1` (from nightly `iv30`), `earnings@v1`, `liquidity_class@v1` (+ `config/site/rollups.toml`), `fundamentals@v1`; `rebalance_selection` for backtests | |
| 3 | Screeners | VRP scanner ([spec](screeners/vrp-scanner.md)) with its 8–15 delta second stage; cash-secured puts / covered calls, IV rank, unusual activity, credit spreads; a screener results baseline | |
| 4 | API | FastAPI app over `services/`; authenticated users mapped to `user_id` with per-user access enforced in services; jobs endpoints; DB-backed `ConfigStore`; TypeScript client generated from the API schema | |
| 5a | Design system | Tokens → **owner approves mockups** → components + catalogue → lint enforcement | |
| 5b | Web app | Screener list, results table, contract detail, data freshness; L4 watchlists and preferences | |
| 6 | Expansion | Backtests from the UI on a queue-backed job runner; on-request pulls; futures (IBKR); intraday bars + `rollups/daily/*`; S3 storage backend and hosting; screener outcome tracking | |

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
