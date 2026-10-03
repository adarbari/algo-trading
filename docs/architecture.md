# Architecture

The canonical description of the system: what it is, the rules it follows, and what is built
versus planned. Detail lives in companion docs:

| Topic | Doc |
|---|---|
| The four data layers (L1–L4), tables, roll-ups, L1 columns | [data/layers.md](data/layers.md) |
| Physical storage: grains, partitions, backends, contract tests | [data/storage.md](data/storage.md) |
| Configs, selections and users (L3/L4) | [configuration.md](configuration.md) |
| Instruments and the universe | [data/instruments.md](data/instruments.md) |
| Vendors | [data/vendors.md](data/vendors.md) |
| Screeners | [screeners/](screeners/README.md) |
| UI design system | [ui/design-system.md](ui/design-system.md) |
| Who owns each responsibility (machine-readable) | `architecture/ownership.toml`, [ADR 0019](adr/0019-ownership-and-boundaries.md) |
| Why each decision was made | [adr/](adr/README.md) |
| Order of work and follow-ups | [roadmap.md](roadmap.md) |

---

## 1. System view

```
 APPS (entry points: wiring, config, scheduling. Thin, little logic.)

   apps/ingestion        apps/backtest          apps/api (phase 4)  apps/web (phase 5)
   scheduled pipeline    CLI / notebooks        FastAPI server      React + design system
   pull → validate →         │                      │                  │
   normalise → rollups       │ in-process           │◀──── HTTP ───────┘
   → scheduled screens       │                      │
        │ WRITES             │ READS                │ READS (+ submits jobs)
        ▼                    ▼                      ▼
 ┌─────────────────────────── storage (the data contract) ────────────────────────────┐
 │ L1 instruments/reference · rollups/instrument/*                                      │
 │ L2 bars/<interval> · chains/* · events/<type> · rollups/daily/*                      │
 │ universe · catalog/* · results/* · run and job records · raw/ (90-day retention)     │
 └──────────────────────────────────────────────────────────────────────────────────────┘
   L3 config/site/*.toml (shared, via PR) · L4 config/users/<id>/*.toml (per user)

 SHARED LIBRARY (src/algotrade/), layered top to bottom:
   services/    use cases: jobs, configs, selection, screening, backtests, evaluation, exports
   engines/     backtest/ · screening/ · selection/
   strategies/  trading/ (backtests) · screeners/. Pure: MarketView / FeatureView in, decisions out.
   features/    versioned rollup definitions          analytics/   metrics, reports
   storage/     schemas · stores per layer · readers / writers · backends/ · config store
   config/      typed configs, selections, users, layered resolution + hash
   (quant/      pricing maths, Greeks, IV: phase 2b)
   core/        instruments, value objects, MarketView / FeatureView, options, errors, time
```

### Build status

| Area | Built | Planned (phase) |
|---|---|---|
| Apps | `apps/ingestion`, `apps/backtest` | `apps/api` (4), `apps/web` (5) |
| L1 | `instruments/reference` from the Nasdaq Trader + SPY universe builder (or universe CSVs) with FIGI / CIK and vendor security types (Massive), `instruments/symbol_history`, FIGI-based `instrument_id` + `instruments/id_map` + `SymbolResolver` (ADR 0018), company details (SEC EDGAR), `events/reference_change` (incl. `ticker_changed`, `id_changed`) + `events/index_change`, `rollups/instrument/option_liquidity@v1`, `InstrumentView` reader | `price_stats`, `iv_history`, `earnings`, `liquidity_class`, `fundamentals` rollups (2b) |
| L2 | `chains/*` (Cboe), `events/earnings` (Nasdaq), `bars/1d` + `events/split` + `events/dividend` (Massive, unadjusted; adjusted at read time), golden data | live Massive run awaits the API key (1); intraday bars + `rollups/daily/*` (6) |
| L3 | `defaults.toml`, `universe.toml`, `overrides/leveraged_etfs.csv`, `presets/selections/*`, `presets/strategies/*` | `sources.toml` (1, done); `rollups.toml` (2b) |
| L4 | `strategies/`, `selections/` | `watchlists/`, `preferences.toml` (4–5); DB-backed `ConfigStore` (4) |
| Jobs | local runner keyed by config hash; `backtest`, `screen`, `nightly` | queue-backed runner (6) |
| Other | uv workspace, Parquet storage (local + memory backends) | DuckDB query engine and catalog; S3 backend for hosting (6); `quant/` (2b) |

