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
| Web app architecture (layers, component-only rules, workspaces) | [ui/architecture.md](ui/architecture.md) |
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
 │ L2 bars/<interval> · chains/* · events/<type> · rates/treasury · rollups/daily/*     │
 │ universe · catalog/* · results/* · run and job records · raw/ (90-day retention)     │
 └──────────────────────────────────────────────────────────────────────────────────────┘
   L3 config/site/*.toml (shared, via PR) · L4 config/users/<id>/*.toml (per user)

 SHARED LIBRARY (src/algotrade/), layered top to bottom:
   services/    use cases: backtests/ · screening/ (+ exports) · jobs/ · evaluation/ · configs, selection
   engines/     backtest/ · screening/ · selection/
   strategies/  trading/ (backtests) · screeners/. Pure: MarketView / FeatureView in, decisions out.
   features/    framework/ · rollups/ · expressions/ · registry · site  analytics/   metrics, reports
   storage/     tables/ (schemas, readers / writers) · backends/ · configs/ (config store) · runs, locks
   config/      site/ (L3 settings) · strategy/ (configs, selections, resolution + hash) · env, user
   quant/       pure numerics: Black-Scholes price + Greeks, IV, realised vol, rate conventions
   core/        model/ (value objects, instruments, options, ids, errors) · time/ · views/ · validation/
```

### Build status

See [roadmap.md](roadmap.md) (phase tables and Now / Next) for what is built; this document describes the target.

---|---|---|
| Apps | `apps/ingestion`, `apps/backtest`, `apps/api` v1 (read-only, ADR 0024); `apps/web` skeleton + harness (ADR 0025: layers, design-system package, final tokens + layout primitives, placeholder routes) | API writes (submit jobs) (4), `apps/web` screens (5, after mockup approval) |
| L1 | `instruments/reference` from the Nasdaq Trader + SPY universe builder (or universe CSVs) with FIGI / CIK and vendor security types (Massive), `instruments/symbol_history`, FIGI-based `instrument_id` + `instruments/id_map` + `SymbolResolver` (ADR 0018), company details (SEC EDGAR), `events/reference_change` (incl. `ticker_changed`, `id_changed`) + `events/index_change`, rollups `option_liquidity@v1`, `price_stats@v2`, `earnings@v1` (the rollup framework, 2b.2; v2 since ADR 0023 step 3), `InstrumentView` reader | `iv_history` rollup (2b.3) and the liquidity class (an expression feature since ADR 0023 step 3); `fundamentals@v2` + `instruments/shares` from SEC company facts (2b.4) |
| L2 | `chains/*` (Cboe), `events/earnings` (Nasdaq), `bars/1d` + `events/split` + `events/dividend` (Massive, unadjusted; adjusted at read time), `rates/treasury` (U.S. Treasury par yield curve), golden data | live Massive run awaits the API key (1); intraday bars + `rollups/daily/*` (6) |
| L3 | `defaults.toml`, `universe.toml`, `sources.toml`, `nightly.toml`, `rollups.toml`, `features/*.toml` (expression features, ADR 0023), `overrides/leveraged_etfs.csv`, `presets/selections/*`, `presets/strategies/*` | |
| L4 | `strategies/`, `selections/` | `watchlists/`, `preferences.toml` (4–5); DB-backed `ConfigStore` (4) |
| Jobs | local runner keyed by config hash; `backtest`, `screen`, `nightly` | queue-backed runner (6) |
| Other | uv workspace, Parquet storage (local + memory backends), `quant/` (ADR 0021) | DuckDB query engine and catalog; S3 backend for hosting (6) |

---

## 2. Data layers

Every piece of data or configuration belongs to exactly one layer
([data/layers.md](data/layers.md), [ADR 0016](adr/0016-four-data-layers.md)):

| Layer | What | Tables / files | Format | Written by |
|---|---|---|---|---|
| **L1 Instrument** | What each instrument *is* (facts) and what we *know* about it as of a date (derived) | `instruments/reference`, `rollups/instrument/<name>@vN`, read together as `InstrumentView(as_of)` | Parquet, one full snapshot per date | `apps/ingestion` |
| **L2 Instrument × time** | Values over time and events | `bars/<interval>` (1m…1d, unadjusted), `chains/*`, `events/<type>`, `rates/treasury`, `rollups/daily/<name>@vN` | Parquet, partitioned by session date | `apps/ingestion` |
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
| 2 | **Only `apps/ingestion` writes** market and rollup data. The API writes only user configs ([0029](adr/0029-rule-screener.md)) and its live-quote log ([0028](adr/0028-ibkr-enrichment-source.md)). Everyone else reads. Vendor SDKs live in `libs/sources` ([0027](adr/0027-vendor-sources-shared-package.md)); credentials are read only through `config.env`. | [0005](adr/0005-ingestion-is-the-only-writer.md) |
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
             user's): one `screen` job each → select → screen → results/ + exports
  quality checks per session; raw / staging purge last
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
(or, with `[backtest] rebalance_selection`, on every rebalance session, point in time, the set
taking effect `selection_lag_sessions` bars later; see configuration.md "Rebalancing
selections"), never with
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
- Apps never build a runner (contract R5): CLIs call `services.jobs.run_job` (build, recover
  the kinds the caller holds the lock for, run to completion, shut down). A handler runs child
  jobs through `JobContext.jobs.run(...)`, in its own thread, so a busy pool cannot deadlock
  (the nightly runs its `screen` jobs this way). Fan-out inside a task (chain workers) uses
  `services.jobs.as_completed`.

### The nightly workflow (R5)

`apps/ingestion/algotrade_ingestion/workflows/`: `nightly.py` (the steps and the job
handler), `steps.py` (isolation, status rule), `sessions.py` (catch-up), `screens.py` (screen
jobs), `notify.py` (summary file + notifiers), `records.py` / `report.py` / `timing.py` / `render.py`
(the summary email).

- **Steps** (`NIGHTLY`): `universe-build`, `company-details`, `earnings`, `bars`, `rates`,
  `corporate-actions`, `chains`, `rollups`, `screens`, `quality`; then `purge-raw` once
  (`FINALLY`). Each is a registry task (or the `screens` job step) run in isolation: an
  exception makes the step FAILED with its error and later steps still run. A step names its
  hard dependencies (`screens` on `chains` and `rollups`): when one FAILED it is BLOCKED.
  `rollups` runs for every session and reports a rollup whose input the session lacks as
  `no_input`. Data preconditions are separate: `chains` and `screens` need a universe
  snapshot to exist, not today's build to succeed. Missing sources → SKIPPED with the reason.
  `quality` ends every session and `purge-raw` ends the run, whatever failed before. Every
  step records its status and duration.
- **Status, in one place** (`steps.overall`): of the steps that ran, none succeeded → FAILED;
  any FAILED, BLOCKED or PARTIAL → PARTIAL; else COMPLETE. Each session gets a `nightly` run
  record with that status and its per-step results.
- **Exchange calendar** (`core/time/calendar.py`, pure Python): NYSE full-day holidays (with the
  Saturday/Sunday observance rules, Good Friday from the Easter computus, Juneteenth from 2022)
  and 13:00 early closes (July 3 and December 24 when they are sessions, the day after
  Thanksgiving). `last_closed_session(now)` is the latest session whose close plus a settle
  margin (`config/site/nightly.toml`, 30 min) has passed in New York. Every default session in
  `algotrade-ingest` comes from it, so a run started during market hours never ingests today's
  intraday data as end of day.
- **Catch-up** (`sessions.py`): without `--date`, the nightly runs every session after the
  last COMPLETE / PARTIAL nightly up to the last closed session, oldest first, capped at the
  latest `max_catch_up` (5; older ones are reported as `catch_up.dropped`). A FAILED nightly
  is retried next time. Bars, corporate actions, earnings and rollups catch up; sources that
  only serve the current snapshot (universe files, SEC, Cboe chains) and screens run only for
  the latest session. Chains still check that the Cboe snapshot's
  session matches (`STALE_DATA` otherwise), so a missed session's chains can be fetched only
  until the next session opens. `--date D` runs exactly D.
- **Quiet when up to date** (`cli/main.py`): the scheduled form (no `--date`, no `--force`)
  first reads the `nightly` run records, before taking the lock; when every session up to the
  last closed one is COMPLETE / PARTIAL it prints `nothing to do: <session> already ingested`
  and exits 0 (no run or job record, no summary file, no notification). If the lock is held
  (a nightly still running) it prints `busy: ...` and exits 3, without notifying. `--force`
  runs anyway: the missed sessions, or the last closed session again when none are missing.
- **Screens are jobs**: one `screen` job per scheduled screener config, for its owner;
  exports are that job's output. The screen audit records `universe_pre_snapshot`
  (survivorship).
- **Notification** (`notify.py`): every run writes its summary to
  `var/logs/nightly-latest.json`, then hands a `Notice` to the `Notifier` (one interface;
  `notify(notice)` returns a warning instead of raising). The macOS notifier (`osascript`,
  never in tests) alerts only when the status is not COMPLETE; the email notifier sends the
  summary email after every run (below). A run longer than `max_duration_minutes` is
  recorded as a `nightly_duration` WARN. All in `config/site/nightly.toml` (`[notify]
  enabled = false` turns every notification off).

### Nightly summary email

After every nightly (COMPLETE or not) the owner gets one email: subject
`[algotrade] 2026-10-02 nightly: PARTIAL · chains 3,624 OK · 5 steps with failures`, a plain-text
and an HTML part (inline styles only, no images or external assets).

- **Inputs** (`records.py`, read-only): the run summary plus, per step, the registry task's run
  record that step produced (the latest record of that task for the session that finished inside
  the nightly's window). Its per-item statuses (`OK`, `STALE_DATA: chain is for ...`,
  `FETCH_ERROR: ...`) are the deep dive's raw material.
- **Report** (`report.py`, pure): header (sessions, status, start / end, duration, warnings);
  statistics per step (status, duration, per-item status counts, key counts: rows, fetched /
  failed, rollup rows, screens); **failure deep dive**: step errors, failed items grouped by
  normalised reason (ids, URLs, dates and numbers stripped) with counts and up to
  `max_examples` examples each (instrument ids labelled with tickers), quality checks that did
  not pass with their detail, screen coverage gaps (UNKNOWN by reason); short "what to do" hints
  for known failure kinds (circuit open, HTTP 401/403/429, STALE_DATA, NO_CHAIN, duplicate
  keys, ...). Informational statuses (`NO_FACTS`, `EMPTY`, `NO_SESSION`, `NO_INPUT`) are counted,
  not listed as failures.
- **Run timing** (`timing.py`, pure; times in America/Los_Angeles and UTC): total duration vs
  `[alerts] max_duration_minutes`, sessions (catch-up, dropped); per step (per session) start,
  end, duration, share of the run, items processed and throughput (chains underlyings, earnings
  dates, shares CIKs, bars sessions, rollup rows), sub-step timings (each rollup's `seconds`),
  and the trend against the previous nightly and the median of the last 7 (steps over 50 %
  slower flagged; the slowest step highlighted). Steps run one after another, so a step's start
  is the run start plus the steps before it. Not shown yet: run-lock wait and time spent in the
  vendor rate limiter / retries (the limiter returns its wait per request, but nothing sums it
  into run stats).
- **Delivery** (`notify.EmailNotifier`): stdlib `smtplib`, STARTTLS on 587 (465: implicit TLS),
  30 s timeout. `[notify.email]` in `nightly.toml` enables it and names the server; recipients,
  sender and SMTP login come only from the environment (`config/env.py`). Missing variables, an
  SMTP error, or a report that cannot be built become a `notify` WARN in the run summary (and the
  summary file); the nightly never fails for its email, and credentials are never logged.
- **Re-render / re-send**: `algotrade-ingest report --date D [--out f.html] [--send]` rebuilds the
  same report for a past session from the stored run records.

---

## 7. Consistency and concurrency

- **Writers:** only ingestion writes market and rollup data (the API writes only user configs and its live-quote log, ADRs 0029 / 0028). Every file is written to a unique
  temp file in its directory and renamed into place; a run replaces only its own partition.
  The per-partition run index (`_runs.json`) is updated under a file lock, so two runs writing
  the same partition at once (threads or processes) are both indexed (contract-tested).
- **A run publishes all its tables at once** (ADR 0022): `IngestRun` writes pending and
  commits every table when the run finishes COMPLETE or PARTIAL; a FAILED run publishes
  nothing. A read never sees half a commit. A crash mid-commit is completed, and a crashed
  run's pending writes dropped, when the next writing command starts (under the ingest
  lock); retention (`purge-raw`) drops pending writes nobody claimed.
- **One ingest run at a time per store:** every writing `algotrade-ingest` command takes the
  store's `ingest` lock (`Backend.lock`; local: `locks/ingest.lock` under the data root). A
  second run exits with code 3, or queues with `--wait`. Holding it, the CLI marks `nightly` /
  `screen` jobs left running by a crashed process as failed (`JobRunner.recover`), so they
  never block a re-run.
- **Vendor pacing** is shared across processes too (`sources/framework/limiter.py`, `var/run/limits/`),
  and adaptive: Retry-After holds, back-off on 429s and error bursts, slow recovery to the floor.
- **Readers** pick, per partition, the latest run with `knowledge_ts ≤ as_of`. A reader racing
  a writer sees either the old or the new run, never a mix.
- **Configs** are resolved once per run and the hash is recorded; edits affect only later runs.
- **Users:** results and jobs are namespaced by `user_id`; market data is shared and read-only
  to everyone except ingestion.

---

## 8. Code layout (enforced)

Four packages in a uv workspace: `algotrade` (the library), `algotrade-ingestion`,
`algotrade-backtest` and `algotrade-api`, each declaring only its own dependencies, pinned by
`uv.lock`.
Dependencies point **downwards only**, and siblings on the same row may not import each other.
`import-linter` enforces this (`[tool.importlinter]` in `pyproject.toml`).

```
apps/ingestion · apps/backtest · apps/api (algotrade_api)   never import each other
        │ import the library, never the reverse
        ▼
     services/           use cases: jobs, configs, selection, screening, backtests, evaluation;
                         explore/ (read-only queries the API serves)
        │
     engines/            backtest/ · screening/ · selection/   (independent of each other)
        │
 strategies/ (trading · screeners) · features/ · analytics/
        │
     data/               the domain read API (features' framework reads through it)
        │
     storage/ · config/ · quant/
        │
      core/
```

Extra contracts:
- strategies and screeners see only `core`
- feature definitions and configs never touch storage
- only `apps/ingestion` may import `storage.tables.writers`
- inside `engines/backtest`, risk (`limits`, `sizing`), execution (`simulated`) and accounting
  (`portfolio`) stay independent

| Package | Responsibility | May import |
|---|---|---|
| `core/` | `model/`: value objects (`Order`, `Fill`), `Instrument`, options, field names, ids, errors. `time/`: exchange calendar, clock helpers. `views/`: `MarketView`, `FeatureView`, `PriceSeries` (what strategies see). `validation/`: OHLCV sanity. | numpy only |
| `config/` | `site/`: L3 site settings loader. `strategy/`: typed `StrategyConfig` / `Selection` / `Rule`, field catalogue, layered resolution and the config hash. `env.py` (environment), `user.py` (L4 users). Pure. | core |
| `storage/` | Generic data contract. `tables/`: schemas, a `Protocol` per store, the generic reader (tables, ranges, dates, runs) and writer / result-writer facades. `backends/`: `local` (Parquet) and `memory`. `configs/`: the `ConfigStore` and its file / memory stores (never imports `tables/` or `backends/`). `runs.py`, `locks.py`, `factory.py`. No domain rules. | core, pandas, pyarrow (backends only) |
| `data/` | The domain read API, the only way consumers read market data: `reference` (one snapshot rule, instruments, terms, `InstrumentView`, universe, `SymbolResolver`), `prices` (bars + split / dividend adjustment), `events` (by event date), `chains` (filter by underlying), `rates` (the Treasury curve a date sees), `rollups` (stored group rows), `shares` (share counts by filing date), `feature_inputs` (what a feature group reads, by table name; ADR 0023). | storage, quant, core |
| `quant/` | Pure numerics (ADR 0021): `black_scholes` (European price + Greeks, continuous q and r), `implied_vol` (safeguarded Newton, NaN + status code on failure), `realized_vol` (close-to-close, Parkinson, Garman-Klass, Yang-Zhang; 252), `rates` (par → continuous, tenor days, curve interpolation). | numpy, core |
| `strategies/` → `trading/` | Backtest strategies: `MarketView` in, target weights out, plus their registry. | core, quant |
| `strategies/` → `screeners/` | Screener contract, shared `Decision` categories, `short_premium_liquidity`. | core, quant |
| `features/` | The feature store (ADR 0023): `framework/` (`Feature`: one typed, documented column with kind, unit, null meaning, range; `FeatureGroup`: inputs + lookback, params from `rollups.toml`, its features; the dependency graph and the per-session runner, point in time, chunked backfills), `rollups/` (the groups: `FEATURES` + a pure compute; only core, quant, numpy, pandas), `registry.py` (`GROUPS`, `FEATURES`, `feature(name)`, `SUPERSEDED`), `expressions/` (the typed expression language: lexer, parser, type checker, vectorised evaluator, never Python `eval`; expression features from `config/site/features/*.toml` resolved into a `FeatureSet` with the code groups and the groups that materialise expressions), `site.py` (the site's `FeatureSet`; the selection catalogue and the `rollups` task are built from it), `catalogue.py` (renders `docs/data/features.md`). Inputs are asked of `data.feature_inputs` by table name; expression features are computed on read (`services/features.py`) unless materialised. | data (`data.feature_inputs` only), config.site, quant, core |
| `analytics/` | Metrics and report formatting from equity curves + fills. | core |
| `engines/` | `backtest/`: the bar loop, risk limits, sizing, simulated broker, costs, portfolio. `screening/`: runs a screener and audits coverage. `selection/`: three-valued evaluation with a per-rule audit; `schedule.py`, the rebalance sessions and the audit of each change. `backtest/universe.py`: the tradable set per bar (fixed, or from a rebalance schedule; exits on removal). | strategies, config, analytics, core |
| `services/` | Use cases: `backtests/`, `screening/` (run + `exports`), `jobs/`, `evaluation/`; shared by several: `configs`, `selection`, golden `datasets`, `views` (FeatureView builder), `features` (expression features on read: only the stored columns they need). | everything below except `storage.tables.writers` and `storage.tables.readers` (through `data/`) |
| `libs/sources` (`algotrade_sources`, ADR 0027) | Vendor sources as a shared package: `framework/` (protocols, HTTP with retries, pacing, the source registry), `vendors/<vendor>/`, `fixtures/` (synthetic/golden). Vendor SDKs (`ib_async`, `openpyxl`) are declared here. Used by ingestion (batch); the API uses it for live, read-only quotes (ADR 0028); backtests and the library never import it. | core, quant, `config.env` only (import-linter) |
| `apps/ingestion` | Depends on `algotrade-sources`; `tasks/` (`framework/`: `IngestRun` in `run.py` and the task registry; one module per dataset in `reference/`, `market/`, `derived/`, `maintenance/`); nightly workflow (`workflows/nightly/`: ordered, isolated registry tasks, catch-up, screens as jobs, notification); `cli/` (`algotrade-ingest`); `ops/` (schedule). | library |
| `apps/api` | `algotrade-api` (ADR 0024): `main.py` (app factory, CORS, error handlers), `routes/` (one router per area), `schemas/` (pydantic response models = the OpenAPI contract), `deps.py` (settings, store, user). Routes call one `services.explore` query each. | `services.explore`, `config`, `core` only (import-linter) |
| `apps/backtest` | `algotrade-backtest` (`algotrade` alias): datasets list, backtest (golden dataset or config, via jobs), evaluate, config validate/show. Reads only through `data/`. | library |

### Directory layout (ADR 0020)

One folder holds one kind of thing. `architecture/layout.toml` declares every directory under
`src/`, `libs/`, `apps/`, `tests/`, `config/` and `docs/` with a one-line purpose and the import-linter contracts that enforce its
rule; `tests/architecture/test_layout.py` fails on a module in an undeclared directory, on a
directory with more than 10 modules (no exceptions), on a contract name that does not exist,
and on a package whose `__init__.py` has no docstring. The library:

```
src/algotrade/
  core/           pure: no I/O, no pandas / pyarrow, no other algotrade package
    model/        types, instruments, options, fields, ids, errors
    time/         calendar.py (exchange sessions), clock.py (UTC helpers)
    views/        market_view, feature_view, series         what strategies see
    validation/   bars.py (OHLCV sanity)
  config/         env.py, user.py
    site/         settings.py (the one L3 loader), fields.py
    strategy/     schema.py, resolve.py, catalog.py           configs and selections
  storage/        runs.py, locks.py, factory.py
    tables/       interfaces, readers, writers, schemas, result_writer
    backends/     local, memory, arrow, run_selection        the only Parquet / Arrow code
    configs/      store.py (ConfigStore), files.py            config documents only
  quant/          black_scholes, implied_vol, realized_vol, rates   pure numerics (numpy)
  data/           reference, prices, events, chains, rates, resolver
  features/       framework/ (declaration, columns, graph, runner), rollups/, expressions/, registry, site, catalogue
  strategies/{trading,screeners}/  engines/{backtest,screening,selection}/  analytics/
  services/       configs, datasets, selection, views         shared by several use cases
    backtests/    run.py
    screening/    run.py, exports.py
    explore/      store, runs, universe, instruments, chains, features, screens,
                  backtests, configs, ingestion, ideas/       read-only queries (the API)
    jobs/  evaluation/
```

Library folder rules (import-linter): every `core/*` package is pure; `core.model` and
`core.time` never import `core.views` / `core.validation`; strategies see only `core` and
`quant`; `quant` imports only numpy and `core` (no pandas, pyarrow, storage, data, config);
`storage.configs` never imports `storage.tables` or `storage.backends` (and the reverse);
pyarrow only in `storage.backends`; `config.site` never imports `config.strategy`; the
`backtests` and `screening` use cases are independent. Vendor sources (ADR 0027):

```
libs/sources/algotrade_sources/
  framework/      base.py, http.py, limiter.py, registry.py      non-vendor machinery
  vendors/        cboe/, ibkr/, massive/, nasdaq/, sec/, ssga/, treasury/   one folder per vendor
  fixtures/       the golden synthetic source
```

The ingestion app:

```
apps/ingestion/algotrade_ingestion/
  cli/            main.py (argument parsing, console script), commands.py
  ops/            schedule.py (launchd plist for the nightly)
  tasks/
    framework/    run.py (IngestRun, TaskContext), registry.py   machinery
    reference/    universe_build, universe_import, classify, instrument_ids, reference_diff,
                  symbol_history, company_details
    market/       bars, corporate_actions, earnings, option_chains, rates
    derived/      rollups
    maintenance/  quality, purge, migrate_ids, golden
  workflows/
    nightly/      nightly, steps, sessions, screens, notify
```

Folder rules (tests + import-linter): a vendor folder registers at least one source in
`algotrade_sources/framework/registry.py` and nothing else imports it; vendors never import
each other; `algotrade_sources` imports only `core`, `quant` and `config.env` (never storage,
data, features, services, engines or any app); the library and `algotrade_backtest` never import
`algotrade_sources`; only the IBKR facade imports `ib_async`; tasks never import
`algotrade_sources.vendors` (sources come from the registry through `ctx.sources`). A module in
`tasks/<domain>/` is a registered task or a helper imported only inside its domain (or by the
task registry); `[[shared]]` names the reasoned exceptions (the ingestion id rule,
`reference/instrument_ids.py`).

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
| Nightly options pipeline, ~4.2k underlyings | ~80 min, dominated by Cboe chains paced at ~57 requests/min (~75 min; Cboe allows ~60/min) (WARN recorded above 150 min) |
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
(universe size change, bar freshness and count drop, option chains, earnings present;
thresholds in `config/site/sources.toml` `[quality]`); any FAIL marks the nightly `PARTIAL`.
Option chains are judged on two separate counts: **fetch failures** (`FETCH_ERROR`, including
an open circuit breaker, or never attempted) above `max_chain_fetch_failures` (5% of the
universe) FAIL `chains_fetch`, because the night's data is missing; **stale chains**
(`STALE_DATA`: the feed served an older session) above `max_chain_stale_share` (20%) only WARN
`chains_stale`, because screens already treat those names as UNKNOWN. Both details report the
OK / STALE_DATA / NO_CHAIN / NO_STANDARD_SERIES counts. It is scheduled
locally by a launchd agent (`algotrade-ingest schedule`, `ops/schedule.py`): weekdays at 15:00
local (Pacific; close 13:00 PT), `RunAtLoad` (login / boot, for a Mac that was off) and an
hourly `StartInterval` watchdog. Every start runs `nightly` without `--date`: a no-op when up to
date, otherwise catch-up, which is safe at any hour because of `last_closed_session` (before
close + settle the previous session is the latest). The owner may add a weekday wake with
`sudo pmset repeat wakeorpoweron MTWRF 14:55:00`; the code never runs it. A run that
is not COMPLETE triggers a desktop notification; every run's summary is in
`var/logs/nightly-latest.json`. Monitoring lives in run records today: status per job and per
nightly step, coverage per screen (alert below 98%), selection size per config (alert on a
> 20% day-over-day change), nightly duration (recorded as a WARN above 150 min,
`config/site/nightly.toml`).

## 12. API

[ADR 0024](adr/0024-api.md). `apps/api` is the web app's only backend: a read-only FastAPI
(`algotrade-api` → uvicorn on 127.0.0.1:8000, `--reload` for development) over
`services/explore/`. It reads the store at `ALGOTRADE_DATA_URL` and the configs at
`ALGOTRADE_CONFIG_DIR` for the single local user `ALGOTRADE_USER`.

```
web (apps/web) ──HTTP/JSON──▶ routes/<area>.py ──one call──▶ services/explore/<area>.py
                               │ schemas/<area>.py             │ algotrade.data (market data)
                               │ (pydantic → OpenAPI            │ StoreReader.runs / .run (records)
                               ▼  → apps/api/openapi.json)      ▼ services.configs (configs)
```

| Area | Endpoints (GET; `?date=` defaults to the latest session the area has) |
|---|---|
| health | `/health`: storage kind, latest session, tables, versions |
| explore | `/explore/tickers?date&<universe filters>&columns=<feature names>&sort=[-]<column>&page&size` (tickers × any catalogue columns, values through `InstrumentView`, columns validated against the catalogue); `/explore/compare?ids=a,b,c&features=` (one row per feature, one value per ticker); `/explore/compare/prices?ids&from&to&rebase=100&adjust` (closes on one date axis, rebased; `rebase=0`: raw) |
| universe | `/universe?date&security_type&leveraged&sector&liquidity_class&optionable&q&page&size` |
| instruments | `/instruments/{id}` (id or ticker: reference + company + latest features); `.../bars?from&to&adjust=splits\|none\|total_return`; `.../events?from&to`; `.../features?names&from&to`; `.../holdings?top=10&date` (an ETF's largest holdings with weights, the file's total line count, the issuer's as-of date and the source; a non-ETF or an ETF with nothing stored is 200 with an empty list; ADR 0035) |
| chains | `/chains/{underlying_id}?date&expiry`: expiries, strikes, quotes with Cboe IV + Greeks, underlying quote, fetch status, our IV30; `/chains/{underlying_id}/live?expiry&strikes=` (repeatable; default the `live_strikes` nearest the underlying): live IBKR quotes through `services/live/` ([ADR 0028](adr/0028-ibkr-enrichment-source.md#live-option-quotes-in-the-api)), cached 60 s, recorded to `live/option_quotes`; when the gateway cannot answer, the stored chain with `source = stored` and a `status` (DISABLED, UNAVAILABLE, ERROR), never an error |
| features | `/features` (catalogue: kind, dtype, description, null meaning, version, inputs); `/features/{name}/distribution?date` (count, nulls, quantiles, histogram or categories) |
| ideas | `/ideas?date&user&limit` (one row per ticker over every rule screen's latest stored run, ranked by the user's `ideas.priority` in `config/users/<u>/preferences.toml`, then score) |
| screener view | `GET /preferences/screeners/{id}/view?user` and `PUT` (a user's added catalogue columns, sort and shown decisions for one screener's results, in `screeners.<id>.view` of `preferences.toml`; never part of a screener version or hash; ADR 0032) |
| screen run | `POST /screens/{config_id}/run?date&user` (run a screener on request for the latest session with data, unless this version has results for it: `ready`, else the nightly's `screen` job under the writer lock, 202) and `GET /screens/{config_id}/run/{job_id}` (its state; ADR 0033) |
| screens | `/screens` (screener configs + schedule + latest run); `/screens/{config_id}/results?date&decision&page&size` (+ audit); `/screens/{config_id}/table?date&decision&change&q&columns&sort&page&size` (a rule screen's run as a review table: criteria, display columns, features, new / dropped; ADR 0032) |
| backtests | `/backtests`; `/backtests/{run_id}` (metrics, selection, data versions, rebalances, equity curve, fills) |
| configs | `/configs`; `/configs/{id}` (resolved: layers + hash) |
| preview (POST, read-only dry runs; `routes/preview/` → `services/explore/preview/`) | `POST /screeners/preview {spec, user, limit}` (an unsaved rule-screen draft evaluated by the nightly `evaluate_screen` on the latest closed session: summary, decisions, funnel per gating criterion, coverage, top rows; field frame cached per session, fields, user features and `visible_seq`; an invalid draft → 400 naming its path); `POST /features/check {expr, user, sample}` (a formula's type, inputs and licence, sampled on the latest session its inputs have) |
| admin (Admin workspace only; role-gating attaches to `/admin/`) | `/admin/ingestion/completeness?sessions=10` (dataset × session: present vs expected rows, COMPLETE / PARTIAL / MISSING / CARRIED, run ids); `/admin/ingestion/{dataset}/{session}` (drill-down: items not OK grouped by reason with examples, the runs); `/admin/runs/nightly?limit=` (per session: status, steps with status / duration / counts); `/admin/runs/{run_id}` (items by status, failures grouped by reason, stats); `/admin/runs/{run_id}/items` (every item with its status code); `/admin/quality?date=` (the latest data-quality checks: PASS / WARN / FAIL with detail); `/admin/verification/ibkr?date=` (the live verification vs IBKR: counts by status and check, failing rows); `/admin/review/figi`, `/admin/review/leveraged` (the owner's curation lists) |

Errors: unknown id / no data for the date → 404; bad configuration → 400; bad parameters →
422. The API writes nothing except the live quotes it served (`live/*` tables, ADR 0028). The committed `apps/api/openapi.json` must match the app (`scripts/export_openapi.py`; a
test fails when it is stale); the web client is generated from it.

## 13. Hosting

Local (macOS) today: Python 3.12 via uv, storage at `ALGOTRADE_DATA_URL` (default
`file://./var/data`), configs at `ALGOTRADE_CONFIG_DIR` (default `./config`). Hosting needs no
redesign: an `s3://` storage backend, a DB-backed `ConfigStore` and a queue-backed job runner
(phases 4–6).

---

## 14. Ownership and boundaries

[ADR 0019](adr/0019-ownership-and-boundaries.md). Layers say who may import whom; ownership
says who may *do* what. Each responsibility below has exactly one owner; the restructure
(roadmap track R) that moved them there is complete. `architecture/ownership.toml` is the
source of truth, with the AST patterns `scripts/check_ownership.py` uses to flag anyone else
doing it. The ratchet `architecture/known_violations.toml` is empty: any hit fails CI.

| Responsibility | Owner |
|---|---|
| snapshot selection ("latest on or before D", else earliest + `pre_snapshot`) | `data/reference.py` |
| market-data reads for consumers | `data/` |
| which Treasury curve a date sees; rates for a time to expiry | `data/rates.py` |
| option prices and Greeks; implied vol; realised vol; rate conventions (ADR 0021) | `quant/black_scholes.py`; `quant/implied_vol.py`; `quant/realized_vol.py`; `quant/rates.py` |
| run ids, run records, COMPLETE / PARTIAL | `storage/runs.py` (`start_run`, `RunRecord.finish` for screens and backtests), `services/jobs/`, ingestion `tasks/framework/run.py` (`IngestRun`) |
| raw persistence, row stamping, id resolution in ingestion | `tasks/framework/run.py` (`IngestRun`) |
| which ingestion steps run, with which defaults | `tasks/framework/registry.py`; nightly order in `workflows/nightly/nightly.py` |
| the nightly summary report and its delivery (desktop alert, summary email over SMTP) | `workflows/nightly/` (`records.py`, `report.py`, `timing.py`, `render.py`, `notify.py`) |
| vendor HTTP, retries, retry cap, circuit breaker | `sources/framework/http.py` |
| rate limiting | `sources/framework/limiter.py`, one per key, shared across threads and processes |
| source construction (vendors and the golden fixture source) | `sources/framework/registry.py` (vendor specifics stay in `sources/vendors/<vendor>/`) |
| session sources (a stateful gateway connection: probe, open, always close) | `sources/framework/base.py` (`SessionSource`, `opened`), `sources/framework/registry.py` (`SessionSpec`) |
| broker access, READ-ONLY (the only `ib_async` import; market data only; ADR 0026) | `sources/vendors/ibkr/gateway.py` |
| live verification against IBKR (sample, checks, `verification/ibkr`) | `tasks/verification/` |
| locks (flock, named store locks, run-index lock); the ingest run lock | `storage/locks.py`; `services/jobs/exclusive.py` |
| session / exchange calendar | `core/time/calendar.py` |
| job execution | `services/jobs/` (apps use `run_job`; fan-out `as_completed`) |
| screen execution | `services/screening/run.py`, submitted as `screen` jobs (nightly: `workflows/nightly/screens.py`) |
| site settings: `config/site/*.toml` → typed objects | `config/site/settings.py` (the store only reads files) |
| environment variables and `.env` | `config/env.py` (the storage factory receives the URL) |
| table schemas: required columns, declared types, validation, how a table's runs combine (`TableSpec.runs`) | `storage/tables/schemas.py` |
| which runs of a partition a read sees (`snapshot` / `merge`, restating runs; ADR 0007) | `storage/backends/run_selection.py` |
| Parquet / Arrow I/O (casting to declared types, schema version, row groups) | `storage/backends/` (`arrow.py` shared by every backend) |
| HTTP: routers, response schemas, CORS, error mapping, the ASGI server (ADR 0024) | `apps/api/algotrade_api/` |
| read-only queries pages show (which partition a `?date=` sees, pages, JSON-safe rows) | `services/explore/` |

### Typed settings and schemas (R6)

**Settings.** `config/site/settings.py` is the one loader for `config/site/*.toml`:
`SourcesSettings` (vendors, `[http]`, `[quality]`, retention), `UniverseSettings` (+ the
curated leveraged-ETF overrides), `NightlySettings`, and the run defaults
`ScreeningSettings` / `BacktestSettings` (layered per config by `resolve`, exposed as
`ResolvedConfig.screening` / `.backtest`). All are frozen dataclasses; the types live in the
library, not in the app that reads them, so the loader validates every key in one place. A
missing file or key falls back to the defaults; an unknown key, a wrong type or an
out-of-range value fails with its path (`sources.toml [massive] min_interval_s: expected a
number >= 0, got 'fast'`). `config/` does no file I/O: documents come from the
`ConfigStore`. `config/env.py` is the only reader of environment variables (`credential`,
`data_url`, `config_dir`, `user_id`, `load_dotenv`).

**Schemas.** `storage/tables/schemas.py` declares every column of every fixed table with an abstract
type (`string`, `float64`, `int64`, `bool`, `date`, `timestamp_utc`) and nullability; open
tables (`events/`, `rollups/`, `results/`, `catalog/`) type their common and key columns.
Writers validate (missing, undeclared, null keys, duplicates, OHLCV sanity); backends cast to
the declared types through `storage/backends/arrow.py`, fail on uncastable data, and stamp
the table name and `SCHEMA_VERSION` into each Parquet file. Details:
[data/storage.md](data/storage.md#column-types-and-schema-version).

### Ingestion tasks (R3)

An ingestion **task** produces stored tables and one run record; a **job** is something
`services/jobs` runs (nightly, screens, backtests). In `apps/ingestion/algotrade_ingestion/tasks/`:

- `framework/run.py`: `IngestRun`, the ingest loop written once. It creates the run id and
  record (resuming an unfinished one when asked), `fetch`es (raw payload saved as received,
  then normalised), records per-item status with exception capture, resolves tickers to ids
  through `algotrade.data`, stamps the point-in-time columns, validates and writes, and
  decides the status in one place: any failed item or explicit `partial` → PARTIAL; an
  exception → a saved FAILED record, re-raised. The clock is injected (`TaskContext.clock`).
- `framework/registry.py`: every task declared once: name, description, tables it writes (checked
  against `[[table]]` producers in `architecture/ownership.toml`), sources it needs (by name
  in `TaskContext.sources`), the settings section it reads, its parameters (the CLI turns
  them into flags) and `run(ctx, params)`. Defaults from settings are applied here, so
  `algotrade-ingest <task>`, `algotrade-ingest run <task>` and nightly cannot drift.
- one module per dataset, grouped by domain (`market/`: `bars.py`, `corporate_actions.py`,
  `earnings.py`, `option_chains.py`, `rates.py`; `reference/`: `company_details.py`, `universe_build.py`,
  `universe_import.py`; `derived/`: `rollups.py`; `maintenance/`: `quality.py`, `purge.py`,
  `migrate_ids.py`, `golden.py`): only what to fetch, how to combine frames, task stats.

Sources are built by the source registry (`sources/framework/registry.py`, R4): each declared once with
its `sources.toml` section, credential variable, limiter key and default pacing. A source whose
section is disabled or whose variable is missing is left out with a reason; nightly skips the
tasks that need it (`skipped: <reason>`) and an explicit run fails with it. Tasks receive
sources through the context (`ctx.sources[name]`) and never import vendor modules
(contract R3).

Rules: **R1** only `data/` reads market data for consumers; **R2** storage has no domain
knowledge; **R3** tasks get sources from the registry, never import vendor modules; **R4**
sources never import storage; **R5** everything runs through the job runner. All five are
import-linter contracts; none is pending. Every stored table has exactly one producing owner
(`[[table]]` in the registry).

Gates (all in `make check` and CI): `make ownership` (the ratchet
`architecture/known_violations.toml` is empty, and a fitness test keeps it empty with no
pending contract: an exception needs an ADR and an `allowed` entry with its reason),
`make dupes` (pylint duplicate-code against `architecture/dupes_baseline.txt`), `make arch`,
and `tests/architecture/`.

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
| An API endpoint | `.claude/skills/add-api-endpoint` |
| An architectural decision | `.claude/skills/write-adr` |
