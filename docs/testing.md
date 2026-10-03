# Testing strategy

| Suite | Path | Purpose | Speed |
|---|---|---|---|
| Unit | `tests/unit/<path>/` | One module at a time; mirrors `src/algotrade/<path>/`. | ms |
| App | `tests/apps/<app>/<path>/` | App modules; mirrors `apps/<app>/<package>/<path>/`. | ms |
| Contract | `tests/contract/<protocol>/` | Every implementation of a protocol (storage backends). | ms |
| Architecture | `tests/architecture/` | Fitness tests: layout, ownership, file length, docstrings, docs. | ms |
| Property | `tests/property/` | Hypothesis invariants across *all* registered strategies. | ~1s (`dev`), minutes (`nightly`) |
| Integration | `tests/integration/` | Real data store + engine across every golden dataset. | ~1s |
| End-to-end | `tests/e2e/` | The `algotrade-backtest` CLI against committed datasets and baseline. | seconds |

## Test layout

Tests follow the directory layout (ADR 0020, `architecture/layout.toml`, checked by
`tests/architecture/test_layout_buckets.py`):

- **Mirror the source.** A test for `src/algotrade/<path>/x.py` lives in `tests/unit/<path>/`;
  for `apps/ingestion/algotrade_ingestion/<path>/x.py` in `tests/apps/ingestion/<path>/`
  (`[[test_mirror]]`). A test folder whose source folder does not exist fails.
- **Shared builders** live in `tests/helpers/`, one module per thing built
  (`stored_frames`, `ingest_fakes`, `rollup_store`, `domain_objects`); synthetic payloads in
  a vendor's wire format in `tests/helpers/payloads/<vendor>.py`. Never name a module
  `helpers.py` or `utils.py`.
- **Recorded data** (real format, trimmed) lives in `tests/fixtures/sources/<vendor>/`.
- **Anything else** is a declared `[[test_dir]]` bucket with a purpose; `tests/` itself
  holds only `conftest.py`.
- At most 10 modules per test folder (`__init__.py`, `conftest.py` excluded): split by kind,
  mirroring the source. `make layout` lists folders at 8+.

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
