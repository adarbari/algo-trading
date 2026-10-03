# Screeners

| Screener | Status | Reads | Spec |
|---|---|---|---|
| `short_premium_liquidity` | implemented | `features/option_liquidity@v1` | below |
| VRP scanner (IV vs HV near 52-week extremes) | spec (phase 2b) | needs `iv30`, `hv20/30`, 52-week range, moving averages, earnings | [vrp-scanner.md](vrp-scanner.md) |

## Contract (all screeners)

- Input: a point-in-time `FeatureView` holding exactly the production universe for the
  session. Output: **one `ScreenRow` per instrument**, with a shared `Decision`
  (`QUALIFIED`, `WATCH`, `EVENT_RISK`, `LIQUIDITY_RISK`, `REJECT`, `UNKNOWN`), score and reasons.
- Missing or stale data is `UNKNOWN` (fail closed) and does not count as processed.
- Every run saves an audit: universe snapshot, version and last-verified date, rows
  loaded, duplicates removed, processed, skipped with reasons, coverage %, decision
  counts, and a coverage status. Only `COMPLETE` runs may claim "no qualified candidates".
  Below 98% coverage a run is `PARTIAL`; a universe verified more than 45 days ago makes it
  `UNIVERSE_INCOMPLETE`.

## `short_premium_liquidity`

A port of the original `liquidity_screen.py` + `combine_liquidity.py`:

- **Feature:** `option_liquidity@v1` (`src/algotrade/features/option_liquidity.py`) picks the
  target expiry (standard monthly closest to 35 DTE in 21–60, with fallbacks), the most
  liquid strike in the 0.20–0.40 |delta| band, and grades each side A–D.
- **Decision:** `QUALIFIED` when either side is tier A or B (the original `process_further`),
  `LIQUIDITY_RISK` when quoted but thin, `REJECT` when there is no usable chain, and
  `UNKNOWN` when data is missing or failed.
- **Exports:** `algotrade-ingest screen --export-dir out/` writes
  `optionable_universe_with_liquidity_<date>.csv` and `short_premium_candidates_<date>.csv`
  in the original column layout.

Differences from the original (all deliberate; covered by tests):

| Original | Now | Why |
|---|---|---|
| DTE from the wall-clock date | DTE from the chain's session date | point-in-time correctness |
| Monthly = day 15–21 Friday heuristic | exact third Friday, or Thursday when listed instead | holidays (Good Friday, Juneteenth) |
| Missing deltas silently dropped | counted in `<side>_missing_delta` | data-quality visibility |
| Ties broken by feed row order | broken by lower strike | deterministic results |
| HTTP 403 treated as "no chain" | 403 is an error; mass no-chain makes the run PARTIAL | fail closed if blocked |
| Monthly pre-screen | runs nightly | liquidity changes daily |

Known gap: liquidity is measured in the 20–40 delta band, but the VRP scanner trades
8–15 delta puts. Phase 2b adds a VRP-specific liquidity check at the traded strikes.
