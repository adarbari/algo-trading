# ADR 0019: Ownership and boundaries

**Status:** accepted (2026-10-02). Extends [0001](0001-layered-architecture.md),
[0005](0005-ingestion-is-the-only-writer.md), [0006](0006-storage-grains-and-adapters.md),
[0010](0010-jobs-model.md) and [0018](0018-figi-instrument-ids.md). Registry:
`architecture/ownership.toml`. Work plan: [roadmap](../roadmap.md), track R.

## Context
Layers are enforced (ADR 0001), but nothing stops one responsibility from being implemented
in several modules of the same layer. A review of the code found:

- **The ingest loop** (fetch → raw save → normalise → resolve ids → stamp → write → run
  record) re-implemented in 10 modules of `apps/ingestion/.../jobs/`: `RunRecord` built in
  13 files, COMPLETE / PARTIAL decided in 12.
- **"Latest snapshot on or before D"** at 11 call sites with different fallbacks
  (`latest_date(` in `storage/readers.py`, `services/views.py`, `services/datasets.py`,
  `jobs/quality.py`, `jobs/company_details.py`, `jobs/migrate_ids.py`).
- **Domain reads** split across `storage/readers.py`, `services/views.py` and
  `services/market_data.py`.
- **Source construction, pacing and auth** in `commands.py`; a `MinInterval` per source and
  no limiter shared across workers or processes.
- **Vendor specifics in jobs**: Nasdaq file names in `jobs/universe_build.py`, Massive
  `splits:` / `dividends:` keys in `jobs/bars.py`, SEC helpers in `jobs/company_details.py`.
- **Site settings loaded in three places** (`pipeline.universe_settings`,
  `settings.load_sources`, `services/backtests.backtest_settings`).
- **Ingestion steps run from three entry points** (CLI commands, `pipeline`, the job runner)
  with drifting defaults: `commands.py` hardcodes the corporate-actions window;
  `cboe.workers` and `cboe.enabled` in `config/site/sources.toml` are never read.
- **"jobs" names two concepts**: ingestion step functions and the `services/jobs` runner.

## Decision
Every responsibility has **exactly one owner module**, recorded in
`architecture/ownership.toml` with AST patterns that detect anyone else doing that work.
Before writing code that does X, find X's owner and extend it; a new responsibility gets an
entry and an owner in the same PR. Target layout (moves land in PRs 2–6):

```
src/algotrade/
  core/      pure types (+ calendar.py: exchange sessions)
  config/    + typed site settings (universe, sources, quality, backtest), one loader
  storage/   GENERIC only: backends, partitions, run index, locks, schemas + validation
  data/      the domain read API, the only way to read market data:
             reference.py (one snapshot rule, InstrumentView, universe, resolver),
             prices.py (bars + adjustments), events.py (by event date), chains.py
  features/ engines/ strategies/ analytics/
  services/  use cases; services/jobs is the ONLY executor (locks, recovery, step isolation)
apps/ingestion/
  sources/   vendor adapters only + registry (from sources.toml) + a shared cross-process
             rate limiter; they emit standard frames
  tasks/     (renamed from jobs/) framework.py = IngestRun (the loop, written once) + one
             module per dataset declaring its sources, tables and settings section
  workflows/ nightly as ordered, isolated tasks; exchange-calendar session; screens are
             submitted as `screen` jobs
  cli.py     generic: run <task>, nightly, admin
```

### R1: only data/ reads market data
Consumers (services, engines, apps, tasks) read market data only through `algotrade.data`,
never `storage.readers`. One snapshot rule lives in `data/reference.py`; events are read by
event date. Responsibilities: `snapshot-selection`, `market-data-reads`.

### R2: storage is generic
`storage/` knows partitions, backends, run records, locks, schemas and validation; nothing
about instruments, universes or adjustments. Parquet and Arrow stay in `storage/backends/`
(`parquet-io`).

### R3: tasks get sources from the registry
Tasks never import vendor modules; the source registry builds sources (transport,
credentials, pacing) from `config/site/sources.toml`, and every vendor detail (file names,
request keys, response fields) stays in `sources/`. Responsibilities: `vendor-http`,
`rate-limiting`, `source-construction`.

### R4: sources never import storage
A source fetches and normalises to standard frames; it never writes, reads or stamps.

### R5: everything runs through the job runner
CLI commands, nightly and screens submit jobs to `services/jobs`, the only executor. Nightly
keeps triggering screens, but **submits them as `screen` jobs** (decided). The session date
comes from the exchange calendar. Responsibilities: `ingestion-step-dispatch`,
`job-execution`, `screen-execution`, `session-calendar`.

### The ingest loop is written once
`tasks/framework.py` (`IngestRun`) owns run ids and records, the COMPLETE / PARTIAL
decision, raw persistence, id resolution and point-in-time stamping. Dataset modules declare
what to fetch and how to compose tables. Responsibilities: `run-records`, `raw-persistence`,
`row-stamping`, `id-resolution`.

### Settings and environment
One typed loader in `config/` for site settings (`site-settings`); environment variables are
read in one place (`secrets-env`). Every key in `config/site/*.toml` must drive code.

### Guardrails
| Check | What it enforces | Ratchet |
|---|---|---|
| `make ownership` (`scripts/check_ownership.py`) | detect hits only inside the owner (or its target owner) | `architecture/known_violations.toml`, shrink-only |
| `make dupes` (`scripts/check_dupes.py`) | pylint `duplicate-code` over `src/` and `apps/` | `architecture/dupes_baseline.txt`, must match |
| `make arch` (import-linter) | the rules that already hold as contracts | pending ones: `[[pending_contract]]` in the registry |
| `tests/architecture/test_ownership.py` | one producing owner per table; registry paths exist; site settings are read | `KNOWN_UNREAD`, shrink-only |

Both ratchets fail when a count goes **down** without the file being updated, so fixed
problems cannot come back. Each restructure PR moves code to the target owner, shrinks the
ratchets and enables its pending contracts in `pyproject.toml`.

| Alternative | Rejected because |
|---|---|
| Review discipline only | the duplications above all passed review |
| import-linter only | it sees modules, not responsibilities: ten jobs may legally re-implement one loop |
| Fix everything in one PR | too large to review; the ratchet lets PRs 2–6 land one at a time |

## Consequences
- Adding code that does an owned job outside its owner fails CI with the owner's name and
  this section. Agents find owners in `CLAUDE.md` and `architecture/ownership.toml`; the
  `add-responsibility` skill covers adding or moving one.
- `known_violations.toml` is the restructure's to-do list, per responsibility.
- Detection is heuristic (AST names, not semantics). A false positive is fixed by
  narrowing the detect rule or listing the module in `allowed` with a reason, never by
  growing the ratchet.