---

## 2. Data layers

Every piece of data or configuration belongs to exactly one layer
([data/layers.md](data/layers.md), [ADR 0016](adr/0016-four-data-layers.md)):

| Layer | What | Tables / files | Format | Written by |
|---|---|---|---|---|
| **L1 Instrument** | What each instrument *is* (facts) and what we *know* about it as of a date (derived) | `instruments/reference`, `rollups/instrument/<name>@vN`, read together as `InstrumentView(as_of)` | Parquet, one full snapshot per date | `apps/ingestion` |
| **L2 Instrument × time** | Values over time and events | `bars/<interval>` (1m…1d, unadjusted), `chains/*`, `events/<type>`, `rollups/daily/<name>@vN` | Parquet, partitioned by session date | `apps/ingestion` |
| **L3 Site config** | Shared choices: coverage, sources, rollup thresholds, defaults, presets, curated overrides | `config/site/*.toml`, `config/site/overrides/*.csv` | TOML / CSV, changed by PR | the repo |
| **L4 User config** | One user's selections, strategy configs, watchlists, preferences | `config/users/<id>/*.toml` | TOML now, DB later | the user |

L1 and L2 are global market data, written only by ingestion and point-in-time. L3 and L4 are
configuration, resolved into a hashed `ResolvedConfig`. Below the layers sits plumbing (raw
vendor responses, run and job records); above them sit outputs (results, per user).

---

## 3. Non-negotiable rules

| # | Rule | ADR |
|---|---|---|
| 1 | Apps are separate processes and packages in one repo. They **never import each other**; they share only the library and storage. | [0004](adr/0004-apps-and-shared-libraries.md) |
| 2 | **Only `apps/ingestion` writes** market and rollup data. Everyone else reads. Vendor SDKs and credentials live only in ingestion. | [0005](adr/0005-ingestion-is-the-only-writer.md) |
| 3 | Storage is organised by **data grain and layer** behind repository interfaces. Parquet on local disk today (DuckDB-readable; a DuckDB query engine is planned); backends swap via `ALGOTRADE_DATA_URL`. | [0006](adr/0006-storage-grains-and-adapters.md), [0016](adr/0016-four-data-layers.md) |
| 4 | All market and rollup data is **point-in-time**: every row records when it happened *and* when we learned it. | [0007](adr/0007-point-in-time-data.md) |
| 5 | **Backtests only read from stores.** They never call a vendor. Missing data is an error that names the ingestion job to run. | [0008](adr/0008-backtests-read-only-from-stores.md) |
| 6 | Everything is keyed by a generic **instrument** with a contract multiplier, so options and futures need no redesign. | [0009](adr/0009-generic-instrument-model.md) |
| 7 | Long-running work (backtests, screens, nightly runs; later on-request pulls) is a **job** submitted through `services/jobs`. | [0010](adr/0010-jobs-model.md) |
| 8 | Strategies and screeners are **pure**: they see a `MarketView` or `FeatureView` only, never storage or vendors. | [0001](adr/0001-layered-architecture.md) |
| 9 | Data comes from **several sources, free first**, each behind the same source interface. | [0012](adr/0012-data-vendors.md), [0014](adr/0014-cboe-options-source.md) |
| 10 | **The universe is coverage, not a filter:** every US-listed common stock, ADR and ETF (including leveraged and inverse), with S&P 500 membership as data, saved as a dated snapshot. Coverage is a site decision (`config/site/universe.toml`). **Each strategy picks its subset with a `Selection`** in a site (L3) or user (L4) config, resolved defaults < site < user < run; a user can narrow coverage but never widen it. Every run records the user and the config hash. | [0013](adr/0013-universe.md), [0015](adr/0015-configs-selections-users.md) |
| 11 | The UI is built **design-system first**. | [0011](adr/0011-design-system-first-ui.md) |
| 12 | Local first, hostable later: config from env vars, storage and configs behind URLs and protocols, the API serves the web build. | [0004](adr/0004-apps-and-shared-libraries.md) |
| 13 | **Every responsibility has exactly one owner** (`architecture/ownership.toml`). Extend the owner; never re-implement. CI rejects new duplicates (`make ownership`, `make dupes`). | [0019](adr/0019-ownership-and-boundaries.md) |

