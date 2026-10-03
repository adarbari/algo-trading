---
name: add-screener
description: Add an end-of-day screener (options or equities) that filters and ranks instruments from stored features. Use when creating or changing a screener.
---

# Add a screener

Read first: ADRs 0007 and 0008, and `docs/data/storage.md` (feature and result grains).

**Ownership check (ADR 0019):** a screener only scores a `FeatureView`. Selecting,
auditing coverage, writing results and run records belong to `services/screening.py`;
running it belongs to the job runner (`services/jobs`, kind `screen`; nightly submits
`screen` jobs). Shared filters live in one helper, not copies: `make dupes` must pass.
Owners are listed in `architecture/ownership.toml`.

1. **Location:** `src/algotrade/strategies/screeners/<name>.py`. Implement the screener
   interface: `screen(view: FeatureView) -> ranked rows`. Each row carries
   `instrument_id`, a score and human-readable `reasons`.
2. **Pure:** read only from `FeatureView` (point-in-time). Needs a new input? Add a
   feature. Apply liquidity filters (minimum open interest, maximum spread %) through
   shared helpers, not copy-paste.
3. **Parameters** go in a typed config with defaults, so the UI can show and edit them.
4. **Register it** with one line in the screener registry.
5. **Tests:** unit tests on synthetic chains; property tests (deterministic, every row
   satisfies the declared filters, no data after `as_of` is read).
6. **Baseline:** results on the golden option chains go into the screener baseline
   (`make baseline`).
7. **UI:** columns and formats are declared on the screener, so the generic `DataTable`
   renders it without any screen-specific code.
8. **Config:** add a site preset in `config/site/presets/strategies/<id>.toml` (`kind =
   "screener"`, `impl`, `params`, a `selection` preset or inline selection; `schedule =
   "nightly"` if it should run every night). Never filter instruments inside the screener
   itself; that is the selection's job. Check it with `algotrade-backtest config validate <id>`.
9. Run `make check`.
