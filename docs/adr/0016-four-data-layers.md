# ADR 0016: Four data layers; instrument level stored as daily snapshots

**Status:** accepted (2026-10-03). Refines [0006](0006-storage-grains-and-adapters.md). Spec: [docs/data/layers.md](../data/layers.md).

## Context
Storage grains (ADR 0006) say how rows are shaped, but not where a given piece of data or
configuration belongs. The owner defined four layers: instrument-level information,
instrument × time values with roll-ups, site configuration and user configuration.

## Decision
- **L1 instrument level:** `instruments/reference` (sourced facts) plus
  `rollups/instrument/<name>@vN` (derived state as of a date), read together as an
  `InstrumentView`.
- **L2 instrument × time:** `bars/<interval>` (one schema for every interval), `chains/*`,
  `events/<type>` and `rollups/daily/<name>@vN` (intraday rolled up to a session).
- **L3 site configuration** (`config/site`, reviewed via PR) and **L4 user configuration**
  (`config/users/<id>`), see [ADR 0015](0015-configs-selections-users.md).
- L1 history is stored as **one full snapshot per date**, not validity ranges. Diffs between
  snapshots become `events/reference_change`.
- Bars are stored **unadjusted**; corporate actions are applied at read time from events.

| Alternative | Rejected because |
|---|---|
| Grains only, no layers | Leaves "where does X go?" to each author; duplicated or misplaced data |
| Validity ranges (`valid_from`/`valid_to`) for L1 | Hard to write idempotently; snapshots are tiny (< 1 MB/day) |
| Latest-only reference data | Breaks point-in-time backtests (renames, delistings) |
| Vendor-adjusted bars | Adjusted history is rewritten on every split, silently changing past results |

## Consequences
- Every new datum is routed by the "where does it go?" table in `docs/data/layers.md`.
- Labels such as "highly liquid" are rollups with thresholds in `config/site/rollups.toml`.