---

## 4. Configuration in one page

Full reference: [configuration.md](configuration.md).

- **L3 site** (`config/site/`): `defaults.toml`, shared `presets/selections` and
  `presets/strategies`; planned `universe.toml`, `sources.toml`, `rollups.toml` and curated
  `overrides/`.
- **L4 user** (`config/users/<id>/`): `selections/` and `strategies/`; planned `watchlists/`
  and `preferences.toml`.
- **Resolution:** built-in defaults < L3 < L4 < run overrides. A user **narrows** a preset
  (`selection_overrides`, AND-ed, so preset fixes still apply), **replaces** its selection, or
  **extends** it under a new id.
- **Selections** are typed rules over a field catalogue (`instrument.*`,
  `rollup.<name>@vN.*`), evaluated with three-valued logic: missing data is UNKNOWN and never
  passes. Each run stores a per-rule audit.
- **Users** are a validated label today (`--user`); identity and auth arrive with the API.
  Market data and rollups are global; configs, results and jobs are per user.

---

## 5. Data flow

```
nightly (the "nightly" job; later also intraday or on request)
  universe build (Nasdaq Trader + SPY holdings, when universe.toml source = nasdaq_trader;
                  otherwise the monthly master CSV import)
    → instruments/reference (everything listed) + universe (coverage) + change events
  ingestion: pull per source → raw/ (as received, 90-day retention)
           → validate + normalise → reference / events / bars / chains
           → rollups (versioned)
           → every config with schedule = "nightly" (site presets as user "site", then each
             user's): select → screen → results/ + exports
on request
  backtest CLI / api → services.jobs.submit("backtest") → engines.backtest (reads stores only)
  api → services → results / rollups                       (web UI, phase 4–5)
```

### Critical path: a configured backtest

```
algotrade-backtest --user U backtest --config sma_trend --start S --end E
  → services.jobs.submit("backtest", {config, start, end}, user)          → job id
  → services.configs.resolve_config("sma_trend", user)                    → ResolvedConfig (hash)
  → services.selection.select(reader, cfg.selection, session=S)           → instruments + audit
  → reader.bars("1d", S, E, instruments) + reader.instrument_terms(S)     → aligned series + multipliers
  → engines.backtest.run_backtest(series, strategy(cfg.params), settings) → BacktestResult
  → result_writer.write_result("backtests", …) + run record (user, config hash, dataset versions)
```

Results land in `results/backtest_equity` (instrument `PORTFOLIO`) and
`results/backtest_fills`, and the run record holds the metrics, the selection audit, the config
hash and the exact `bars` / reference runs read. Survivorship rule: the selection is evaluated as of the backtest's start date
(re-evaluation at a `rebalance_selection` interval is planned, phase 2b), never with
today's universe.

### Critical path: a configured screen

```
select (as of session) → FeatureView of the screener's rollups for the selected instruments
  → screener → one row per instrument with a Decision → coverage audit
  → results/<screener> (user_id, config_id, config_hash) + run record + declared exports
```

