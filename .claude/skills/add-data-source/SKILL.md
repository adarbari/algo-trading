---
name: add-data-source
description: Add a new market data vendor or source adapter (e.g. IBKR, Massive, Schwab, Nasdaq Trader) to the ingestion app. Use whenever data must be pulled from a new external source.
---

# Add a data source

Read first: `docs/data/vendors.md`, `docs/data/storage.md`, ADRs 0005, 0006, 0008 and 0012.

1. **Location:** `apps/ingestion/sources/<vendor>.py`, one module per vendor. If it grows past
   about 300 lines, split it into a package (`client.py`, `mapping.py`, `limits.py`). Nothing
   outside `apps/ingestion` may import it.
2. **Implement `sources/base.py` `Source`:** `name`, `dataset`, `fetch(FetchRequest) -> bytes | None`
   (raw, exactly as received; `None` only for a genuine "nothing there", never for errors)
   and `normalize(FetchRequest, bytes) -> Normalized | None` (canonical frames keyed by
   storage table, without point-in-time columns). Map vendor symbols to `instrument_id`
   via the reference store; never key data by raw ticker. Register the adapter in
   `tests/apps/ingestion/test_source_contract.py::ADAPTERS` with a canned payload.
3. **Save raw first:** store the response as received under `raw/` before normalising.
   Normalisation must be re-runnable from raw alone.
4. **Limits:** add a rate limiter matching the vendor's documented limits (IBKR: at most
   60 historical requests per 10 min). Jobs record checkpoints so they can resume.
5. **Secrets:** only from environment variables (`ALGOTRADE_<VENDOR>_*`). Add placeholders
   to `.env.example`.
6. **Tests:** save real responses as fixtures under `tests/fixtures/sources/<vendor>/`
   (strip account ids). Unit-test normalisation, error handling (429s, gateway down,
   partial responses) and symbol mapping. No network access in CI.
7. **Data quality:** validation in `storage/schemas.py` must pass. Add vendor-specific
   sanity checks (for example bid ≤ ask, open interest ≥ 0).
8. **Docs:** update the table in `docs/data/vendors.md`. If the vendor changes a decision,
   write an ADR.
9. Run `make check`.
