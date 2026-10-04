# ADR 0031: Options positioning features are daily chain-derived estimates

**Status:** proposed (2026-10-04, parked: the roadmap schedules the SW track first; revisit before any OP code). Each "Proposed" item
in [docs/data/positioning.md](../data/positioning.md) is confirmed or changed by the owner
before OP1 code starts; this ADR is then accepted. Extends [0014](0014-cboe-options-source.md)
(we compute Greeks ourselves), [0021](0021-option-pricing-conventions.md) (pricing
conventions) and [0023](0023-feature-store.md) (feature groups, expression features).

## Context
The owner wants the fields of a third-party options positioning panel: gamma and delta
exposure, call / put walls, key strikes, a hedge wall, flow ratios, skew and its rank, and
the implied move. Most can be derived from the chains we already store, but each name hides a
convention (who is long, how dollars scale, which expiries count, what "next expiry" or
"skew" means) that changes the number. The data also has hard limits: Cboe's open interest is
OCC's previous-session figure, the snapshot is end of day, and nothing says which side of a
contract a customer or a dealer holds.

## Decision
- Positioning features are **daily estimates computed from the stored chains**, never
  observations: exposures on session S are positions at the close of S-1 (OCC open interest)
  priced at the close of S, with our own IV and Greeks (ADR 0021). No intraday values.
- Gamma exposure assumes a **stated dealer positioning** (proposed: dealers long calls,
  short puts) and every gamma feature's description says so. Delta exposure carries no
  positioning assumption.
- The groups are `gex@v1`, `chain_flow@v1`, `skew@v1`, `skew_history@v1`, `implied_move@v1`,
  plus `prev_close` in `price_moves@v2` and the ratio and impact formulas as expression
  features. Their names, units, formulas, statuses, null rules, tie-breaks and worked examples
  are specified in [positioning.md](../data/positioning.md), which is the source of truth for
  these conventions.
- Every group has a status label that is never null; a null value is UNKNOWN; a ratio with a
  zero denominator is null, never 0 or infinity. All features are `licence = "open"`.
- No new vendor, table grain or stored per-contract Greeks table for OP1 to OP4. Dark-pool
  fields (OP6) need their own data decision and ADR.

| Alternative | Rejected because |
|---|---|
| The feed's `gamma` / `delta` columns | unknown model and inputs (ADR 0014); kept as a cross-check |
| Copying a vendor's proprietary definitions (hedge wall, options impact) | not published, so not reproducible; we document our own and say they are proxies |
| A stored per-contract Greeks table shared by the groups | ~1.5M rows a night for a saving of tens of seconds; revisit if a third consumer appears |
| Waiting for side-aware data (customer vs. firm volume) | not available free; the estimate with a stated assumption is useful now |

## Consequences
- Walls, flips and exposures can be wrong where the dealer assumption is (heavy retail call
  buying); screens and the UI must present them as estimates.
- Skew rank needs 60 sessions of stored chains before it is PROVISIONAL; there is no earlier
  history to backfill.
- The nightly rollups step grows by an estimated 30 to 40 s; `nightly-footprint.md` is
  re-measured after OP1 and OP3.
- `features/rollups/` is split by kind; the groups go in `features/rollups/options/`; the
  shared per-contract pricing step gets one owner in `ownership.toml`.
