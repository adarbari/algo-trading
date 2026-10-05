# ADR 0038: Per-instrument values are read by catalogue name

**Status:** accepted (2026-10-05; owner decision). Extends [0023](0023-feature-store.md) (the
catalogue is the vocabulary) and [0032](0032-screener-review-table.md) (view columns are
catalogue names). Spec: [docs/api/read-model.md](../api/read-model.md) ("Catalogue feature or
typed field", "What the browser may not derive").

## Context
Stored values reach pages under ad hoc names: `Idea.next_earnings_date`, `days_to_earnings`,
`OptionChain.our_iv`, `UniversePage.liquidity_class`, an `InstrumentDetail.features` bag. Each
needs its own schema field, its own format guess in the web app and its own partition rule.
Some facts are not stored at all (nearest expiry, DTE, earnings before expiry are computed per
request in the Ideas ranking, and again in the browser), so the server and the browser can
disagree.

## Decision
1. **Typed fields are identity and structure** only: who something is (id, symbol, name,
   security type, asset class, exchange), what links to what, and run / session bookkeeping
   (run id, session, status, decision, score, rank, criterion outcomes). They come from snapshot
   or result tables, never from `rollups/*`.
2. **Every per-instrument, per-session value is a catalogue feature** (`rollup.<group>@vN.<col>`,
   `feature.<name>`, `instrument.<col>`), read by name through `features(names)`: a
   `FeatureValue` (value, an UNKNOWN reason, `FeatureInfo` metadata), never a typed field.
   Decided cases: `instrument.optionable` is a catalogue field; a chain's `status` and an
   instrument's `description` are typed.
3. **A fact a page needs that is computed in a read becomes a stored feature first**
   (`.claude/skills/add-feature`): `rollup.nearest_expiry@v1` and
   `feature.earnings_before_expiry` are the first.
4. **Display format comes from the catalogue** (`FeatureInfo.format`, derived from unit and
   dtype on the server), not from the feature's name in the browser.
5. **The browser derives no fact from raw rows**: no next earnings from events, no "today"
   against stored dates, no counts from a page, no picked / new / dropped from decision strings,
   no symbol from an id (`architecture/web_forbidden_derivations.toml`, a fitness test).
6. **Tables are one widget with column factories**: `widgets/feature-table` and the factories in
   `entities/feature/model/columns.tsx`; a column is a catalogue name or a typed result field.

## Consequences
- No `Idea.next_earnings_date`-style fields again; adding a column anywhere is a catalogue
  name, not a schema change.
- Site feature names are typed at compile time in TS (a generated `catalogue.ts`); user
  expression features are checked at request time by the `FeatureName` scalar.
- A few facts need a backfill when they become features (PR 3's `nearest_expiry@v1`).
- The derivation list starts with the patterns today's code respects; each migration PR enables
  the entry for the derivation it removes.
