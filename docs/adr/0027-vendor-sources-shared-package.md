# ADR 0027: Vendor sources as a shared package

**Status:** accepted (2026-10-03); amends ADR 0005

## Context
ADR 0005 put vendor SDKs, credentials and source adapters inside the ingestion app
(`apps/ingestion/sources/`). The API will need live, read-only vendor reads (quotes for a page)
without importing the ingestion app (apps never import each other, ADR 0004), and nothing
stopped a future change from reaching a vendor from a backtest except review. Vendor code is a
library used by more than one app, not part of one app.

## Decision
- Vendor sources move, unchanged, into a uv workspace package `libs/sources`
  (`algotrade-sources`, import name `algotrade_sources`): `framework/` (protocols, HTTP with
  retries and the circuit breaker, pacing, the source registry), `vendors/<vendor>/` and
  `fixtures/` (the golden synthetic source). Vendor SDKs (`ib_async`, `openpyxl`) are declared
  in its `pyproject.toml` and nowhere else. Credentials still come only from the environment.
- **Batch use by ingestion**: `apps/ingestion` depends on it; tasks get sources only as
  `ctx.sources[...]` from the registry. Ingestion stays the only writer of market and feature
  data (ADR 0005 otherwise unchanged).
- **Live read-only use by the API (future)**: `algotrade_api` may import
  `algotrade_sources.framework.registry` (never a vendor folder). Any writes it then needs
  (cached live quotes) get a `live/*`-only writer exception, added with an ADR amendment in the
  live-quotes PR. Nothing is added to the API now.
- **Backtests can never reach vendors**: `algotrade_backtest` and the library `algotrade`
  never import `algotrade_sources` (ADR 0008).
- Boundaries, enforced by import-linter: `algotrade_sources` imports only `algotrade.core`,
  `algotrade.quant` (rate conventions) and `algotrade.config.env` (variable names); never
  storage, data, features, services, engines, strategies, site settings or any app. Vendors are
  independent; only `framework/registry.py` imports vendor folders; only the read-only IBKR
  facade imports `ib_async` (ADR 0026, fitness test kept with the vendor's tests).
- Tests mirror the package under `tests/libs/sources/`.

## Consequences
- A pure move: raw saving, pacing, retries, the circuit breaker, registry behaviour, source and
  task names, and the `algotrade-ingest` commands are unchanged.
- The API can gain live reads without depending on ingestion; a backtest importing a vendor
  fails CI.
- `layout.toml`, `ownership.toml` and the fitness scanners cover `libs/` as well as `src/` and
  `apps/`.
