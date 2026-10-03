# Testing strategy

| Suite | Path | Purpose | Speed |
|---|---|---|---|
| Unit | `tests/unit/<path>/` | One module at a time; mirrors `src/algotrade/<path>/`. | ms |
| App | `tests/apps/<app>/<path>/` | App modules; mirrors `apps/<app>/<package>/<path>/`. | ms |
| Contract | `tests/contract/<protocol>/` | Every implementation of a protocol (storage backends). | ms |
| Architecture | `tests/architecture/` | Fitness tests: layout, ownership, file length, docstrings, docs. | ms |
| Property | `tests/property/` | Hypothesis invariants across *all* registered strategies. | ~1s (`dev`), minutes (`nightly`) |
| Integration | `tests/integration/` | Real data store + engine across every golden dataset. | ~1s |
| Reconciliation | `tests/reconciliation/` | Our features recomputed from recorded raw inputs vs another source's recorded values (marker `reconciliation`). | ms |
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

## Reconciliation suite (cross-source)

`tests/reconciliation/` checks our numbers against another source, offline: each module pairs a
recorded snapshot of that source with OUR raw inputs for the same session, both committed under
`tests/fixtures/reconciliation/<source>_<session>/` (a README there gives provenance and field
meanings). The test recomputes our side with production code (`data.prices.adjust_bars`, the
feature groups' `compute` through their `FeatureGroup`, `quant.realized_vol`), so a change to
adjustment or feature maths that drifts from the market shows up in `make check` (the tests
carry the pytest marker `reconciliation`: `pytest -m reconciliation`).

`test_ibkr_2026_10_02.py` (IBKR, session 2026-10-02; AAPL, SPY, KO, TQQQ, TSM, RPGL) proves:

| Check | Tolerance |
|---|---|
| Split-adjusted closes equal IBKR's on all 32 shared sessions (RPGL across its 1-for-16 reverse split) | 0.2% relative |
| Daily highs / lows (all but RPGL, which IBKR gave closes for only) | 0.1% relative |
| `price_stats.hv20` equals close-to-close HV20 recomputed from IBKR's closes | 0.5% relative |
| `high_52w` equals IBKR's where no dividend adjustment moves it (AAPL, SPY, RPGL) | 0.05% relative |
| `high_52w` / `low_52w` on our split-only basis: ours >= IBKR's (dividend-adjusted), the gap at most `div_ttm` | 0.05% slack |
| `dividends.div_yield` | 0.05 percentage points |
| Recorded `iv30` (ours, status OK) vs IBKR's implied vol, every name IBKR has one for | 2.5 vol points |

Not compared, on purpose: IBKR's HV30 (a different estimator from our close-to-close
`hv30`), IBKR chart-bar volume (a narrower trade set than consolidated volume) and IBKR's
90-day ADV (a different window from `adv_usd_20d`). The 52-week basis is a decision, not a
discrepancy: ours is split-adjusted only (2026-10-03, `docs/data/layers.md`).

**Refreshing (a new recorded session).** Never hand-edit a fixture; record a new folder:

1. Ask Claude, with the IBKR connector, to pull **read-only** a price snapshot (52-week
   high / low, HV, implied vol, dividend yield, ADV) and the last 32 daily bars (close, high,
   low, volume) for the tickers, and write them as `ibkr.json` in the format of the existing
   one. Market-data calls only: never place, modify or cancel orders, never change alerts,
   watchlists or account settings.
2. Re-extract our side read-only from the production store through `algotrade.data`
   (`prices.bars` raw `bars/1d` for 262 sessions, `events.read_events` for `events/split` and
   `events/dividend`, `rollups.rollup_rows` for the session's `iv30@v1` row), keeping only
   the columns the README lists.
3. Copy the test module for the new session, adjust the dates and the tickers whose 52-week
   high is untouched by dividends, keep the fixtures under 500 KB, and record any new
   discrepancy as a decision (docs) or a fix, never by widening a tolerance silently.

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
