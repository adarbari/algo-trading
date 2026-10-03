# ADR 0020: Directory layout: one kind of thing per folder

**Status:** accepted (2026-10-03; Layout PR A: the ingestion app. Layout PR B: the library).
Extends [0019](0019-ownership-and-boundaries.md). Registry: `architecture/layout.toml`.

## Context
ADR 0019 gave every responsibility one owning module, but said nothing about where modules
live. `apps/ingestion/algotrade_ingestion/tasks/` held 18 modules: registered tasks, their
private helpers and the run machinery side by side. `sources/` mixed the source framework
(protocols, HTTP, pacing, registry) with vendor adapters and the golden fixture source, and
one 269-line `massive.py` served three datasets. A new module had no rule saying where it
goes, so folders grew by accretion.

## Decision
- **One folder holds one kind of thing**, and `architecture/layout.toml` declares every
  directory under `src/` and `apps/` with a one-line purpose. A module in an undeclared
  directory fails `tests/architecture/test_layout.py`; adding a folder means declaring it
  (`.claude/skills/add-responsibility`).
- **At most 10 modules per directory** (excluding `__init__.py`); split by kind. Today's
  oversized library folders are listed as `[[exception]]` with `until = "layout-pr-b"`, and
  the test fails once one is back under the limit, so the list only shrinks.
- **Every package's `__init__.py` docstring says what the folder holds.**
- **Ingestion app:** `cli/`, `ops/`; `sources/framework/` (non-vendor machinery),
  `sources/vendors/<vendor>/` (one folder per vendor), `sources/fixtures/`;
  `tasks/framework/` (`IngestRun`, the task registry) and `tasks/<domain>/` (`reference`,
  `market`, `derived`, `maintenance`); `workflows/nightly/`. Task, source and CLI names do
  not change.
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
- The library (`src/algotrade/`) is declared as it is today; Layout PR B reorganises it and
  removes the `core/` exception.