Coverage statuses: `COMPLETE`, `PARTIAL` (below `min_coverage`), `UNIVERSE_INCOMPLETE`
(universe older than `max_universe_age_days`), `EMPTY_SELECTION`. Only a `COMPLETE` run may
report "no qualified candidates".

---

## 6. Jobs

`services/jobs` ([ADR 0010](adr/0010-jobs-model.md)): `submit(kind, params, user)` → job id;
`status`, `wait`. Job records are stored as run records, so they survive restarts and appear in
audits. The local runner uses 2 threads.

- **Idempotent:** identical work returns the existing job. The key is **(kind, config hash,
  session or dates, user)**, so editing a config and resubmitting runs again. Each job kind
  declares its identity (`JobKind(handler, identity)`).
- `force` re-runs a finished job (the CLIs use it); failed jobs re-run on resubmit; a queued or
  running job is never duplicated.
- `recover()` marks jobs abandoned by a crashed process as failed.
- Handlers: the library provides `backtest` and `screen`; the ingestion app registers
  `nightly`. A queue-backed runner (phase 6) implements the same protocol.

---

## 7. Consistency and concurrency

- **Writers:** only ingestion writes market and rollup data. Every file is written to a unique
  temp file in its directory and renamed into place; a run replaces only its own partition.
  The per-partition run index (`_runs.json`) is updated under a file lock, so two runs writing
  the same partition at once (threads or processes) are both indexed (contract-tested).
- **One ingest run at a time per store:** every writing `algotrade-ingest` command takes the
  store's `ingest` lock (`Backend.lock`; local: `locks/ingest.lock` under the data root). A
  second run exits with code 3, or queues with `--wait`. Holding it, the CLI marks `nightly` /
  `screen` jobs left running by a crashed process as failed (`JobRunner.recover`), so they
  never block a re-run.
- **Vendor pacing** is shared across processes too (`sources/limiter.py`, `var/run/limits/`).
- **Readers** pick, per partition, the latest run with `knowledge_ts ≤ as_of`. A reader racing
  a writer sees either the old or the new run, never a mix.
- **Configs** are resolved once per run and the hash is recorded; edits affect only later runs.
- **Users:** results and jobs are namespaced by `user_id`; market data is shared and read-only
  to everyone except ingestion.

---

## 8. Code layout (enforced)

Three packages in a uv workspace: `algotrade` (the library), `algotrade-ingestion` and
`algotrade-backtest`, each declaring only its own dependencies, pinned by `uv.lock`.
Dependencies point **downwards only**, and siblings on the same row may not import each other.
`import-linter` enforces this (`[tool.importlinter]` in `pyproject.toml`).

```
apps/ingestion (algotrade_ingestion) · apps/backtest (algotrade_backtest)   never import each other
        │ import the library, never the reverse
        ▼
     services/           use cases: jobs, configs, selection, screening, backtests, evaluation
        │
     engines/            backtest/ · screening/ · selection/   (independent of each other)
        │
 strategies/ (trading · screeners) · features/ · analytics/
        │
     storage/ · config/
        │
      core/
```

Extra contracts:
- strategies and screeners see only `core`
- feature definitions and configs never touch storage
- only `apps/ingestion` may import `storage.writers`
- inside `engines/backtest`, risk (`limits`, `sizing`), execution (`simulated`) and accounting
  (`portfolio`) stay independent

