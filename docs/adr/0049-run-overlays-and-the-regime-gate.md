# ADR 0049: Run overlays and the regime gate

**Status:** accepted (2026-10-06; architect design for the market regime track,
[market-regime-plan.md](../market-regime-plan.md)). Extends [0008](0008-backtests-read-only-from-stores.md)
(a missing market value is an error), [0015](0015-configs-selections-users.md) (the `[regime]`
config layers and is hashed) and [0029](0029-rule-screener.md) (a new screener decision). Reads
market features from [0047](0047-market-entity-features-and-non-tradable-ids.md).

## Context
The regime track stores a label (`regime@v1`: CALM, CAUTION, STRESS, CRISIS) per session. Its use
is sizing: smaller new positions in rough markets and some idea kinds paused, in backtests and
screeners alike. Strategies import only `core` and `quant` (rule 1), so they cannot apply a
market-wide rule themselves, and one rule copied into every strategy would drift.
`engines/backtest` is at the 10-module cap.

## Decision
1. **Overlays in the engine**, a new folder `engines/overlays/`. `overlay.py`: an `Overlay`
   Protocol, `apply(weights: TargetWeights, market: Mapping[str, FeatureValue]) ->
   OverlayStep(weights, reasons)`. `scale.py`: `ScaleByLabel(feature, multipliers)`; volatility
   targeting later becomes `ScaleByValue`. `run_backtest(..., overlays=(), market=None)` applies
   the overlays after `on_bar` and before `apply_limits`.
2. **Market data for the engine.** `core/views/market_features.py` `MarketFeatures` (columns
   aligned to the bars timeline, `at(cursor)`); `MarketView` gains an optional `market` and
   `market_feature(name)`, sliced at the cursor; `services/backtests/market.py` builds it. Session
   t's features feed orders that fill at the open of t+1. A missing value raises
   `MissingDataError` (ADR 0008).
3. **Config `[regime]`** in `defaults.toml`, typed in `config/strategy/regime.py`, layered per ADR
   0015 so the config hash records it: `enabled = false`, `label = "regime@v1"`,
   `multipliers = {CALM = 1, CAUTION = 0.75, STRESS = 0.5, CRISIS = 0.25}`, `pause_in = []`. The
   multiplier lives in config, not in a feature, so a user can override it.
4. **Screeners.** `FeatureView.market` carries the session's market values. A row the gate blocks
   is `Decision.PAUSED`, with `processed = True`, and its reason. Result rows gain `regime` and
   `size_multiplier`.
5. **Fail closed.** A regime that is UNKNOWN for the session pauses every gated row, with the
   reason; it never passes as CALM.

Rejected: the plan's `SKIPPED` for gated rows (`SKIPPED` means "no data" and lowers coverage,
so every Storm run would grade PARTIAL); the multiplier as a stored feature (users could not
override it); the overlay inside each strategy (breaks the layer rule and drifts); a new module in
`engines/backtest` (at the cap).

## Consequences
- Every backtest can run with and without the overlay; the two runs differ only in the config
  hash, which is what `make evaluate` compares (max drawdown, Sharpe, time in market).
- A paused idea stays visible with its reason (Ideas "Paused by regime"), never silently dropped.
- The gate is off by default: nothing changes until a user or the site enables `[regime]`.
