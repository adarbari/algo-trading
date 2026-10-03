# Architecture Decision Records

Each ADR records one decision: its context, the decision and its consequences. To change a
decision, add a new ADR that supersedes the old one, and update the old one's status line.
Do not rewrite history. Use `.claude/skills/write-adr` to add one.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-layered-architecture.md) | Layered architecture enforced by import-linter | accepted |
| [0002](0002-fill-model.md) | Decide at close, fill at next open | accepted |
| [0003](0003-golden-master-baseline.md) | Golden datasets and a golden-master results baseline | accepted |
| [0004](0004-apps-and-shared-libraries.md) | Four apps, shared libraries, one repo | accepted |
| [0005](0005-ingestion-is-the-only-writer.md) | Ingestion is the only writer of market and feature data | accepted, amended by 0027 |
| [0006](0006-storage-grains-and-adapters.md) | Storage by data grain, Parquet (DuckDB-readable), swappable adapters | accepted |
| [0007](0007-point-in-time-data.md) | Point-in-time data and versioned features (`as_of` is a version pin; one snapshot rule) | accepted, amended |
| [0008](0008-backtests-read-only-from-stores.md) | Backtests read only from stores | accepted |
| [0009](0009-generic-instrument-model.md) | Generic instrument model (futures-ready) | accepted |
| [0010](0010-jobs-model.md) | Long-running work is a job | accepted |
| [0011](0011-design-system-first-ui.md) | Design-system-first UI | accepted |
| [0012](0012-data-vendors.md) | Several data sources, free first, IBKR for derivatives | accepted |
| [0013](0013-universe.md) | The universe | accepted |
| [0014](0014-cboe-options-source.md) | Cboe delayed feed for option chains; limited raw retention | accepted |
| [0015](0015-configs-selections-users.md) | Configs, selections and users | accepted |
| [0016](0016-four-data-layers.md) | Four data layers; instrument level as daily snapshots | accepted |
| [0017](0017-golden-data-through-ingestion.md) | Golden datasets load through ingestion into a separate fixture store | accepted |
| [0018](0018-figi-instrument-ids.md) | FIGI-based instrument ids through one symbol resolver | accepted |
| [0019](0019-ownership-and-boundaries.md) | Every responsibility has one owner; ownership registry and boundary guardrails | implemented |
| [0020](0020-directory-layout.md) | Directory layout: one kind of thing per folder, declared in a layout registry | implemented |
| [0021](0021-option-pricing-conventions.md) | Option pricing conventions: BSM, calendar/365 time, Treasury rates, IV failure codes; IV30 method, dividend yield, IV rank (2b.3 addendum) | accepted |
| [0022](0022-atomic-run-publication.md) | A run's table writes publish atomically: pending until COMPLETE / PARTIAL commits them all, FAILED publishes nothing; `as_of` sees a run from its commit | accepted |
| [0023](0023-feature-store.md) | Feature store: per-feature definitions (kind, dtype, unit, null meaning, range) in feature groups, a generated catalogue, inputs asked of `data/` by table name; steps 3-7 (features by name, expressions in config, virtual by default, quality, new grains) recorded | accepted (steps 1-2 implemented) |
| [0024](0024-api.md) | API v1: a read-only FastAPI over `services.explore`; thin routes, pydantic schemas as the OpenAPI contract | accepted |
| [0025](0025-frontend-architecture.md) | Frontend architecture: layered (app, pages, widgets, features, entities, shared), component-only web app; TRADER / ADMIN workspaces; enforced by ESLint, Stylelint, layout and design-system checks | accepted |
| [0026](0026-live-verification-ibkr.md) | Live verification against IBKR, read-only by construction (facade, fitness test, gateway setting); session sources; the `verify` task, quality check and email section | accepted |
| [0027](0027-vendor-sources-shared-package.md) | Vendor sources as a shared package (`libs/sources`, `algotrade_sources`): batch use by ingestion, live read-only use by the API later, never by backtests; amends 0005 | accepted |
| [0028](0028-ibkr-enrichment-source.md) | IBKR as an enrichment source, read-only: conids and IB's IV / HV history (backfill + nightly snapshot), `ibkr_iv@v1`, `iv_rank` with a labelled fallback to ours, `licence` tags on features | accepted |