| Package | Responsibility | May import |
|---|---|---|
| `core/` | Value objects (`Order`, `Fill`, `PriceSeries`), `Instrument`, `MarketView`, `FeatureView`, options, ids, errors, time. | numpy only |
| `config/` | L3/L4 configuration: typed `StrategyConfig` / `Selection` / `Rule`, field catalogue, layered resolution and the config hash. Pure. | core |
| `storage/` | Generic data contract: schemas, a `Protocol` per store, the generic reader (tables, ranges, dates, runs) and writer / result-writer facades, `local` (Parquet) and `memory` backends, `ConfigStore`. No domain rules. | core, pandas, pyarrow |
| `data/` | The domain read API, the only way consumers read market data: `reference` (one snapshot rule, instruments, terms, `InstrumentView`, universe, `SymbolResolver`), `prices` (bars + split / dividend adjustment), `events` (by event date), `chains` (filter by underlying). | storage, core |
| `strategies/` → `trading/` | Backtest strategies: `MarketView` in, target weights out, plus their registry. | core |
| `strategies/` → `screeners/` | Screener contract, shared `Decision` categories, `short_premium_liquidity`. | core |
| `features/` | Pure, versioned rollup definitions (`option_liquidity@v1`) with declared output columns, and their registry. | core |
| `analytics/` | Metrics and report formatting from equity curves + fills. | core |
| `engines/` | `backtest/`: the bar loop, risk limits, sizing, simulated broker, costs, portfolio. `screening/`: runs a screener and audits coverage. `selection/`: three-valued evaluation with a per-rule audit. | strategies, config, analytics, core |
| `services/` | Use cases: `jobs`, `configs`, `selection`, `backtests`, `screening`, golden `datasets`, `exports`, `evaluation/`. | everything below except `storage.writers` and `storage.readers` (through `data/`) |
| `apps/ingestion` | Sources (Cboe, HTTP with retries, synthetic/golden); `tasks/` (one module per dataset, run by `tasks/framework.py` `IngestRun` and declared once in `tasks/registry.py`); nightly workflow (`pipeline.py`, an ordered list of registry tasks); `algotrade-ingest`. | library |
| `apps/backtest` | `algotrade-backtest` (`algotrade` alias): datasets list, backtest (golden dataset or config, via jobs), evaluate, config validate/show. Reads only through `data/`. | library |

### One bar in the backtest engine

```
open of bar t   : SimulatedBroker fills orders queued at t-1 (slippage, commission, buying power)
                  -> Portfolio.apply_fill (value = qty × price × multiplier)
close of bar t  : Portfolio marked to market -> equity[t]
                  Strategy.on_bar(MarketView(data, cursor=t)) -> target weights | None
                  apply_limits -> targets_to_orders -> Broker.submit
```

---

## 9. Failure modes

| Component | Failure | Detection | Recovery | Impact |
|---|---|---|---|---|
| Config load | invalid TOML, unknown field, wrong type | `ConfigurationError` with file and field path | fix the file | the run refuses to start (fail closed) |
| Selection | matches nothing | `EMPTY_SELECTION` | the audit shows which rule removed everything | no results, clearly labelled |
| Selection | rollup missing for the session | values UNKNOWN, counted in the audit | run the rollup job | instruments excluded, never included |
| Backtest data | bars missing for a range | `MissingDataError` naming the ingestion command | backfill | backtest refuses to run |
| Vendor | blocked (403), rate-limited, down | per-ticker status; mass `NO_CHAIN` makes the run `PARTIAL` | retries, resumable job, next sweep | partial runs are labelled, never "complete" |
| Golden fixture store | stale versus committed CSVs | checksum verification on load | `make golden-store` | CI fails loudly |
| Packaging | lock drift | `uv lock --check` | `uv lock` + PR | CI fails |
| Jobs | process exits mid-job | job left running | `recover()` marks it failed; resubmit | re-run needed |

---

## 10. Security and privacy

- **Auth:** none yet. `--user` is a namespace, not an identity. Phase 4 maps authenticated users
  to `user_id`, and services enforce per-user access to configs, results and jobs.
- **PII:** none stored; user ids are opaque labels.
- **Threats:** malicious configs (typed rules only, never code or SQL); path traversal (ids
  restricted to `[a-z0-9_-]{1,64}`); secrets in configs (rejected at load: secret-like keys
  such as `api_key`, `token`, `password`; credentials only from env); cross-user reads (namespaced now, enforced in phase 4).

