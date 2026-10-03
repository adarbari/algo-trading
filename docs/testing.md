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
reversion, crash, high vol, regime switching, correlated multi-asset) as committed CSVs with
SHA-256 checksums in `manifest.json`. These are the reviewable source of truth.

```
algotrade-ingest golden build    regenerate the CSVs from apps/ingestion/.../synthetic/catalog.py
algotrade-ingest golden verify   every committed file matches its checksum      (make datasets-verify)
algotrade-ingest golden load     load them into a store via the normal writers  (make golden-store)
```

`make golden-store` loads them into a **separate fixture store** (`datasets/golden/store`,
git-ignored): `bars/1d`, `instruments/reference` and `catalog/golden_datasets`. Backtests,
`make evaluate` and the tests read that store through `StoreReader`, the same code path as
production data (ADR 0008). It is never mixed into the production store, because synthetic
symbols such as `AAA` collide with real tickers.

Why synthetic? Free, licence-clean, reproducible, and we can build the regimes we want to
stress on purpose. **`random_walk` is the null hypothesis**: a strategy that looks good
there is fitting noise.

## The regression baseline (golden master)

`benchmarks/baseline.json` stores every metric for every `strategy@dataset`. CI fails on
any change beyond floating-point tolerance. That turns "did my refactor change results?"
into a yes/no question.

- Unintended diff → it's a bug. Fix it.
- Intended diff (new strategy, fixed cost model) → `make baseline`, commit the JSON, and
  explain the scorecard change in the PR.
