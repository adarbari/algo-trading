# ADR 0047: Market-entity features and non-tradable id namespaces

**Status:** accepted (2026-10-06; architect design for the market regime track,
[market-regime-plan.md](../market-regime-plan.md)). Amends [0009](0009-generic-instrument-model.md)
(non-tradable id namespaces) and [0023](0023-feature-store.md) (`FeatureGroup.entity`, market
groups). Indices are stored as series under [0048](0048-macro-series-with-vintages.md).

## Context
Every stored feature is keyed by `instrument_id`. The regime track needs facts about the whole
market for a session (index trend, breadth, cross-asset turbulence) and decades of index history
(S&P 500, Nasdaq, VIX, VIX3M) to replay the twelve big drawdowns. `docs/data/storage.md` already
names a "cross-section / market" grain; nothing implements it. `Feature.entity` already exists
(`Literal["instrument"]`, `market` reserved); expression definitions already use `scope` for
site / user, so the new axis cannot be called `scope`.

## Decision
1. **`FeatureGroup.entity`** (`instrument` default, or `market`), inherited by its features as
   `applies_to` is. `ENTITIES = {"instrument", "market"}`; `sector` and `universe` fit later
   unchanged (`SECT:` / `UNIV:` rows).
2. **Storage.** A market group writes `rollups/market/<name>@v<N>`, one wide table per group like
   instrument groups: one row per session with `instrument_id = "MKT:US"` (the column is the
   storage entity key; `RATE:UST-3M` rows set the precedent), the point-in-time columns
   unchanged, partitioned by `session_date`, snapshot runs. `core/model/fields.py` gains
   `rollup_table(entity, key)` and `MARKET_ROLLUP_PREFIX`; `field_source` maps
   `market.<group>@vN.<col>`; `schemas.OPEN_PREFIXES` gains `rollups/market/`.
3. **Compute and inputs.** The same signature as instrument groups over ordinary multi-instrument
   frames; new `data/feature_inputs` loaders `universe` (the session's snapshot, `None` when
   `pre_snapshot`) and `instruments/symbol_ids` (from `SymbolResolver.ids`, so a group finds SPY
   without building an id). The runner checks a market group returns exactly one `MKT:US` row.
4. **Reads and expressions.** The definitions checker infers an expression's entity from its
   inputs; mixing entities is an error (broadcasting is a later ADR). The feature-value loader is
   generalised to take an entity id; a thin `services/read/market/features.py` calls it. The
   catalogue gains a "Market features" section.
5. **Non-tradable ids** (amends 0009): namespaces `MKT` (`market_id("US")`), `MACRO` and `IDX`
   (`index_id(key)`: `IDX:SPX`, `IDX:COMP`, `IDX:VIX`, `IDX:VIX3M`) are minted only in
   `core/model/instruments.py` (`AssetClass.MARKET = "MKT"`; `AssetClass.INDEX` exists). They
   come from config, not vendor tickers, so `SymbolResolver` and ADR 0018 are unchanged. The
   universe and the reference snapshot never hold them: screens never see an index.
6. **Index levels are series, not bars.** `bars/1d` uses snapshot runs (a separate index run
   would replace the session's equity bars on read) and the `bars` task skips stored dates (1970-
   2024 partitions would block equity backfills), so index levels live in `macro/series` (ADR
   0048, `kind = "index"`); index trend comes from the market `trend` group through `quant`.
7. **Nightly.** `compute_rollups(..., entity=...)` and a registered task `market-rollups`,
   `Step("market-rollups", needs=("rollups",), critical=False)` before the screens: a bug in a
   market group never holds back the screens (ADR 0039).

Rejected: long format (loses dtypes, breaks the expression join and column projection); a
generic entity column in storage (touches backends, contract tests, the join and `FeatureView`
for no gain); a synthetic index instrument (breadth is a property of the universe); the plan's
`features/market` table name (the `rollups/<entity>/` family is consistent); index levels in
`bars/1d` (loses equity bars, blocks backfills).

## Consequences
- Market features are catalogue features read by name (ADR 0038) with no new storage machinery;
  ownership gets `[[table]]` entries for each `rollups/market/*`.
- Breadth before our universe history starts is null, never zero; the scorecard validates breadth
  only on the window we hold.
- An expression cannot yet combine a market and an instrument feature (e.g. beta-scaled stress):
  that needs the broadcasting ADR.

## Amendment (2026-10-06, RG1c review)
A group that reads only a few tickers declares them as `Input("bars/1d", symbols=(...))`: the
input loads only the ids those tickers resolve to in the reference snapshot each session of the
chunk sees (`reference.ids_for_symbols`, the union), instead of every instrument's bars, and the
group still picks each session's ids through `instruments/symbol_ids`. The prefilter is a
superset of every session's ids, so point in time and ADR 0018 (no built ids) are unchanged.

## Amendment (2026-10-06, RG3a review): licences of the regime's verdicts, scores and label
ADR 0028 marks values derived from a personal-use source `personal` so that the licensed data
itself is never shown to other users; it does not mean every conclusion we draw from it is
hidden. So a raw third-party value keeps its licence (`market_macro@v1.hy_oas`, `vix`,
`vix_term_ratio` and the card values `regime_indicators@v1.hy_oas` / `vix_term` are personal),
while a verdict, score or label we compute is our own aggregate and is `open`: every
`<key>_on` and `<key>_changed` of `regime_indicators@v1` and every column of `regime@v1`.
Otherwise the regime, which reads the high-yield spread and the VIX, would be hidden from every
non-owner user (the traders being onboarded). An expression feature still takes the most
restrictive licence of what it reads (`vix_band` is personal).