---

## 11. Scale, targets and monitoring

| Target | Value |
|---|---|
| Strategy baseline | identical within `rel_tol=1e-6, abs_tol=1e-9` on every change |
| Test suite | ≤ 60 s locally and in CI |
| Golden evaluation (3 strategies × 8 datasets) from the store | ≤ 5 s |
| Selection, 10k instruments × 10 rules | ≤ 1 s |
| Nightly options pipeline, ~4.2k underlyings | ≤ 25 min |
| Config resolution | deterministic hash on every OS |
| Code gates | no file > 1000 lines, coverage ≥ 90%, strict mypy, all import contracts |

| Load item | Estimate |
|---|---|
| Daily bars | 10k instruments × 252 sessions ≈ 2.5M rows/yr ≈ 60–80 MB Parquet |
| L1 reference snapshot | < 1 MB/day |
| Option chains | ~1–1.5M rows/day; raw responses 1–3 GB/day before compression (90-day retention) |
| Per-user nightly screens | ~1–3 s per config; 20 users × 5 configs ≈ 3–5 min |

Single machine, stateless services over file storage. Shared work (ingestion, rollups) is
O(universe); per-user work is O(users × configs). The nightly run ends with a `quality` run
(universe size change, bar freshness and count drop, chain coverage, earnings present;
thresholds in `config/site/sources.toml`); any FAIL marks the nightly `PARTIAL`. It is scheduled
locally by a launchd agent (`algotrade-ingest schedule`). Monitoring lives in run records today:
status per job, coverage per screen (alert below 98%), selection size per config (alert on a
> 20% day-over-day change), nightly duration (alert above 40 min).

## 12. Hosting

Local (macOS) today: Python 3.12 via uv, storage at `ALGOTRADE_DATA_URL` (default
`file://./var/data`), configs at `ALGOTRADE_CONFIG_DIR` (default `./config`). Hosting needs no
redesign: an `s3://` storage backend, a DB-backed `ConfigStore` and a queue-backed job runner
(phases 4–6).

---

## 13. Ownership and boundaries

[ADR 0019](adr/0019-ownership-and-boundaries.md). Layers say who may import whom; ownership
says who may *do* what. Each responsibility below has one owner today and one target owner
after the restructure (roadmap track R). `architecture/ownership.toml` is the source of
truth, with the AST patterns `scripts/check_ownership.py` uses to flag anyone else doing it.

| Responsibility | Owner today | Target owner (PR) |
|---|---|---|
| snapshot selection ("latest on or before D", else earliest + `pre_snapshot`) | `data/reference.py` | same (done in R2) |
| market-data reads for consumers | `data/` | same (done in R2) |
| run ids, run records, COMPLETE / PARTIAL | `storage/runs.py`, `services/jobs/`, ingestion `tasks/framework.py` | same (done in R3) |
| raw persistence, row stamping, id resolution in ingestion | `tasks/framework.py` (`IngestRun`) | same (done in R3) |
| which ingestion steps run, with which defaults | `tasks/registry.py`; nightly order in `pipeline.py` | `workflows/` (R5) |
| vendor HTTP, retries, retry cap, circuit breaker | `sources/http.py` | same |
| rate limiting | `sources/limiter.py`, one per key, shared across threads and processes | same (done in R4) |
| source construction | `sources/registry.py` (vendor specifics stay in `sources/<vendor>.py`) | same (done in R4) |
| locks (flock, named store locks, run-index lock); the ingest run lock | `storage/locks.py`; `services/jobs/exclusive.py` | same (done in R4) |
| session / exchange calendar | `core/time.py` | `core/calendar.py` (R5) |
| job execution | `services/jobs/` | same; screens from nightly become `screen` jobs (R5) |
| site settings loading | `config/` | `config/settings.py`, one typed loader (R6) |
| environment variables | `ingestion env.py`, `storage/factory.py` | `config/env.py` (R6) |
| Parquet / Arrow I/O | `storage/backends/` | same |

