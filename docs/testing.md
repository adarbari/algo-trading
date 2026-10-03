# Testing strategy

| Suite | Path | Purpose | Speed |
|---|---|---|---|
| Unit | `tests/unit/<layer>/` | One module at a time; mirrors `src/` layout. | ms |
| Architecture | `tests/architecture/` | File-length limit, every layer tested + documented, module docstrings. | ms |
| Property | `tests/property/` | Hypothesis invariants across *all* registered strategies. | ~1s (`dev`), minutes (`nightly`) |
| Integration | `tests/integration/` | Real data store + engine across every golden dataset. | ~1s |
| End-to-end | `tests/e2e/` | The `algotrade-backtest` CLI against committed datasets and baseline. | seconds |

Run everything with `make test` (enforces 90% branch coverage). Hypothesis profiles are
chosen with `HYPOTHESIS_PROFILE=dev|ci|nightly`.

## Invariants every strategy must satisfy

These run automatically for anything in `strategies/registry.py`:

1. **No look-ahead.** Rewriting bars after `t` must not change any decision at or before `t`.
2. **Accounting identity.** With zero costs, final equity == cash + position × last price.
3. **Long-only by default.** Default risk limits never produce a short or negative equity,
   even under violent overnight gaps.

## The golden datasets

`datasets/golden/` holds deterministic synthetic regimes (trend, bear, random walk, mean
reversion, crash, high vol, regime switching, correlated multi-asset). They are committed
with SHA-256 checksums in `manifest.json`; `algotrade-backtest datasets verify` fails if a byte changes.

Why synthetic? Free, licence-clean, reproducible, and we can build the regimes we want to
stress on purpose. **`random_walk` is the null hypothesis**: a strategy that looks good
there is fitting noise.

Real historical data should be added later as a separate, *non-committed* research set
(downloaded by a script, cached locally), never as a CI dependency.

## The regression baseline (golden master)

`benchmarks/baseline.json` stores every metric for every `strategy@dataset`. CI fails on
any change beyond floating-point tolerance. That turns "did my refactor change results?"
into a yes/no question.

- Unintended diff → it's a bug. Fix it.
- Intended diff (new strategy, fixed cost model) → `make baseline`, commit the JSON, and
  explain the scorecard change in the PR.
