# Architecture

This document has two parts:

1. **Target architecture**: where the system is going. All new work must fit it.
2. **Current code layout**: what exists today, and the rules enforced on it right now.

The reasons behind each decision are in [docs/adr/](adr/README.md). The order of work is
in [docs/roadmap.md](roadmap.md).

---

## 1. Target architecture

### Apps and backend

```
 APPS (entry points: wiring, config, scheduling. Thin, little logic.)

   apps/ingestion        apps/backtest          apps/api            apps/web
   scheduled pipeline    CLI / notebooks        FastAPI server      React + design system
   pull → validate →         │                      │                  │
   normalise → features      │ in-process           │◀──── HTTP ───────┘
   → run screeners           │                      │
        │ WRITES             │ READS                │ READS (+ submits jobs)
        ▼                    ▼                      ▼
 ┌────────────────────────── storage (the data contract) ──────────────────────────┐
 │ reference · events · bars(interval) · chains · features · universe · results     │
 └───────────────────────────────────────────────────────────────────────────────────┘

 SHARED LIBRARIES (src/algotrade/), layered top to bottom:
   services/    use cases + the jobs model (run_backtest, run_screen, ingest, ...)
   engines/     backtest/ (loop, simulated fills, portfolio, risk)   screening/
   strategies/  trading/ (backtests)   screeners/ (screening). Pure: FeatureView in, decisions out.
   features/    versioned feature definitions, pipeline, point-in-time FeatureView
   storage/     repository interfaces per data grain · readers · writers · backends/
   quant/       pricing maths, Greeks, implied volatility, roll maths
   core/        instruments, value objects, calendars, errors, time
```

### Non-negotiable rules

| # | Rule | ADR |
|---|---|---|
| 1 | Apps are separate processes in one repo. They **never import each other**; they share only libraries and storage. | [0004](adr/0004-apps-and-shared-libraries.md) |
| 2 | **Only `apps/ingestion` writes** market and feature data. Everyone else reads. Vendor SDKs and credentials live only in ingestion. | [0005](adr/0005-ingestion-is-the-only-writer.md) |
| 3 | Storage is organised by **data grain** behind repository interfaces. Parquet + DuckDB on local disk for now; backends can be swapped via config. | [0006](adr/0006-storage-grains-and-adapters.md) |
| 4 | All market and feature data is **point-in-time**: every row records when it happened *and* when we learned it. | [0007](adr/0007-point-in-time-data.md) |
| 5 | **Backtests only read from stores.** They never call a vendor. Missing data is an error that says which ingestion job to run. | [0008](adr/0008-backtests-read-only-from-stores.md) |
| 6 | Everything is keyed by a generic **instrument** (stock, ETF, index, option, future, …), so adding futures needs no redesign. | [0009](adr/0009-generic-instrument-model.md) |
| 7 | Long-running work (backtests from the UI, on-request pulls, nightly runs) is a **job** submitted through `services/`. | [0010](adr/0010-jobs-model.md) |
| 8 | Strategies and screeners are **pure**: they see a `FeatureView` (or `MarketView`) only, never storage or vendors. | [0001](adr/0001-layered-architecture.md) |
| 9 | Data comes from **several sources, free first**, each behind the same source interface. | [0012](adr/0012-data-vendors.md) |
| 10 | The universe is **S&P 500 constituents + all Nasdaq-listed stocks + all ETFs (including leveraged and inverse)**, saved as a dated snapshot each day. | [0013](adr/0013-universe.md) |
| 11 | The UI is built **design-system first**: screens use only design-system components. A missing component is added to the design system in a generic form first. | [0011](adr/0011-design-system-first-ui.md) |
| 12 | Local first, hostable later: config from env vars, storage behind URLs, the API serves the web build. | [0004](adr/0004-apps-and-shared-libraries.md) |

Detailed specs:
[storage](data/storage.md) · [instruments & universe](data/instruments.md) ·
[vendors](data/vendors.md) · [design system](ui/design-system.md)

### Data flow

```
nightly (and later: intraday or on request, via a job)
  ingestion: universe snapshot → pull per source → raw/ (as received, kept forever)
           → validate + normalise → reference / events / bars / chains
           → compute features (versioned) → run all screeners → results/
on request
  api ──► services ──► reads results / features             (web UI)
  api ──► services.jobs.submit(backtest) ──► engines.backtest ──► results/
  backtest CLI ──► services ──► engines.backtest (reads stores only)
```

