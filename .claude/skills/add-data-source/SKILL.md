---
name: add-data-source
description: Add a new market data vendor or source adapter (e.g. IBKR, Massive, Schwab, Nasdaq Trader) to the ingestion app. Use whenever data must be pulled from a new external source.
---

# Add a data source

Read first: `docs/data/vendors.md`, `docs/data/storage.md`, ADRs 0005, 0006, 0008 and 0012.

**Ownership check (ADR 0019):** a source owns only fetch + normalise for its vendor. HTTP,
retries, the retry cap and the circuit breaker belong to `sources/http.py`; pacing belongs to
the shared limiter (`sources/limiter.py`, one per key across threads and processes); building
the source from `config/site/sources.toml` belongs to the source registry
(`sources/registry.py`); raw saving, id resolution, stamping and run records belong to the
ingest loop (`tasks/framework.py`, `IngestRun`). **Never pace, sleep or build a source
yourself**: the source takes one `Http` client and calls `http.get(url)`. Keep every vendor detail (file
names, request keys, response fields) inside `sources/<vendor>.py`; never import
`algotrade.storage` I/O. Look these up in `architecture/ownership.toml`; `make ownership`
must pass without growing `architecture/known_violations.toml`.

1. **Location:** `apps/ingestion/sources/<vendor>.py`, one module per vendor. If it grows past
   about 300 lines, split it into a package (`client.py`, `mapping.py`, `limits.py`). Nothing
   outside `apps/ingestion` may import it.
2. **Implement `sources/base.py` `Source`:** `name`, `dataset`, `fetch(FetchRequest) -> bytes | None`
   (raw, exactly as received; `None` only for a genuine "nothing there", never for errors)
   and `normalize(FetchRequest, bytes) -> Normalized | None` (canonical frames keyed by
   storage table, without point-in-time columns). Its constructor takes one `Http` (tests:
   `tests.ingest_helpers.http_for(fake_transport)`). Rows keyed by a vendor ticker carry
   `symbol`; the task resolves `instrument_id` through the reference (ADR 0018). Register the adapter in
   `tests/apps/ingestion/test_source_contract.py::ADAPTERS` with a canned payload.
3. **Raw is saved for you:** tasks call `IngestRun.fetch(source, request)`, which saves the
   response as received under `raw/` before normalising. Normalisation must be re-runnable
   from raw alone. A source that needs several requests for one window (one per event kind)
   implements `WindowedSource.window_requests` so request keys stay in the source.
4. **Limits:** give the vendor a `[<vendor>]` section in `config/site/sources.toml` with
   `enabled` and `min_interval_s` matching its documented limits (IBKR: at most 60 historical
   requests per 10 min = 10 s). The registry's limiter enforces it across every process; never
   call `time.sleep` in a source (a fitness test fails). Tasks checkpoint through
   `IngestRun.checkpoint()`.
5. **Register it:** add one `SourceSpec` per source to `SOURCES` in `sources/registry.py`:
   name (e.g. `massive_bars`), section, limiter key (one per vendor host; sources sharing a key
   share the section), default `min_interval_s`, the credential variable and how it becomes
   headers (`Authorization`, a `User-Agent`), retry tries, and the class (built from `Http`).
   Then declare the task that uses it in `tasks/registry.py` (see `add-dataset`). Tasks get it
   as `ctx.sources["<name>"]`; they never import vendor modules (contract R3). A disabled
   section or a missing variable leaves the source out, and tasks needing it are skipped with
   that reason.
6. **Secrets:** only from environment variables (`ALGOTRADE_<VENDOR>_*`), named in the
   `SourceSpec` and read through `env.credential`. Add placeholders to `.env.example`.
7. **Tests:** save real responses as fixtures under `tests/fixtures/sources/<vendor>/`
   (strip account ids). Unit-test normalisation, error handling (429s, gateway down,
   partial responses) and symbol mapping. No network access in CI.
8. **Data quality:** validation in `storage/schemas.py` must pass. Add vendor-specific
   sanity checks (for example bid ≤ ask, open interest ≥ 0).
9. **Docs:** update the table in `docs/data/vendors.md`. If the vendor changes a decision,
   write an ADR.
10. Run `make check`.
