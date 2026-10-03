# Roadmap

Each phase is one or more PRs, merged only with CI green. Update the status column as work
lands.

| # | Phase | Delivers | Status |
|---|---|---|---|
| — | Harness | Layered library, tests, golden datasets, baseline, CI | done |
| — | Decisions | Docs, ADRs 0004–0013, workflows | done |
| 2a | Options liquidity slice | `storage/` (contract-tested local + memory backends), `apps/ingestion` (Cboe source, universe import, resumable chain job, features job, nightly pipeline, CLI), `option_liquidity@v1`, screener contract + `short_premium_liquidity`, screening engine with coverage audit, legacy CSV exports | done |
| 0 | Restructure | `apps/{ingestion,backtest,api,web}` + shared libraries in a uv workspace; `storage/` interfaces with readers and writers and a `parquet_local` backend + contract tests; `instrument_id` and multiplier in core; `services/jobs` with a local runner; source interface; new import-linter contracts. **Baseline must stay identical.** | next |
| 1 | Ingestion: universe + bars | Nasdaq Trader + SPY holdings universe snapshots, leveraged-ETF overrides, Massive daily bars, synthetic source, local nightly scheduler, data-quality checks | |
| 2b | VRP scanner | `docs/screeners/vrp-scanner.md`: daily bars (Massive) for HV20/HV30, 52-week range, moving averages and returns; `iv30` history from nightly Cboe snapshots (IV rank/percentile); earnings-calendar source; second-stage 8–15 delta put screener; `quant/` (our own IV and Greeks) | next |
| 3 | Screening | `strategies/screeners/` (cash-secured puts / covered calls, IV rank, unusual activity, credit spreads), `engines/screening/`, results store, screener baseline | |
| 4 | API | `services/` use cases, FastAPI read endpoints, jobs endpoints, TypeScript client generated from the API schema | |
| 5a | Design system | Tokens → **owner approves mockups** → components + catalogue → lint enforcement | |
| 5b | Web app | Screener list, results table, contract detail, data freshness | |
| 6 | Expansion | Backtests from the UI, on-request pulls, futures (IBKR), intraday bars, screener outcome tracking | |

## Open decisions

| Decision | Options | Default if not decided |
|---|---|---|
| Earnings-calendar source | Nasdaq (unofficial), Finnhub free tier, paid | needed for phase 2b |
| Cboe terms | Confirm acceptable use of the delayed feed | owner to confirm |
| Production job queue | Redis/RQ, Postgres-backed, cloud queue | Local runner until hosting |
| Hosting target | VM + docker-compose, a container platform | Local only |