---

## 2. Current code layout (enforced today)

Phase 0 is in progress (see [docs/design/phase-0.md](design/phase-0.md)). The library
already uses the target layers. Dependencies point **downwards only**, and siblings on the
same row may not import each other. `import-linter` enforces this (`[tool.importlinter]` in
`pyproject.toml`).

```
apps/ingestion (algotrade_ingestion) · apps/backtest (algotrade_backtest)   never import each other
        │ import the library, never the reverse
        ▼
     services/           use cases: screening, evaluation, views, exports
        │
     engines/            backtest/ · screening/   (independent of each other)
        │
 strategies/ (trading · screeners) · features/ · analytics/
        │
     storage/
        │
      core/
```

Extra contracts:
- strategies and screeners see only `core`
- feature definitions never touch storage
- only `apps/ingestion` may import `storage.writers`
- inside `engines/backtest`, risk (`limits`, `sizing`), execution (`simulated`) and accounting (`portfolio`) stay independent

| Package | Responsibility | May import |
|---|---|---|
| `core/` | Value objects (`Order`, `Fill`, `PriceSeries`), `MarketView`, `FeatureView`, instruments, options, errors, time. | numpy only |
| `storage/` | Data contract: schemas, a `Protocol` per store, reader / writer / result-writer facades, `local` (Parquet) and `memory` backends. | core, pandas, pyarrow |
| `strategies/` → `trading/` | Backtest strategies: `MarketView` in, target weights out, plus their registry. | core |
| `strategies/` → `screeners/` | Screener contract, shared `Decision` categories, `short_premium_liquidity`. | core |
| `features/` | Pure, versioned rollup definitions (`option_liquidity@v1`) and their registry. | core |
| `analytics/` | Metrics and report formatting from equity curves + fills. | core |
| `engines/` | `backtest/`: the bar loop, risk limits, sizing, simulated broker, costs, portfolio. `screening/`: runs a screener and audits coverage. | strategies, analytics, core |
| `services/` | Use cases: universe + `FeatureView` loading, `market_data` (stored bars → aligned series), golden `datasets`, screening runs, legacy exports, `evaluation/` (strategy × golden dataset vs baseline). | everything below except `storage.writers` |
| `apps/ingestion` | Sources (Cboe, HTTP with retries, synthetic/golden), jobs (universe, option chains, features, golden load), nightly pipeline, `algotrade-ingest`. | library |
| `apps/backtest` | `algotrade-backtest` CLI (`algotrade` alias): datasets list, backtest, evaluate. Reads only through storage (`--data-url`). | library |

### One bar in the backtest engine

```
open of bar t   : SimulatedBroker fills orders queued at t-1 (slippage, commission, buying power)
                  -> Portfolio.apply_fill
close of bar t  : Portfolio marked to market -> equity[t]
                  Strategy.on_bar(MarketView(data, cursor=t)) -> target weights | None
                  risk.apply_limits -> risk.targets_to_orders -> Broker.submit
```

---

## Rules of thumb

- **One responsibility per module. 1000 lines is a hard ceiling; aim for about 300.** Split
  by responsibility, not alphabetically.
- **Strategies are pure.** If a strategy needs new inputs, add a feature and read it through
  `FeatureView`. Never let a strategy open a file or call an API.
- **Everything is UTC and timezone-aware.** The trading day is a separate `session_date`
  column, taken from the instrument's exchange calendar (see ADR 0009).
- **Fail loudly.** Bad data raises `DataValidationError`; bad config raises
  `ConfigurationError`. Never silently fill, drop or default.
- **Changing a boundary needs an ADR** in `docs/adr/` plus the matching `pyproject.toml` contract.

## Adding things

| To add… | Workflow |
|---|---|
| A data source / vendor | `.claude/skills/add-data-source` |
| A dataset or new data grain | `.claude/skills/add-dataset` |
| A feature | `.claude/skills/add-feature` |
| A trading strategy | `.claude/skills/add-strategy` |
| A screener | `.claude/skills/add-screener` |
| A UI widget or screen | `.claude/skills/add-ui-component` |
| An architectural decision | `.claude/skills/write-adr` |