### Ingestion tasks (R3)

An ingestion **task** produces stored tables and one run record; a **job** is something
`services/jobs` runs (nightly, screens, backtests). In `apps/ingestion/algotrade_ingestion/tasks/`:

- `framework.py`: `IngestRun`, the ingest loop written once. It creates the run id and
  record (resuming an unfinished one when asked), `fetch`es (raw payload saved as received,
  then normalised), records per-item status with exception capture, resolves tickers to ids
  through `algotrade.data`, stamps the point-in-time columns, validates and writes, and
  decides the status in one place: any failed item or explicit `partial` → PARTIAL; an
  exception → a saved FAILED record, re-raised. The clock is injected (`TaskContext.clock`).
- `registry.py`: every task declared once: name, description, tables it writes (checked
  against `[[table]]` producers in `architecture/ownership.toml`), sources it needs (by name
  in `TaskContext.sources`), the settings section it reads, its parameters (the CLI turns
  them into flags) and `run(ctx, params)`. Defaults from settings are applied here, so
  `algotrade-ingest <task>`, `algotrade-ingest run <task>` and nightly cannot drift.
- one module per dataset (`bars.py`, `corporate_actions.py`, `earnings.py`, `option_chains.py`,
  `company_details.py`, `universe_build.py`, `universe.py`, `features.py`, `quality.py`,
  `migrate_ids.py`, `golden.py`): only what to fetch, how to combine frames, task stats.

Sources are built by the source registry (`sources/registry.py`, R4): each declared once with
its `sources.toml` section, credential variable, limiter key and default pacing. A source whose
section is disabled or whose variable is missing is left out with a reason; nightly skips the
tasks that need it (`skipped: <reason>`) and an explicit run fails with it. Tasks receive
sources through the context (`ctx.sources[name]`) and never import vendor modules
(contract R3).

Rules: **R1** only `data/` reads market data for consumers; **R2** storage has no domain
knowledge; **R3** tasks get sources from the registry, never import vendor modules; **R4**
sources never import storage; **R5** everything runs through the job runner. Rules that
already hold are import-linter contracts; the rest are `pending_contract` entries in the
registry, enabled by the PR that makes them true. Every stored table has exactly one
producing owner (`[[table]]` in the registry).

Gates (all in `make check` and CI): `make ownership` (shrink-only
`architecture/known_violations.toml`), `make dupes` (pylint duplicate-code against
`architecture/dupes_baseline.txt`), `make arch`, and `tests/architecture/`.

## Rules of thumb

- **One responsibility per module. 1000 lines is a hard ceiling; aim for about 300.**
- **Strategies are pure.** New inputs become rollups read through `FeatureView`; instrument
  filtering is a selection's job, never strategy code.
- **Everything is UTC and timezone-aware.** The trading day is a separate `session_date`.
- **Fail loudly.** Bad data raises `DataValidationError`; bad config raises
  `ConfigurationError`; missing data is UNKNOWN or `MissingDataError`, never a default.
- **Changing a boundary needs an ADR** plus the matching `pyproject.toml` contract.

## Adding things

| To add… | Workflow |
|---|---|
| A data source / vendor | `.claude/skills/add-data-source` |
| A dataset or new data grain | `.claude/skills/add-dataset` |
| A rollup (feature) | `.claude/skills/add-feature` |
| A trading strategy | `.claude/skills/add-strategy` |
| A screener | `.claude/skills/add-screener` |
| A selection or strategy config | a TOML file in `config/site/presets/` (shared) or `config/users/<id>/` ([configuration.md](configuration.md)); check with `algotrade-backtest config validate <id>` |
| A UI widget or screen | `.claude/skills/add-ui-component` |
| A new responsibility, or moving one | `.claude/skills/add-responsibility` |
| An architectural decision | `.claude/skills/write-adr` |
