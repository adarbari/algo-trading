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
- **Re-runs keep the map** (note, 2026-10-03). The build starts its cumulative state (ids,
  `id_map`, `symbol_history`, `first_seen`, delistings) from the latest snapshot known when it
  runs, including an earlier run of the same session; events still diff against the previous
  session. `id_map` and `symbol_history` merge their runs (ADR 0007, key `old_id` + `new_id`
  and `figi` + `symbol` + `valid_from`). Before this, a same-session re-run started the map
  from nothing: on 2026-10-02 it wrote 3 upgrades that hid 10,817, and `migrate-ids` mapped 3
  ids. The map is keyed on the pair, not `old_id` alone, because a reused symbol id can
  upgrade again to another FIGI (told apart by `known_at`).
- **FIGI ids never change automatically** (addendum, 2026-10-03; owner decision 1a). On
  2026-10-02 the vendor reported two FIGIs for DFAC across same-session runs
  (BBG011DXY5J0 -> BBG0132J6C32 -> BBG011DXY5J0) and the id followed each flip, leaving a
  phantom delisted instrument and same-day rollups under the second id; MMED and MMEDV were
  reported with one FIGI and the symbol history gave its open row to MMEDV, which held a symbol
  id. Now: once a listing (same symbol, as the build already tracks) holds `EQ:<FIGI>`, a
  build keeps that id and FIGI whatever the vendor reports; a different vendor FIGI is stored
  as `vendor_figi` (with `figi_review_since`) and listed in a review file
  (`universe-build --figi-review-out`, default `var/figi_review.csv`: symbol, held_figi,
  vendor_figi, first_seen, note) and in the run stats. A shared FIGI stays with the listing
  that held it; the others keep symbol ids; all are listed; only the holder has an open
  `symbol_history` row. The owner resolves a row with `config/site/overrides/figi.csv`
  (symbol, figi, note; blank figi = symbol id), loaded and validated by the site settings
  loader; an override that changes a held id is an **explicit** id change, recorded in
  `instruments/id_map` so `migrate-ids` moves history. Rejected: following the vendor (ids
  churn with vendor noise, splitting history) and failing the build (one bad FIGI would stop
  the nightly).
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
- **Historic listings: `EQ:TIINGO:<permaTicker>`** (amendment, 2026-10-08; edges track ED6, [0053](0053-edges-hypotheses-outcomes-and-one-harness.md)). The winners study needs names that were listed in 2010 and are gone, which no `instruments/reference` snapshot ever held and for which no composite FIGI is trusted. Such a listing's id is chosen in this order: (a) its ticker and dates overlap an `instruments/symbol_history` row: that row's id; (b) else the vendor-namespaced `EQ:TIINGO:<permaTicker>` (Tiingo's permanent id, stable across ticker changes); (c) never `EQ:<symbol>`, whose reused tickers merge two companies. A listing with no `permaTicker` yet (the supported-tickers file has none; the meta pull fills it) has no id and is not used until it has one. No OpenFIGI lookup of historic FIGIs runs during ingestion. A FIGI confirmed later is an upgrade like any other: an `instruments/id_map` row (old `EQ:TIINGO:...`, new `EQ:<FIGI>`), an `id_changed` event, and `migrate-ids` moves the stored history. `core/model/instruments.equity_id(symbol, figi=None, perma_ticker=None)` stays the only `EQ:` constructor (FIGI, then permaTicker, then symbol); a symbol never contains `:` (a fitness test), so the namespaced key cannot collide with one. `SymbolResolver.from_listings(listings, S)` maps a symbol to the listing whose dates contain S, so a recycled ticker resolves to two ids by date. Rejected: ids derived from (ticker, startDate) (a listing's start date is revised by the vendor, which would silently change ids). **Gate:** if `permaTicker` turns out to need a paid fundamentals plan, ED6b stops and returns to this ADR.

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
