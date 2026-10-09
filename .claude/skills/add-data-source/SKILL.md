---
name: add-data-source
description: Add a new market data vendor or source adapter (e.g. IBKR, Massive, Schwab, Nasdaq Trader) to the vendor sources package (libs/sources, algotrade_sources). Use whenever data must be pulled from a new external source.
---

# Add a data source

Read first: `docs/data/vendors.md`, `docs/data/storage.md`, ADRs 0005, 0006, 0008, 0012 and 0027.

Vendor code lives in the shared workspace package `libs/sources/algotrade_sources/` (ADR
0027); `sources/...` paths below are relative to it. Its SDK dependencies go in
`libs/sources/pyproject.toml` (then `uv lock`). It may import only `algotrade.core`,
`algotrade.quant` and `algotrade.config.env` (import-linter); backtests never import it.

**Ownership check (ADR 0019):** a source owns only fetch + normalise for its vendor. HTTP,
retries, the retry cap and the circuit breaker belong to `sources/framework/http.py`; pacing belongs to
the shared limiter (`sources/framework/limiter.py`, one per key across threads and processes); building
the source from `config/site/sources.toml` belongs to the source registry
(`sources/framework/registry.py`); raw saving, id resolution, stamping and run records belong to the
ingest loop (`tasks/framework/run.py`, `IngestRun`). **Never pace, sleep or build a source
yourself**: the source takes one `Http` client and calls `http.get(url)`. Keep every vendor detail (file
names, request keys, response fields) inside `sources/vendors/<vendor>/`; never import
`algotrade.storage` (contract R4). New `sources.toml` keys are typed in
`src/algotrade/config/site/settings.py`. Look these up in `architecture/*_ownership.toml`; `make ownership`
must pass with `architecture/known_violations.toml` still empty.

0. **Where it goes:** `libs/sources/algotrade_sources/vendors/<vendor>/` (new folder, covered by the `vendors/*` entry) (`grep -n purpose architecture/layout.toml`); no fit: new folder, `add-responsibility` step 3. Tests mirror it; if a folder is at 8+ modules, plan the split (`make layout`).
1. **Location:** a new folder `libs/sources/algotrade_sources/vendors/<vendor>/`
   with an `__init__.py` docstring naming the vendor, and one module per dataset it serves
   (e.g. `bars.py`); shared auth / paging goes in `client.py` (see `vendors/massive/`). The
   folder is covered by the `libs/sources/algotrade_sources/vendors/*` entry in `architecture/layout.toml`
   (`tests/architecture/test_layout.py`): it must register at least one source (step 5), only
   `sources/framework/registry.py` may import it, and vendors never import each other (an
   import-linter independence contract: add the new folder to it in `pyproject.toml`).
2. **Implement `sources/framework/base.py` `Source`:** `name`, `dataset`, `fetch(FetchRequest) -> bytes | None`
   (raw, exactly as received; `None` only for a genuine "nothing there", never for errors)
   and `normalize(FetchRequest, bytes) -> Normalized | None` (canonical frames keyed by
   storage table, without point-in-time columns). Its constructor takes one `Http` (tests:
   `tests.helpers.ingest_fakes.http_for(fake_transport)`). Rows keyed by a vendor ticker carry
   `symbol`; the task resolves `instrument_id` through the reference (ADR 0018). Register the adapter in
   `tests/libs/sources/test_source_contract.py::ADAPTERS` with a canned payload.
3. **Raw is saved for you:** tasks call `IngestRun.fetch(source, request)`, which saves the
   response as received under `raw/` before normalising. Normalisation must be re-runnable
   from raw alone. A source that needs several requests for one window (one per event kind)
   implements `WindowedSource.window_requests` so request keys stay in the source.
4. **Limits:** give the vendor a `[<vendor>]` section in `config/site/sources.toml` with
   `enabled` and `min_interval_s` matching its documented limits (IBKR: at most 60 historical
   requests per 10 min = 10 s). The registry's limiter enforces it across every process; never
   call `time.sleep` in a source (a fitness test fails). Tasks checkpoint through
   `IngestRun.checkpoint()`.
5. **Register it:** add one `SourceSpec` per source to `SOURCES` in `sources/framework/registry.py`:
   name (e.g. `massive_bars`), section, limiter key (one per vendor host; sources sharing a key
   share the section), default `min_interval_s`, the credential variable and how it becomes
   headers (`Authorization`, a `User-Agent`), retry tries, and the class (built from `Http`).
   Then declare the task that uses it in `tasks/framework/registry.py` (see `add-dataset`). Tasks get it
   as `ctx.sources["<name>"]`; they never import vendor modules (contract R3). A disabled
   section or a missing variable leaves the source out, and tasks needing it are skipped with
   that reason.
6. **Secrets:** only from environment variables (`ALGOTRADE_<VENDOR>_*`), named in the
   `SourceSpec` and read through `env.credential`. Add placeholders to `.env.example`.
7. **Tests:** mirror the folder (`tests/libs/sources/vendors/<vendor>/`). Save real
   responses as fixtures under `tests/fixtures/sources/<vendor>/` (strip account ids). Unit-test normalisation, error handling (429s, gateway down,
   partial responses) and symbol mapping. No network access in CI.
8. **Data quality:** validation in `storage/tables/schemas.py` must pass. Add vendor-specific
   sanity checks (for example bid ≤ ask, open interest ≥ 0).
9. **Docs:** update the table in `docs/data/vendors.md`. If the vendor changes a decision,
   write an ADR.
10. Run `make changed`, then push: CI is the full gate.
