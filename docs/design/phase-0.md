# Design: Phase 0. Apps, storage-backed backtests, configurable selections, users

| Field | Value |
|---|---|
| Author | Claude Code, drafted for @adarbari |
| Reviewers | @adarbari |
| Status | **Implemented** (PRs #18–#19, #21–#26; approved 2026-10-03) |
| Created | 2026-10-03 |
| Last Updated | 2026-10-03 (open questions resolved) |

---

## TL;DR

Finish the restructure the roadmap calls phase 0, so the phase 1 data work (daily bars,
earnings, IV history) is built once, on the final structure:

- Move the backtest into the target layout, reading **only from storage**.
- Add a **configuration layer**: every strategy picks its own subset of the full universe
  through declarative, per-user configs.
- Package the apps as a uv workspace, and add a source interface and a local jobs runner.

**The main trade-off:** about 8 PRs of mostly mechanical change before any new data
arrives, in exchange for not redoing the bars table, the backtest data path and screener
inputs a second time.

---

## Key Decisions Summary

| # | Decision | Options considered | Chosen | Why it matters |
|---|---|---|---|---|
| 1 | Packaging | (a) one distribution with several top-level packages (today) · (b) **uv workspace: one package per app + shared library** · (c) separate repos | **(b)** | Each app's dependencies stay separate (vendor SDKs only in ingestion, FastAPI only in api); adds a lock file |
| 2 | How backtests get data | (a) CSV dataset store (today) · (b) **storage `bars` table via `StoreReader`** · (c) direct Parquet reads | **(b)** | Meets ADR 0008; phase 1 Massive bars plug in with no backtest change |
| 3 | Golden datasets | (a) commit a Parquet store · (b) **keep committed CSVs; a `synthetic` source loads them into a separate fixture store** | **(b)** | CSVs stay reviewable as diffs; tests use the same code path as production; fixture data never mixes with real tickers (`AAA` is a real ETF) |
| 4 | Universe vs strategy inputs | (a) one filtered "production universe" (today) · (b) **universe = every instrument; each strategy declares a `Selection`** | **(b)** | Your requirement; one universe, many views of it |
| 5 | Selection language | (a) Python callables · (b) SQL strings · (c) **typed rules `{field, op, value}` with all/any groups** | **(c)** | Safe to accept from users and the UI later, validated against a field catalogue, auditable per rule |
| 6 | Config format | (a) YAML (needs a dependency) · (b) **TOML (stdlib `tomllib`)** · (c) JSON | **(b)** for files | Typed and readable; already used for `pyproject.toml`. Configs written by the UI go through `ConfigStore` (JSON or DB later) |
| 7 | Per-user scope | (a) everything per user · (b) **market data and features global; configs, results and jobs per user** · (c) no users until hosting | **(b)** | Data is fact and is computed once; users differ only in what they select and how they score it |
| 8 | Instrument keys in the backtest | (a) keep symbols · (b) **`instrument_id` everywhere + `multiplier` from reference data** | **(b)** | Options and futures backtests become possible (ADR 0009) |
| 9 | Jobs | (a) call functions directly · (b) **`services/jobs` with a local in-process runner** · (c) Redis/RQ now | **(b)** | Same interface the UI will use in phase 6; no infrastructure yet |
| 10 | Data model | (a) storage grains only (ADR 0006) · (b) **four layers: L1 instrument, L2 instrument × time (+ rollups), L3 site config, L4 user config** | **(b)**, owner-defined | One place for every datum; see [Data Layers](#data-layers) |
| 11 | Instrument-level history | (a) validity ranges (`valid_from`/`valid_to`) · (b) **full snapshot per date** · (c) latest only | **(b)** | Simple and idempotent; point-in-time reads; diffs become `reference_change` events |

---

## Context / Current State

| Area | Today | Problem |
|---|---|---|
| Backtest data | `data/store.py` reads golden CSVs directly | Breaks ADR 0008; Massive bars would need a second data path |
| Backtest keys | `PriceSeries`, `MarketView`, `Portfolio` keyed by **symbol**, multiplier assumed 1 | Blocks options and futures; inconsistent with storage (`instrument_id`) |
| Layout | `strategies/`, `risk/`, `execution/`, `portfolio/`, `backtest/`, `evaluation/`, `cli/` in the old layout | Two architectures in one repo; import contracts carry both |
| Universe | `services.views.load_universe` hard-codes "production" = active + optionable + {stock, ADR, ETF} | Not configurable; no per-strategy subset; no users |
| Sources | Cboe adapter only; no shared interface; synthetic generator lives in `data/` | Each new vendor would invent its own shape |
| Packaging | One distribution, no lock file | Any app can import any dependency; installs are not reproducible |
| Jobs | None | Phase 6 (backtests from the UI) would need retrofitting |

Measured now: 200 tests in about 13 s, 98.7% coverage, a 24-row strategy baseline, and a
nightly options run of about 15–20 min projected for the full universe.

---

## Goals & Non-Goals

**Goals**
- The code layout matches `docs/architecture.md` §1, and import-linter enforces only the target layers.
- Backtests read bars, reference data and the universe only through `StoreReader`.
- The universe holds every instrument we ingest. Strategies and screeners consume a
  per-user, configurable `Selection` of it, and the selection audit is saved with every run.
- Every run records the resolved config hash and the user, so it can be reproduced.
- **No behaviour change:** the strategy baseline is identical, and liquidity screener
  output on a recorded fixture is identical.

**Non-Goals**
- No new vendors (Massive, earnings), new features or the VRP scanner. Those are phases 1–3.
- No HTTP API, auth, web UI or job queue infrastructure (phases 4–6).
- No multi-tenant security. Phase 0 user identity is a label for namespacing, not authentication.

---

## Requirements

### Functional
1. `apps/backtest` provides the current `algotrade` CLI (`datasets`, `backtest`, `evaluate`), now reading from a store.
2. `apps/ingestion` gains a `golden` job that loads the committed golden CSVs into a fixture store through the `synthetic` source.
3. Storage implements the four data layers' market tables needed now (`bars/1d`, `instruments/reference`, `rollups/instrument/*`, `events/*` schema), with contract tests on both backends.
4. A `Selection` can filter on reference fields (security type, exchange, ETF flags, optionable, status) and on any registered feature column, with `all`/`any`/`not` groups.
5. Configs resolve as **built-in defaults < L3 site config < L4 user config < run-time overrides**, into an immutable `ResolvedConfig` with a SHA-256 hash.
6. Every screen and backtest run takes a `UserContext`; results and run records carry `user_id` and `config_hash`.
7. `services.jobs.submit(kind, params, user)` returns a job id; `status` / `result` work with the local runner. The CLIs use it.

### Non-functional

| NFR | Target |
|---|---|
| Behaviour preservation | Strategy baseline matches within `rel_tol=1e-6, abs_tol=1e-9` (the existing gate); liquidity screener rows identical |
| Test suite runtime | ≤ 60 s locally and in CI (today 13 s) |
| Golden evaluation (3 strategies × 8 datasets) from the store | ≤ 5 s (today ~1 s from CSV) |
| Selection evaluation, 10k instruments × 10 rules | ≤ 1 s |
| Config resolution | deterministic: the same inputs always give the same hash, on every OS |
| Nightly options pipeline | unchanged, ≤ 25 min for ~4.2k underlyings |
| Code quality gates | unchanged: no file > 1000 lines, coverage ≥ 90%, strict mypy, every import contract kept |
| Reproducible installs | `uv.lock` committed; CI fails if `uv lock --check` fails |

---

## Proposed Solution

Do it as a sequence of small PRs. Each one keeps CI green and auto-merges, and the
baseline gate proves nothing changed:

1. pure moves into the target layout
2. instrument keys
3. storage-backed backtests
4. the config and selection layer
5. jobs
6. packaging

The only new concepts are **Selection**, **Config** and **UserContext**. Everything else
relocates existing code to the place the architecture already defines.

## Data Layers

All data and configuration lives in **four layers**. Each layer has one definition, one
owner, one format and one way to read it. Everything in phases 0–6 fits one of them.

```
 ┌───────────────────────────────────────────────────────────────────────────────────────┐
 │ L4  USER CONFIG   config/users/<user_id>/*.toml       per user · selections, strategy   │
 │                   (ConfigStore; DB later)              configs, watchlists, preferences  │
 ├───────────────────────────────────────────────────────────────────────────────────────┤
 │ L3  SITE CONFIG   config/site/*.toml (+ overrides/*.csv)   shared · universe coverage,  │
 │                   reviewed via PR, versioned by git        sources, defaults, presets    │
 ╞═══════════════════════════════════════════════════════════════════════════════════════╡
 │ L1  INSTRUMENT    instruments/reference         what each instrument IS (sourced facts) │
 │                   rollups/instrument/<name>@vN   what we KNOW about it now (derived)     │
 │                   → read together as InstrumentView(as_of=D)                           │
 ├───────────────────────────────────────────────────────────────────────────────────────┤
 │ L2  INSTRUMENT ×  bars/<interval>       OHLCV at 1m · 5m · 1h · 1d                      │
 │     TIME          chains/*              option-chain snapshots (instrument × contract)  │
 │                   events/<type>         earnings, splits, dividends, renames, index Δ   │
 │                   rollups/daily/<name>@vN   intraday → one row per instrument per day   │
 └───────────────────────────────────────────────────────────────────────────────────────┘
   L1 and L2 are market data: global, written only by apps/ingestion, Parquet, point-in-time.
   L3 and L4 are configuration: TOML, read by services, resolved into a hashed ResolvedConfig.
   Below the layers sits plumbing (raw vendor responses, run records); above them sit
   outputs (screen and backtest results, per user).
```

### L1: Instrument level (one row per instrument, as of a date)

Two physical parts, always read together:

| Part | Holds | Examples | Changes | Written by |
|---|---|---|---|---|
| `instruments/reference` | **sourced facts**: identity, company, classification, contract terms | ticker, FIGI, company name, website, description, sector/industry, country, exchange, security type, ETF flags (leveraged, inverse, leverage, tracks), optionable, multiplier, tick size, listing status, listed/delisted dates | rarely | universe and reference ingestion jobs |
| `rollups/instrument/<name>@vN` | **derived state** "as of D", computed from L2 | next earnings date + time + days to it, ADV (20d $), liquidity class ("highly liquid"), option liquidity tiers, market cap, 52-week high/low, HV20/30, IV30 and IV rank | nightly | features/rollup jobs |

- **Format and history:** Parquet, **one full snapshot per date** (≈10k rows, < 1 MB/day).
  Reading "as of D" returns the latest snapshot on or before D, so a 2025 backtest sees
  2025's company names, listings and delistings. Validity ranges (`valid_from`/`valid_to`)
  are *derived* from snapshots if ever needed; they are not stored.
- **Changes become events.** The nightly job diffs today's reference snapshot against the
  previous one and writes `events/reference_change` rows (renames, delistings, type changes).
- **Definitions live in site config.** A label such as "highly liquid" is a rollup whose
  thresholds come from `config/site/rollups.toml`, so the definition is explicit,
  versioned and auditable, never hard-coded.
- **Not in L1:** option and futures *contracts*. There are 1M+ option series; their terms
  (underlying, expiry, strike, right, standard/adjusted) live in the OSI symbol and on
  each chain row in L2. Futures get `instruments/futures_contracts` when they arrive (phase 6).
- **Stable id.** `instrument_id` is `EQ:<ticker>` in phase 0 (interim, as today). Phase 1
  switches to an id that survives renames and ticker reuse (FB → META): the FIGI from
  reference data, plus `instruments/symbol_history` mapping ticker → id over time. Every
  table is already keyed by `instrument_id`, so this is a mapping change, not a schema change.

### L2: Instrument × time (values)

| Table | Grain (one row is…) | Interval | Notes |
|---|---|---|---|
| `bars/<interval>` | instrument × bar start | `1d` (phase 1), `1h`/`5m`/`1m` later | OHLCV + VWAP, **unadjusted**; splits and dividends applied at read time from `events` |
| `chains/option_quotes`, `chains/underlying_quotes`, `chains/status` | contract (or underlying) × snapshot | end of day | already implemented (Cboe) |
| `events/<type>` | instrument × event time | irregular | `earnings`, `split`, `dividend`, `reference_change`, `index_change` |
| `rollups/daily/<name>@vN` | instrument × session | daily | rolls intraday bars up to a day: session OHLCV, VWAP, intraday range, opening gap |

**Roll-up chain.** Each step is a versioned, pure definition (in `features/`), recomputed
nightly and stored point-in-time:

```
bars/1m ──► rollups/daily/session_stats@v1 ──┐
bars/1d ─────────────────────────────────────┼─► rollups/instrument/price_stats@v1   (52w hi/lo, MAs, HV, ADV)
chains/* ────────────────────────────────────┼─► rollups/instrument/option_liquidity@v1, iv_history@v1
events/earnings ─────────────────────────────┴─► rollups/instrument/earnings@v1     (next date, days to it)
```

- **Official daily bars win.** The vendor's `1d` bar (official close, including the closing
  auction) is the source of truth. A daily bar rolled up from `1m` bars is a cross-check,
  never a substitute.
- **Today's `features/option_liquidity@v1` becomes `rollups/instrument/option_liquidity@v1`.**
  The code package stays `features/`, because a feature is a rollup definition. Only the
  table prefix changes.

### L3: Site configuration (shared, reviewed)

```
config/site/
  universe.toml          coverage: which instruments we ingest (all US-listed stocks, ADRs, ETFs incl.
                         leveraged/inverse; test issues excluded). The UNIVERSE is coverage, not a filter.
  sources.toml           enabled vendors, schedules, rate limits, raw retention days
  rollups.toml           default parameters for rollups (e.g. liquidity-class thresholds)
  defaults.toml          backtest defaults (cash, costs, risk limits), screening coverage threshold
  presets/selections/*.toml    shared selections, e.g. liquid_optionable
  presets/strategies/*.toml    shared strategy/screener configs, e.g. vrp_default
  overrides/leveraged_etfs.csv curated reference corrections (leverage, inverse, tracks)
```

Owner: the repo (changes by PR, recorded by git commit). Read by ingestion (universe, sources,
rollups) and services (defaults, presets).

### L4: User configuration (per user)

```
config/users/<user_id>/          git-ignored locally; a DB behind ConfigStore later
  selections/*.toml      the user's own subsets (narrow a preset, or replace it)
  strategies/*.toml      strategy and screener configs: impl + params + selection + schedule + outputs
  watchlists/*.toml      named instrument lists (a selection by explicit ids)
  preferences.toml       export directory; later notifications and UI settings
```

**Resolution order:** built-in defaults < L3 site defaults and presets < L4 user config
< run-time overrides, into one immutable `ResolvedConfig` whose SHA-256 hash is stored with
every run. A user can select from the site universe but cannot widen it. Covering a new
instrument is a site change (or, in phase 6, an on-request ingestion job).

### Where does a new piece of data go?

| Question | Layer / table |
|---|---|
| Is it a fact about what the instrument is, from a vendor? | L1 `instruments/reference` |
| Is it a number derived from history, and true "as of" a day? | L1 `rollups/instrument/*` (or L2 `rollups/daily/*` if per session) |
| Does it have a value per bar or per snapshot? | L2 `bars/*` or `chains/*` |
| Did it *happen* at a point in time? | L2 `events/*` |
| Is it a choice everyone shares? | L3 `config/site` |
| Is it one user's choice? | L4 `config/users/<id>` |

Full column lists: [Appendix C](#appendix-c).

---

## High-Level Design

### Existing Architecture

```
src/algotrade/  cli → evaluation → backtest → {strategies, risk, execution, portfolio, analytics, data} → core
                services → engines/screening → strategies/screeners → core
                storage, features (new layout)
apps/ingestion/algotrade_ingestion  (separate top-level package, same distribution)
```

### Target after phase 0

```
apps/
  ingestion/   pyproject.toml  algotrade_ingestion/
                 sources/{base, http, cboe, synthetic}   ← Source protocol + adapters
                 jobs/{universe, option_chains, features, golden}
                 pipeline.py  cli.py                     (only importer of storage.writers)
  backtest/    pyproject.toml  algotrade_backtest/{cli, commands}   ← today's src/algotrade/cli
src/algotrade/ pyproject.toml  (shared library; no vendor SDKs, no web framework)
  core/        instruments (Instrument, AssetClass, ids), series, market_view, feature_view,
               options, types (Order, Fill keyed by instrument_id), time, errors
  config/      NEW. schema (StrategyConfig, Selection, Rule), resolve (layering + hash),
               catalog (selectable fields), user (UserContext). Pure: no I/O.
  storage/     schemas (+ bars, instruments/reference, rollups, events), interfaces (+ bar,
               instrument and ConfigStore reads), readers, writers, result_writer, runs,
               backends/{local, memory}
  features/    option_liquidity@v1, registry
  strategies/  trading/{base, buy_and_hold, sma_crossover, zscore_mean_reversion, registry}
               screeners/{base, short_premium_liquidity, registry}
  engines/     backtest/{engine, config, result, simulated, costs, portfolio, limits, sizing}
               screening/{runner}
               selection/{evaluate}   ← applies a Selection to a FeatureView, with a per-rule audit
  analytics/   metrics, report
  services/    backtests, screening, evaluation (from evaluation/), selection, views,
               exports, configs (load + resolve via ConfigStore), jobs/{models, local_runner}
config/        site/ (L3, reviewed via PR) and users/<user_id>/ (L4, git-ignored locally)
```

Removed: `src/algotrade/{data, backtest, risk, execution, portfolio, evaluation, cli}`
(contents moved as above; `data/validation.py` moves into `storage/schemas.py`).

### Layering (import-linter)

```
apps/*  (never import each other)
  ↓
services
  ↓
engines (backtest · screening · selection)
  ↓
strategies (trading · screeners) · features · analytics
  ↓
storage · config
  ↓
core
```

Extra contracts:
- strategies and screeners import only `core` (+ `config` types)
- `features` and `config` do no I/O
- only `algotrade_ingestion` imports `storage.writers`
- the library never imports apps

### Storage Choices

| Data | Store | Why | Rejected |
|---|---|---|---|
| Bars (1d now, intraday later) | `bars` table: Parquet partitioned by session date, sorted by `instrument_id` | Same backend as chains; DuckDB-readable; one schema for every interval | One file per ticker (too many files at 10k instruments); SQLite (row store, slow scans) |
| Instrument level (L1) | `instruments/reference` + `rollups/instrument/*`, one snapshot per date | Point-in-time (renames, delistings, changing earnings dates); one view for selections, the UI and multipliers | Validity-range rows (harder to write idempotently); columns on the universe table (mixes "what exists" with "what is selected") |
| Golden fixtures | committed CSV → loaded by the `synthetic` source into `datasets/golden/store` (git-ignored, rebuilt by `make golden-store`) or a memory store in tests | Reviewable source data; production code path | Committed Parquet (binary diffs); keeping the CSV reader (second code path) |
| Configs (L3, L4) | `ConfigStore` protocol; file backend reads `config/site` and `config/users/<id>` | Hand-editable now; the DB/API backend in phase 4 implements the same protocol | Configs in Parquet tables (awkward to edit); env vars (not structured) |
| Results, run records | existing tables + new `user_id`, `config_id`, `config_hash` columns | Namespacing without new stores | Separate store per user (duplicates market data) |

No cache: everything is local disk, and the working set is small (see
[Appendix B](#appendix-b)).

### Key Design Decisions

**D1. uv workspace now.**

| Option | Latency | Cost | Complexity | Operability |
|---|---|---|---|---|
| Keep one distribution | — | 0 | low | apps can silently depend on anything |
| **uv workspace** | faster installs | 0 | medium: new tool locally (`brew install uv`) and in CI | per-app dependencies, lock file, `uv run` everywhere |
| Separate repos | — | 0 | high: cross-repo releases | painful for one owner |

Accepted: one new tool, plus a CI rewrite of the install steps. The ADR 0014 deferral
ends because phase 4 (FastAPI) would force it anyway.

**D2. Selection = typed rules, not code.** User configs, and later UI-built configs,
must be safe to evaluate and explain. Callables cannot be stored or audited; SQL strings
invite injection and couple us to DuckDB. Typed rules are validated against a catalogue
and produce a per-rule count ("passed security type: 9,812; passed ADV: 1,204; …"), which is
the audit the VRP spec asks for. Cost: a small evaluator (~150 lines) and less
expressiveness. Complex logic belongs in a feature, not in a rule.

**D3. Global data, per-user decisions.** Ingestion and features run once for the whole
universe; selections, parameters, results and jobs are per user. Alternative (a) multiplies
ingestion cost by the number of users and lets their data disagree. Alternative (c) bakes
"single user" into every service signature, which is exactly what we would have to undo.

**D4. Separate fixture store for golden data.** Mixing synthetic instruments into the real
store risks collisions (`AAA` is a real ETF ticker) and accidental use in real screens. A
separate URL makes contamination impossible by construction.

---

## Deep Dive

### Critical Path: a backtest after phase 0

```
algotrade-backtest backtest --config sma_trend --user local
  → services.configs.resolve("sma_trend", user)                      → ResolvedConfig (hash)
  → services.selection.select(reader, cfg.selection, session=start)  → instruments + audit
  → reader.bars(instruments, "1d", start, end, as_of)                → aligned PriceSeries (by instrument_id)
  → reader.instruments(instruments, as_of=start)                     → InstrumentView (multipliers, flags)
  → engines.backtest.run(series, strategy(cfg.params), cfg.backtest) → BacktestResult
  → result_writer.write_result("backtests", ...) + RunRecord(user, config_hash, dataset versions)
```

Budget for the golden suite (24 runs): store reads about 30 ms per dataset, engine about
20 ms per run, so about 1 s in total, against a 5 s target.

**Survivorship rule:** selection is evaluated as of the backtest's **start** date (and
re-evaluated at each `rebalance_selection` interval if configured), never with today's
universe.

### Data Model

**`bars`** (grain bar(interval)). Key: (`instrument_id`, `interval`, `ts`).

| Column | Type | Notes |
|---|---|---|
| instrument_id | str | `EQ:AAPL` |
| interval | str | `1d` now |
| ts | timestamp UTC | bar start |
| session_date | date | exchange trading day |
| open, high, low, close | float64 | **unadjusted** (corporate actions applied at read time, from events in phase 1) |
| volume, vwap | float64 | vwap nullable |
| + common | | `knowledge_ts`, `source`, `run_id` |

**`instruments/reference`** (L1). One snapshot per date; key (`instrument_id`, `session_date`).
Phase 0 ships the columns needed now (identity, classification, contract terms, ETF flags,
status, optionable); company fields arrive with phase 1 sources. Full list:
[Appendix C](#appendix-c).

The **universe** table becomes "every instrument we cover on date D" (the coverage defined
in `config/site/universe.toml`). Filtering moves out of `load_universe` into selections.

**Config objects** (`config/schema.py`, frozen dataclasses):

```text
Rule        { field: str, op: eq|ne|in|not_in|gt|gte|lt|lte|between|is_null|not_null, value }
Group       { all: [Rule|Group] } | { any: [Rule|Group] } | { not: Rule|Group }
Selection   { name, base: "universe", where: Group, max_instruments?: int, order_by?: field }
StrategyConfig { id, kind: "screener"|"strategy", impl: registry name, params: {..},
                 selection: Selection | ref, backtest?: {initial_cash, costs, limits},
                 outputs?: {exports: [...]}, schedule?: "nightly" }
ResolvedConfig { config: StrategyConfig, layers: [sources...], hash: sha256(canonical json) }
UserContext    { user_id: str }   # phase 0: plain label from --user / ALGOTRADE_USER, default "local";
                                  # identity scheme deliberately deferred
```

Example site preset `config/site/presets/selections/liquid_optionable.toml`:

```toml
name = "liquid_optionable"
[where]
all = [
  { field = "instrument.security_type", op = "in", value = ["COMMON_STOCK", "ADR", "ETF"] },
  { field = "instrument.status", op = "eq", value = "ACTIVE" },
  { field = "instrument.optionable", op = "eq", value = true },
]
```

Example user config `config/users/abhinav/strategies/short_premium.toml`:

```toml
id = "short_premium"
kind = "screener"
impl = "short_premium_liquidity"
selection = "liquid_optionable"          # preset by name...
[selection_overrides]                    # ...narrowed by user rules (AND-ed)
all = [ { field = "instrument.is_leveraged", op = "eq", value = false } ]
```

**Field catalogue:** `instrument.<column>` for L1 reference columns, plus
`rollup.<name>@vN.<column>` for every registered rollup (for example
`rollup.option_liquidity@v1.put_tier`), with types. Unknown fields or type mismatches fail when the config
loads, with the TOML path in the error.

### API Design (service interfaces; HTTP comes in phase 4)

```python
services.configs.resolve(config_id: str, user: UserContext, overrides: dict | None = None) -> ResolvedConfig
services.selection.select(reader, selection: Selection, session: date, as_of: datetime | None = None) -> SelectionResult
    # SelectionResult(instruments: tuple[str, ...], audit: list[RuleAudit(rule, passed, failed, unknown)])
services.screening.run_screener(reader, writer, config: ResolvedConfig, user, session) -> ScreenOutcome
services.backtests.run_backtest(reader, writer, config: ResolvedConfig, user, start, end) -> BacktestOutcome
services.jobs.submit(kind: str, params: dict, user: UserContext) -> JobId
services.jobs.status(job_id) -> JobStatus          # queued | running | complete | partial | failed
services.jobs.result(job_id) -> RunRecord
```

Errors stay typed: `ConfigurationError` (bad config, with the field path),
`MissingDataError` (with the ingestion hint) and `DataValidationError`. The phase 4 HTTP
layer maps them to 422, 409 and 500.

### Consistency & Concurrency Model

- **Writers:** only the ingestion app writes market and feature data. Partitions are
  written atomically (temp file + rename); a run replaces only its own partition.
- **Readers** pick the latest run with `knowledge_ts ≤ as_of`. A reader racing a writer
  sees either the old or the new run, never a mix.
- **Configs** are read once per run, and the hash is recorded. Editing a config mid-run
  affects only later runs.
- **Jobs** (local runner): a thread pool of 2 by default. The same `(kind, config_hash,
  session)` submitted twice returns the existing job id (idempotent).
- **Users:** results are namespaced by `user_id`. Market data and features are shared and
  read-only to everyone except ingestion.

### Business Workflows

**W1. Nightly** (unchanged order; screening becomes per user × config):

```
ingestion: universe → chains → features
  → for each (user, config) with schedule = "nightly": select → screen → save results + exports
```

Decision: screens run inside the ingestion pipeline (they only read data) but go through
`services`, so the API can trigger the same thing in phase 4.

**W2. Strategy evaluation** (CI baseline): `make evaluate` → for each golden dataset
preset, a selection naming that dataset's instruments → backtest each registered strategy
→ compare with `benchmarks/baseline.json`. Baseline keys stay `strategy@dataset`.

**W3. A user creates a strategy subset:** add `config/users/<id>/strategies/x.toml` (L4) →
`algotrade-backtest config validate x` → `… backtest --config x` or include it in the nightly
run. In phase 4 the UI writes the same object through `ConfigStore`.

---

## Failure Modes

| Component | Failure | Detection | Recovery | User impact |
|---|---|---|---|---|
| Config load | invalid TOML, unknown field, wrong type | `ConfigurationError` with file and field path at load | fix the file; nothing runs on a bad config | the run refuses to start (fail closed) |
| Selection | matches 0 instruments | `SelectionResult.empty`; coverage status `EMPTY_SELECTION` | review the rules (the audit shows which rule removed everything) | no results, clearly labelled |
| Selection | references a feature not computed for the session | values `UNKNOWN`; rule audit counts them | run the features job; the instrument is excluded, never included | fewer candidates, visible in the audit |
| Backtest data | bars missing for a range | `MissingDataError` naming the ingestion command | run the ingestion backfill | backtest refuses to run |
| Golden fixture store | stale versus committed CSVs | checksum manifest compared on load | `make golden-store` | CI fails loudly |
| Packaging | lock drift | `uv lock --check` in CI | `uv lock` + PR | CI fails |
| Jobs runner | process exits mid-job | job record stays `running` past its timeout | marked `failed` on next start; re-submit (jobs are idempotent) | re-run needed |

---

## Security & Privacy

- **Auth / authz:** none in phase 0. `UserContext` comes from `--user` / `ALGOTRADE_USER`
  and is a namespace, not an identity; documented as such. Phase 4 maps authenticated users
  to `user_id`, and **services** enforce that a user reads and writes only their own
  configs, results and jobs.
- **PII:** none stored. User ids are opaque labels.
- **Threats and mitigations:**
  1. Malicious config: typed rules only, no code or SQL evaluation.
  2. Path traversal through a user id or config id: ids validated as `[a-z0-9_-]{1,64}`.
  3. Secrets in configs: forbidden (rule documented, plus a lint check for key-like field names); credentials only via env.
  4. One user reading another's results: namespacing now, enforced in services in phase 4.
- **Compliance:** n/a (personal research tool). Vendor terms are tracked in `docs/data/vendors.md`.

---

## Scale & Reliability

**Load estimation** (details in [Appendix B](#appendix-b)): bars for about 10k instruments ×
252 days ≈ 2.5M rows a year, about 60–80 MB as Parquet. Selections over 10k rows take
milliseconds. Per-user screening costs about 1–3 s per config (feature reads dominate), so
20 users × 5 nightly configs ≈ 5 min extra a night.

**Scaling strategy:**
- Single machine, stateless services over file storage.
- Shared work (ingestion, features) is O(universe); per-user work is O(users × configs) and cheap.
- Backtests are the only heavy per-user job, and they queue through `services/jobs`.

**Failover:** n/a locally. RPO is the last nightly run, because raw responses (90 days) and
normalized tables allow a rebuild. RTO is about 30 min (re-run the nightly job).

**Monitoring** (stored in run records for now, surfaced in the UI later):
- run status by job
- coverage % per screen (alert below 98%)
- selection sizes per config (alert on a > 20% day-over-day change)
- nightly duration (alert above 40 min)
- `uv lock --check` result

---

## Infrastructure & Hosting

Local only (macOS), and unchanged by phase 0: Python 3.12 via uv, storage under
`ALGOTRADE_DATA_URL` (default `file://./var/data`), configs under `ALGOTRADE_CONFIG_DIR`
(default `./config`). Hosting later needs no redesign: storage moves to an `s3://`
backend, `ConfigStore` moves to a DB backend, and jobs move to a queue. Those are phases 4–6.

---

## Execution & Rollout Plan

Each step is one PR. All auto-merge when green. **The baseline gate is the rollback
trigger**: any diff in `benchmarks/baseline.json`, or in the liquidity screener fixture
output, blocks the PR.

| # | PR | Definition of done |
|---|---|---|
| 0.1 | **Moves only:** `strategies/*` → `strategies/trading/`; `backtest, risk, execution, portfolio` → `engines/backtest/`; `evaluation` → `services/evaluation`; import updates; old contracts replaced by target layers | baseline identical; contracts kept; no logic diff (`git diff -M` shows renames) |
| 0.2 | **Instrument keys:** `Instrument` in core; `PriceSeries`, `MarketView`, `Order`, `Fill`, `Portfolio` keyed by `instrument_id`; `Portfolio` uses `multiplier`; `MarketView.symbols` kept as an alias | baseline identical; property tests pass; a multiplier test covers 100× options P&L |
| 0.3 | **Storage-backed backtests and data layers:** `bars/1d`, `instruments/reference`, `rollups/*`, `events/*` schemas + `InstrumentView` read API, contract tests; `features/option_liquidity@v1` table renamed `rollups/instrument/option_liquidity@v1`; `synthetic` source + `golden` ingestion job; evaluation reads from the fixture store; delete `data/` | baseline identical; `make golden-store` reproducible; the CSV checksum test still passes |
| 0.4 | **Source interface:** `sources/base.py` protocol; Cboe and synthetic implement it | ingestion tests unchanged |
| 0.5 | **Config + selection + users:** `config/` package, `config/site` (L3) and `config/users` (L4) layout, field catalogue, evaluator with audit, `ConfigStore` file backend, a site preset reproducing today's "production" filter; screening takes `ResolvedConfig` + `UserContext`; results carry `user_id` and `config_hash` | liquidity screener output identical on the recorded fixture; selection property tests (rule order does not change the result; `not` is the complement) |
| 0.6 | **Jobs:** `services/jobs` models + local runner; both CLIs submit through it | same CLI output; idempotent re-submit test |
| 0.7 | **uv workspace:** split into `algotrade`, `algotrade-ingestion`, `algotrade-backtest`; `uv.lock`; CI on `uv`; Makefile targets unchanged | CI green on 3.12 / 3.13; `uv lock --check` in CI |
| 0.8 | **Docs:** ADR 0015 (configs, selections, users), ADR 0013 amended (universe = everything; strategies select), ADR 0014 amended (workspace done), `architecture.md` §2 removed (no more "current vs target") | doc consistency tests pass |

**Feature flags / canary:** not needed. These are refactors behind an exact-output gate, on
a single-user local system.

**Success metrics:**
- the baseline diff is empty at every step
- after 0.8, `docs/architecture.md` has one architecture, not two
- phase 1 (Massive bars) needs **zero** changes to engines or strategies

---

## Open Questions

| Question | Owner | Decision Needed By | Resolution |
|---|---|---|---|
| Approve uv workspace now (D1), with `brew install uv` needed locally? | @adarbari | before 0.7 | **Yes**, adopt now |
| TOML for config files (decision 6)? | @adarbari | before 0.5 | **Yes**, TOML |
| User id scheme: free-form label now (e.g. `abhinav`), mapped to auth later? | @adarbari | before 0.5 | **Keep it simple:** a plain validated label (default `local`); the real identity scheme is out of scope for phase 0 |
| Should repo presets be per-user-overridable only by narrowing (AND), or also by replacement? Draft: both, via `selection_overrides` (narrow) or a full `selection` (replace) | @adarbari | before 0.5 | **Both.** Narrowing (preset rules + user rules) is the default and inherits later preset improvements; replacing is the explicit escape hatch. The run audit records which was used |
| Keep the `algotrade` command name for the backtest app, or rename it to `algotrade-backtest`? Draft: rename, keeping `algotrade` as an alias for one phase | @adarbari | before 0.1 | **Rename** to `algotrade-backtest` (matches `algotrade-ingest`, `algotrade-api`); `algotrade` stays as an alias through phase 1 |

---

## Appendix

<a id="appendix-a"></a>
### Appendix A: Phase 1 dependencies this design unblocks

| Phase 1 item | Lands on |
|---|---|
| Massive daily bars | a new `sources/massive.py` writing the `bars` table (0.3); backtests and features read it unchanged |
| Earnings calendar (Nasdaq) | `events` grain + `sources/nasdaq_earnings.py`; selections can use `features.earnings.days_to_next` |
| Universe builder (Nasdaq Trader + SPY) | writes `instruments/reference` + `universe` (coverage per `config/site/universe.toml`) + `events/index_change`; strategies keep using selections |
| Company details (website, description, sector) | `instruments/reference`; sources: SEC EDGAR (free, US filers) and Massive ticker details (rolling refresh) |
| Stable instrument ids | FIGI-based `instrument_id` + `instruments/symbol_history` |
| IV history | a feature over `chains/underlying_quotes.iv30` history; selectable like any feature |

<a id="appendix-b"></a>
### Appendix B: Load estimates

| Item | Math | Result |
|---|---|---|
| Daily bars per year | 10,000 instruments × 252 sessions | 2.52M rows ≈ 60–80 MB Parquet (zstd, ~30 B/row) |
| Two-year backfill | 2 × above | ≈ 5M rows, ≈ 150 MB |
| Reference snapshot | 10,000 rows × 20 columns daily | < 1 MB/day |
| Selection eval | 10k rows × 10 vectorised predicates | ~10 ms |
| Per-user nightly screens | 20 users × 5 configs × ~2 s | ≈ 3–5 min |

<a id="appendix-c"></a>
### Appendix C: Instrument-level (L1) columns

**`instruments/reference`** (sourced facts; one snapshot per date)

| Group | Columns | Source (phase) |
|---|---|---|
| Identity | `instrument_id`, `symbol`, `figi` (1), `cik` (1) | Nasdaq Trader (0/1), Massive / OpenFIGI (1) |
| Company | `name`, `description` (1), `website` (1), `sector` (1), `industry` (1), `country` (1) | SEC EDGAR, Massive ticker details (1) |
| Classification | `asset_class`, `security_type` (COMMON_STOCK, ADR, ETF, ETN, PREFERRED, WARRANT, UNIT, RIGHT, CEF), `exchange`, `currency` | Nasdaq Trader |
| Contract terms | `multiplier`, `tick_size`, `round_lot` | derived per asset class |
| ETF attributes | `is_etf`, `is_leveraged`, `is_inverse`, `leverage`, `tracks` | Nasdaq Trader ETF flag + `config/site/overrides/leveraged_etfs.csv` |
| Options | `optionable` | Nasdaq Trader `options.txt` |
| Status | `status`, `listed_on`, `delisted_on`, `is_test_issue` | Nasdaq Trader, Massive |
| Lineage | `session_date`, `knowledge_ts`, `source`, `run_id` | ingestion |

**`rollups/instrument/*`** (derived "as of D"; one table per rollup, versioned)

| Rollup | Columns | Inputs | Phase |
|---|---|---|---|
| `option_liquidity@v1` | put/call tiers, target expiry, spreads, zone OI, chain OI | `chains/*` | done (renamed in 0.3) |
| `price_stats@v1` | `close`, `sma_20/50/200`, `ret_20d/60d`, `high_52w`, `low_52w`, `pct_from_high/low`, `hv20`, `hv30`, `adv_usd_20d` | `bars/1d` + split events | 1–2 |
| `liquidity_class@v1` | `liquidity_class` (HIGH/MEDIUM/LOW) with the thresholds used | `price_stats`, `option_liquidity`, `config/site/rollups.toml` | 2 |
| `iv_history@v1` | `iv30`, `iv_rank_252d`, `iv_percentile_252d`, `history_days` (UNKNOWN below the minimum) | `chains/underlying_quotes` history | 2 |
| `earnings@v1` | `next_earnings_date`, `earnings_time` (pre/post), `days_to_earnings`, `date_confirmed` | `events/earnings` | 1–2 |
| `fundamentals@v1` | `market_cap`, `shares_outstanding` | Massive / EDGAR | 2 |

