---
name: add-data-source
description: Add a new market data vendor or source adapter (e.g. IBKR, Massive, Schwab, Nasdaq Trader) to the ingestion app. Use whenever data must be pulled from a new external source.
---

# Add a data source

Read first: `docs/data/vendors.md`, `docs/data/storage.md`, ADRs 0005, 0006, 0008 and 0012.

**Ownership check (ADR 0019):** a source owns only fetch + normalise for its vendor. HTTP,
retries and pacing belong to `sources/http.py` (shared limiter: `sources/limiter.py`, R4);
building the source from `config/site/sources.toml` belongs to the source registry
(`commands.py` `build_sources` / `VENDOR` until R4); raw saving, id resolution, stamping and
run records belong to the ingest loop (`tasks/framework.py`, `IngestRun`). Keep every vendor detail (file
names, request keys, response fields) inside `sources/<vendor>.py`; never import
`algotrade.storage` I/O. Look these up in `architecture/ownership.toml`; `make ownership`
must pass without growing `architecture/known_violations.toml`.

1. **Location:** `apps/ingestion/sources/<vendor>.py`, one module per vendor. If it grows past
   about 300 lines, split it into a package (`client.py`, `mapping.py`, `limits.py`). Nothing
   outside `apps/ingestion` may import it.
2. **Implement `sources/base.py` `Source`:** `name`, `dataset`, `fetch(FetchRequest) -> bytes | None`
   (raw, exactly as received; `None` only for a genuine "nothing there", never for errors)
   and `normalize(FetchRequest, bytes) -> Normalized | None` (canonical frames keyed by
   storage table, without point-in-time columns). Map vendor symbols to `instrument_id`
   via the reference store; never key data by raw ticker. Register the adapter in
   `tests/apps/ingestion/test_source_contract.py::ADAPTERS` with a canned payload.
3. **Raw is saved for you:** tasks call `IngestRun.fetch(source, request)`, which saves the
   response as received under `raw/` before normalising. Normalisation must be re-runnable
   from raw alone. A source that needs several requests for one window (one per event kind)
   implements `WindowedSource.window_requests` so request keys stay in the source.
4. **Limits:** add a rate limiter matching the vendor's documented limits (IBKR: at most
   60 historical requests per 10 min). Tasks checkpoint through `IngestRun.checkpoint()`.
5. **Wire it up:** name each source (e.g. `massive_bars`) in `commands.py` (`VENDOR` + a
   `<vendor>_sources(settings, required)` factory), then declare the task that uses it in
   `tasks/registry.py` (see `add-dataset`). Tasks get it as `ctx.sources["<name>"]`; they
   never import vendor modules or build sources.
6. **Secrets:** only from environment variables (`ALGOTRADE_<VENDOR>_*`). Add placeholders
   to `.env.example`.
7. **Tests:** save real responses as fixtures under `tests/fixtures/sources/<vendor>/`
   (strip account ids). Unit-test normalisation, error handling (429s, gateway down,
   partial responses) and symbol mapping. No network access in CI.
8. **Data quality:** validation in `storage/schemas.py` must pass. Add vendor-specific
   sanity checks (for example bid ≤ ask, open interest ≥ 0).
9. **Docs:** update the table in `docs/data/vendors.md`. If the vendor changes a decision,
   write an ADR.
10. Run `make check`.
