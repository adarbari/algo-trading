# ADR 0018: FIGI-based instrument ids, resolved through one symbol resolver

**Status:** accepted (2026-10-02). Extends [0009](0009-generic-instrument-model.md) and
[0016](0016-four-data-layers.md); keeps [0007](0007-point-in-time-data.md) and
[0017](0017-golden-data-through-ingestion.md). Spec: [docs/data/instruments.md](../data/instruments.md).

## Context
Equity and ETF ids were `EQ:<symbol>`, so a ticker change (FB -> META) split one company
into two instruments, and a reused ticker merged two. Since phase 1.5 the universe build
knows each listing's composite FIGI and keeps `instruments/symbol_history`. Ids were also
built ad hoc from vendor tickers in five places (bars, corporate actions, earnings, golden,
CSV import), so changing the scheme meant changing every one of them.

## Decision
- **Id scheme.** An equity or ETF with a composite FIGI is `EQ:<composite_figi>`
  (`EQ:BBG000B9XRY4`). One without a FIGI keeps the symbol id `EQ:<symbol>`. Option
  contracts stay `OPT:<OCC symbol>`; their `parent_id` / `underlying_id` is the
  underlying's id, whatever its scheme.
- **Stability.** A FIGI id never changes once assigned: a ticker change only updates
  `symbol` in the reference (plus the existing `ticker_changed` event). When a later build
  finds no FIGI for a symbol whose previous id was FIGI-based, the id (and FIGI) carry forward.
- **Upgrades are recorded.** When an instrument with a symbol id gains a FIGI, the build
  writes `instruments/id_map` (`instrument_id` = new id, `old_id`, `new_id`, `symbol`,
  `effective`; cumulative, one full map per snapshot) and an `id_changed`
  `events/reference_change` row. The old id is not reported as a delisting.
- **One resolver.** `SymbolResolver` (`data/resolver.py`, moved from `storage/` in R2) maps
  symbol -> id from an `instruments/reference` snapshot: `data.reference.resolver(reader, D)`
  uses the latest snapshot on
  or before D, else the earliest one (backfills before the first snapshot; ids are identity,
  not market knowledge). Active rows win over delisted ones; unknown symbols fall back to
  symbol ids and are counted. Vendor adapters emit `symbol`; jobs resolve `instrument_id`.
  Only `core/instruments.equity_id` builds an `EQ:` id (an architecture test enforces it).
- **Humans keep writing symbols.** CLI flags, `universe.toml` include/exclude lists and
  exports stay symbol-based and resolve through the reference as of the date.
- **Stored data migrates append-only.** `algotrade-ingest migrate-ids [--dry-run]` rewrites
  every partition holding a mapped id (`instrument_id`, `underlying_id`, `parent_id`) as a
  **new run** with a later `knowledge_ts`. Old runs stay, so `as_of` before the migration
  still reads the old ids. Re-running maps nothing.

| Alternative | Rejected because |
|---|---|
| Opaque internal ids (`EQ:000123`) from a sequence | Needs a central allocator; FIGI is already a free, global, stable key |
| Share-class FIGI | Composite FIGI is what Massive exposes for every listing and is US-listing specific |
| Rewrite stored partitions in place | Breaks point-in-time reads and the append-only rule |
| Strict resolver (drop unknown symbols) | Loses bars for listings the reference does not know yet |

## Consequences
- Golden and synthetic instruments have no FIGIs, so they keep symbol ids and the baseline is
  unchanged.
- Owner action after upgrading: rebuild the universe with identifiers (Massive key set),
  then run `migrate-ids --dry-run`, then `migrate-ids`.
- Instruments that changed ticker before the first snapshot cannot be linked automatically;
  their pre-change history keeps the old symbol id.
