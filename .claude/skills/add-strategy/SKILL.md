---
name: add-strategy
description: Add a trading strategy for backtesting (momentum, swing, mean reversion, options, futures). Use when creating or changing a strategy in strategies/.
---

# Add a trading strategy

Read first: `docs/architecture.md`, ADRs 0001, 0002 and 0008, and `docs/trading-pitfalls.md`.

1. **Location:** one module in `src/algotrade/strategies/` (`strategies/trading/` after phase 0).
   Subclass `Strategy`: `warmup_bars`, `on_bar(view) -> target weights | None`, `params()`.
2. **Pure and deterministic:** read only from the view you are given. No I/O, no clocks,
   no randomness without a seeded parameter. Needs a new input? Add a feature (`add-feature`).
3. **Register it** with one line in the strategy registry.
4. **Tests:** unit tests for entry and exit logic in `tests/unit/strategies/`. The property
   tests (look-ahead, accounting, long-only) run on it automatically and must pass.
5. **Evaluate:** run `make evaluate`. It must beat `buy_and_hold` somewhere meaningful, and
   a good result on `random_walk` alone is a red flag (it is fitting noise).
6. **Baseline:** run `make baseline` and commit the new rows with an explanation in the PR.
7. Run `make check`.
