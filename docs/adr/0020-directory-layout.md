# ADR 0020: Directory layout: one kind of thing per folder

**Status:** implemented (accepted 2026-10-03; Layout PR A: the ingestion app. Layout PR B: the library).
Extends [0019](0019-ownership-and-boundaries.md). Registry: `architecture/layout.toml`.

## Context
ADR 0019 gave every responsibility one owning module, but said nothing about where modules
live. `apps/ingestion/algotrade_ingestion/tasks/` held 18 modules: registered tasks, their
private helpers and the run machinery side by side. `sources/` mixed the source framework
(protocols, HTTP, pacing, registry) with vendor adapters and the golden fixture source, and
one 269-line `massive.py` served three datasets. A new module had no rule saying where it
goes, so folders grew by accretion. In the library, `core/` held 12 modules (value objects,
calendar, strategy-facing views and OHLCV checks side by side), `config/` mixed site settings
with strategy configs, `storage/` mixed table contracts with config documents, and
`services/` mixed use cases with the helpers they share.

## Decision
- **One folder holds one kind of thing**, and `architecture/layout.toml` declares every
  directory under `src/` and `apps/` with a one-line purpose. A module in an undeclared
  directory fails `tests/architecture/test_layout.py`; adding a folder means declaring it
  (`.claude/skills/add-responsibility`).
- **At most 10 modules per directory** (excluding `__init__.py`); split by kind. Layout PR A
  listed the oversized `core/` as an `[[exception]]`; Layout PR B split it, and a fitness
  test keeps `[[exception]]` absent: an oversized folder is split, never excused.
- **A declaration may name the import-linter contracts that enforce its rule**
  (`contracts = [...]`); the layout test fails if a named contract does not exist.
- **Every package's `__init__.py` docstring says what the folder holds.**
- **Ingestion app:** `cli/`, `ops/`; `sources/framework/` (non-vendor machinery),
  `sources/vendors/<vendor>/` (one folder per vendor), `sources/fixtures/`;
  `tasks/framework/` (`IngestRun`, the task registry) and `tasks/<domain>/` (`reference`,
  `market`, `derived`, `maintenance`); `workflows/nightly/`. Task, source and CLI names do
  not change.
- **Library (`src/algotrade/`, Layout PR B):** `core/` splits into `model/` (types,
  instruments, options, fields, ids, errors), `time/` (`calendar.py`, `clock.py`: was
  `core/time.py`; a module and a package cannot share a name), `views/` (`market_view`,
  `feature_view`, `series`: what strategies see) and `validation/` (`bars.py`). `config/`
  into `site/` (`settings.py`, `fields.py`: was `settings_fields.py`) and `strategy/`
  (`schema`, `resolve`, `catalog`), keeping `env.py` and `user.py`. `storage/` into `tables/`
  (`interfaces`, `readers`, `writers`, `schemas`, `result_writer`), `backends/` (`local`,
  `memory`, `arrow`, `run_selection`: was `selection.py`) and `configs/` (`store.py`: was
  `config_store.py`; `files.py`: was `backends/config_files.py`), keeping `runs`, `locks`,
  `factory`. `services/` gains a package per use case, `backtests/` (`run.py`) and
  `screening/` (`run.py`, `exports.py`); helpers shared by several use cases (`configs`,
  `datasets`, `selection`, `views`) stay at `services/`. Package `__init__` files keep their
  curated exports (`algotrade.core`, `algotrade.config`, `algotrade.storage`); there are no
  re-export shims for old module paths.
- **Library folder rules (import-linter):** every `core/*` package is pure (no pandas,
  pyarrow, storage, config or data); `core.model` and `core.time` never import `core.views` /
  `core.validation`; `storage.configs` never imports `storage.tables` / `storage.backends`,
  nor the reverse (config documents and market tables stay separate); pyarrow only in
  `storage.backends` (now also checked for the rest of `storage/` and `data/`);
  `config.site` never imports `config.strategy`; the `backtests` and `screening` use-case
  packages are independent. Strategies already use `core.model` (errors, target weights) as
  well as `core.views`, so they keep the existing rule (they see only `core`).
- **Vendor folders** each register at least one source in `sources/framework/registry.py`,
  and only that registry imports them. Vendors never import each other (import-linter
  `independence`), nor `tasks`, `workflows`, `cli` or `ops`; tasks never import
  `sources.vendors` (R3).
- **Task domains** hold registered tasks and private helpers; a module is imported only
  within its domain or by the task registry. `[[shared]]` lists reasoned exceptions (today:
  `reference/instrument_ids.py`, the ingestion id rule of ADR 0018, used by `golden` and
  `migrate-ids`); the test fails when a listed module stops being shared.

## Consequences
- Where a new vendor, task or helper goes is decided by the registry, not by taste: the
  `add-data-source` and `add-dataset` skills name the folder.
- Module paths in `architecture/ownership.toml` moved with the code; the ownership ratchet
  stays at zero.
- Layout PR B moved library modules only (no behaviour change; CLI names and the baseline are
  unchanged). Tests mirror the new folders (`tests/unit/core/model/`, ...). Imports name the
  new paths; callers of old module paths fail to import rather than silently resolving.
- No `[[exception]]` remains in `architecture/layout.toml`.
