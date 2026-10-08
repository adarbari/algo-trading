# ADR 0054: Stale chains the chains gate tolerated are excluded from screen coverage

**Status:** accepted (2026-10-07; owner decision). Amends [0039](0039-ingestion-workflows-dependencies-and-acceptance.md)
(a screen step's coverage) and [0030](0030-rule-screener-simplification.md) (Python screeners keep
`UNKNOWN`); builds on [0043](0043-waiting-on-publication-tiered-and-coverage-acceptance.md)
(the tiered stale limits).

## Context
The 2026-10-06 nightly `chains` step passed acceptance with 267 `STALE_DATA` chains (within
`max_chain_stale_share` 20% for the rest tier and `max_chain_stale_share_core` 2%). The screens
then went PARTIAL on those same names: `short_premium_liquidity` reads a stale `liq_status` as
`UNKNOWN` (fail closed, not processed), coverage fell below `min_coverage` 0.98, and the
critical `screens` step FAILED. Two thresholds judged the same names differently
(roadmap "Stale-chain limit vs screener coverage"). Options were to tighten the gate to 2%
(`1 - min_coverage`), to keep a manual waive, or to make the screens consistent with the gate.

## Decision
1. **One tolerance.** `data.chains.tolerated_stale(status_frame, sources)` returns the
   `STALE_DATA` names (instrument id -> reason) of a chain status only when every tier is within
   its limit (core and rest by `chains/status.tier`, a missing tier is rest) and fetch failures
   are within `max_chain_fetch_failures`; otherwise it is empty (fail closed). It shares its
   share computation (`stale_in_tier`) with the `chains_stale_*` checks of `check_chains`, so the
   gate and the screens cannot drift; a contract test pins both at the exact limits.
2. **`Decision.EXCLUDED`.** A name the gate tolerated is never a pick and is out of the coverage
   denominator: `coverage_pct = processed / (unique - excluded)`, 0 (PARTIAL) when nothing is
   left. It is not "processed": it is simply not asked. The run audit gains `excluded` and
   `excluded_reasons`; `skipped` no longer counts it.
3. **One pure step, applied by the engine.** `engines/screening/exclusions.py` rewrites only
   rows that were NOT processed (UNKNOWN, SKIPPED) and whose id is in the map to EXCLUDED, the
   exclusion reason first, then the screener's own reasons; a decided row is never rewritten.
   `run_screener` builds the map from the session's `chain_status` (read as of the run's time)
   and `[quality]` settings, and applies it on the Python and the rule path, as the regime gate
   is applied. Screeners stay pure. Without `sources` nothing is excluded.
4. **Downstream.** EXCLUDED is in `NOT_PICKED` of the read model (never an idea). The GraphQL
   decision is a string, so the schema does not change; the web lists EXCLUDED last in a run's
   decisions.

5. **Chronic staleness is a fetch failure.** `chain_labels(status_frame, session,
   max_chain_stale_sessions)` labels a `STALE_DATA` chain for a day more than
   `[quality] max_chain_stale_sessions` (5) sessions before the session `STALE_CHRONIC`, one of
   `FETCH_FAILURES`: it counts against `max_chain_fetch_failures` in `chains_fetch`, not against
   a tier's stale share, and `tolerated_stale` never excludes it. The 2026-10-06 status held
   chains stale since 2026-09-23 (9 sessions) that the stale share tolerated night after night;
   a feed that is a few sessions late is still tolerated, one that has stopped serving a name
   is not. Both sides read the one labelling, so they stay in step.
   Retries do not clear a name the feed has stopped serving: it stays a fetch failure until the
   feed serves it again or it leaves the optionable universe; above `max_chain_fetch_failures`
   the `chains` step FAILS every night and holds back later sessions until fixed or waived by
   hand (`--waive`, ADR 0039). Measured on the store at N = 5: 26 of 4,205 chains on 2026-10-05
   and 28 of 4,202 on 2026-10-06 (0.67%, under the 2% limit), names the screens no longer
   exclude and that now count against their coverage. The stored text `STALE_DATA: chain is
   for <day>` is pinned to the parser by a test of the chains task.

## Consequences
- A night whose only data problem is a stale share the gate tolerated no longer FAILS the
  `screens` step; one stale name more than the gate tolerates fails the gate (as before) and
  the screens go PARTIAL (the contract test).
- Rule screens reject on missing data (0030), a processed outcome, so today they exclude nothing;
  the rule path is wired for rows a screen leaves unprocessed.
- Excluded names carry their reason in `results/*`, so a stale name is never silently dropped.
- `services/evaluation` must drop EXCLUDED from the base rate when ADR 0053's harness filters
  decisions.
- The reason is the chain's stored status text (`STALE_DATA: chain is for <date>`), so the audit
  shows each name's age.
- The Builder preview does not exclude: it applies no gate either, and rule screens exclude
  nothing today, so its dry run matches the saved run.
