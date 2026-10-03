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
| [0005](0005-ingestion-is-the-only-writer.md) | Ingestion is the only writer of market and feature data | accepted |
| [0006](0006-storage-grains-and-adapters.md) | Storage by data grain, Parquet + DuckDB, swappable adapters | accepted |
| [0007](0007-point-in-time-data.md) | Point-in-time data and versioned features | accepted |
| [0008](0008-backtests-read-only-from-stores.md) | Backtests read only from stores | accepted |
| [0009](0009-generic-instrument-model.md) | Generic instrument model (futures-ready) | accepted |
| [0010](0010-jobs-model.md) | Long-running work is a job | accepted |
| [0011](0011-design-system-first-ui.md) | Design-system-first UI | accepted |
| [0012](0012-data-vendors.md) | Several data sources, free first, IBKR for derivatives | accepted |
| [0013](0013-universe.md) | The universe | accepted |
| [0014](0014-cboe-options-source.md) | Cboe delayed feed for option chains; limited raw retention | accepted |
| [0015](0015-configs-selections-users.md) | Configs, selections and users | accepted |
