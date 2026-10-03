# Instruments and the universe

Decision records: [ADR 0009](../adr/0009-generic-instrument-model.md),
[ADR 0013](../adr/0013-universe.md).

## Generic instrument model

Every tradable or observable thing is an **instrument** with a stable `instrument_id`.
Data is keyed by `instrument_id`, never by ticker string.

| Field | Notes |
|---|---|
| `instrument_id` | Internal, stable, never reused |
| `asset_class` | `equity`, `etf`, `index`, `option`, `future`, `future_option`, (`fx`, `crypto` reserved) |
| `symbol`, `name`, `exchange`, `currency` | Symbol history is kept separately (renames, reuse) |
| `parent_id` | Option → underlying; future → root; future option → future |
| `multiplier` | 1 for stocks, 100 for US equity options, 50 for ES, … **All P&L uses it.** |
| `expiry`, `strike`, `right` | Derivatives only |
| `contract_month`, `root` | Futures only (for example root `ES`, month `2026-12`) |
| `calendar` | Exchange calendar id. Defines sessions and `session_date`. |
| `tick_size` | Minimum price increment |
| `etf_flags` | `is_etf`, `is_leveraged`, `is_inverse`, `leverage` (for example `3.0`, `-1.0`), `tracks` (underlying index) |
| `valid_from`, `valid_to` | Reference rows are versioned history (delistings, renames) |

### Why this makes futures (and options) "just more data"

- Futures contracts are instruments with `parent_id → root`. Continuous series (for example
  back-adjusted `ES`) are a **derived dataset** with the roll rule recorded in its metadata,
  never mixed with the raw contract data.
- Exchange calendars give each bar a `session_date`. ES trading at 23:00 UTC belongs to the
  next session; the engine works in sessions, not calendar days.
- `multiplier` lives on the instrument, so portfolio accounting stays one formula:
  `value = qty × price × multiplier`. (Today's `Portfolio` assumes multiplier 1; it must
  read the instrument multiplier before any options or futures backtest. This is tracked
  in the roadmap.)
- Roll and expiry dates are **events**, so strategies see them through features, not magic.

## The universe

Saved as a dated snapshot every day (`normalized/universe/date=…`), so backtests use the
universe *as it was*, which avoids survivorship bias.

| Segment | Source | Notes |
|---|---|---|
| S&P 500 constituents | SPY daily holdings file (State Street) | Membership changes become `index_add` / `index_remove` events |
| All Nasdaq-listed stocks | Nasdaq Trader `nasdaqlisted.txt` | Exclude test issues (`Test Issue = Y`) |
| All ETFs (any exchange) | `nasdaqlisted.txt` + `otherlisted.txt` (`ETF = Y`) | Most ETFs list on NYSE Arca, so they come from `otherlisted.txt` |
| Leveraged and inverse ETFs | Subset of ETFs, flagged | See below |
| Optionable flag | Nasdaq Trader `options.txt` (underlying symbols) | About 4.2k underlyings as of 2026-10 |
| Futures (later) | Curated root list (ES, NQ, RTY, CL, GC, ZN, …) | Added as roots; contracts come from the vendor |

### Flagging leveraged and inverse ETFs

There is no free official flag. Use these, in order:

1. a curated override file in the repo (`reference/leveraged_etfs.csv`: symbol, leverage, tracks), and
2. name heuristics as a *suggestion only* ("2X", "3X", "Ultra", "UltraPro", "Bull", "Bear",
   "Inverse", "Short", "-1X"), reported for review and never applied automatically.

Leveraged ETFs reset daily, so long-horizon returns drift away from leverage × index
return (volatility decay). The feature library must expose `leverage` and `is_inverse` so
strategies and screeners can account for it.


## Universe build (implemented, phase 1.2)

`algotrade-ingest universe-build [--date D] [--review-out candidates.csv]` (and the nightly
job when `config/site/universe.toml` has `source = "nasdaq_trader"`):

1. Fetches `nasdaqlisted`, `otherlisted`, `options` (Nasdaq Trader) and SPY holdings
   (State Street); raw responses are kept for 90 days.
2. Classifies every listing: `COMMON_STOCK` (incl. partnership units), `ADR`, `ETF`, `ETN`,
   `PREFERRED`, `WARRANT`, `UNIT`, `RIGHT`, `NOTE`, from the name, the ACT symbol and the ETF flag.
3. Writes **all** listings to `instruments/reference` with `optionable`, `in_sp500`,
   `first_seen` and leverage flags. Instruments no longer listed stay as `DELISTED` with
   `delisted_on`.
4. Writes the **coverage** (`security_types`, test issues, include/exclude lists in
   `universe.toml`) to `universe`.
5. Writes `events/reference_change` (added, removed, renamed, type / optionable / exchange
   changed) and `events/index_change` (S&P 500 adds and removes). S&P members that match no
   listing make the run PARTIAL.

Leverage: non-ETFs are unleveraged; curated rows in `config/site/overrides/leveraged_etfs.csv`
win; an ETF without a leverage marker in its name is unleveraged; an ETF with a marker and no
curated row is **UNKNOWN** and listed in the review file with the leverage its name suggests
(2026-10-02: 957 candidates). Curate by moving reviewed rows into the overrides file.


## Identifiers and vendor types (implemented, phase 1.5)

When a Massive key is configured, the universe build also reads Massive's ticker list (~13
requests): every row gets `figi` (composite), `share_class_figi` and `cik`, and **Massive's
security type wins over the name rules** (`security_type_source` = `vendor` or `name_rule`;
disagreements are counted in the run stats). Notably, closed-end funds (`FUND`) become `CEF`
and drop out of the default coverage.

`instruments/symbol_history` tracks which symbol each FIGI used and when; a FIGI that comes
back under a new symbol closes the old row and emits `events/reference_change` with
`change = ticker_changed` (e.g. FB -> META).


## FIGI-based instrument ids (implemented, phase 1.8)

Decision record: [ADR 0018](../adr/0018-figi-instrument-ids.md).

| Instrument | `instrument_id` | Example |
|---|---|---|
| Equity / ETF with a composite FIGI | `EQ:<composite FIGI>` | `EQ:BBG000B9XRY4` (AAPL) |
| Equity / ETF without one (no Massive key, unknown to Massive, golden data) | `EQ:<symbol>` | `EQ:BULL` |
| Option contract | `OPT:<OCC symbol>`; `underlying_id` = the underlying's id | `OPT:SPY261231C00586000` |

- **Stable.** A FIGI id never changes. A ticker change only updates `symbol` in the
  reference (and emits `ticker_changed`). A build that finds no FIGI for a symbol whose id was
  FIGI-based carries the id and FIGI forward (`ids_carried`).
- **Upgrades.** When a symbol-id instrument gains a FIGI, the universe build writes
  `instruments/id_map` (`old_id`, `new_id`, `symbol`, `effective`, `known_at`; the full map in
  every snapshot) and an `id_changed` reference-change event; the old id is not reported as
  delisted. Build stats: `identifiers.ids_by_figi`, `ids_by_symbol`, `ids_carried`,
  `ids_upgraded`, `figi_conflicts` (two listings with one FIGI: the holder keeps it).
- **One resolver.** `SymbolResolver` maps symbol → id from the reference snapshot on or before
  a date (`data.reference.resolver(reader, D)`; before the first snapshot, the earliest one). Active rows
  win a reused ticker. Vendor adapters (Massive bars/splits/dividends, Nasdaq earnings) emit
  `symbol`; jobs resolve ids and count `unresolved` symbols, which keep symbol ids. CLI flags
  (`chains --symbols`), `universe.toml` include/exclude lists and exports stay symbol-based.
- **Migrating stored data.** `algotrade-ingest migrate-ids [--dry-run]` reads the latest
  `instruments/id_map` and rewrites every partition whose latest run holds a mapped id
  (`instrument_id`, `underlying_id`, `parent_id`) as a **new run** with a later
  `knowledge_ts`. Old runs stay readable with `as_of`. Only rows known before the upgrade
  (`known_at`) move, so a symbol id reused later is left alone. A partition that would hold
  both ids is reported, not written. Re-running maps nothing.

Owner steps on an existing store (after the bars backfill finishes):

```bash
algotrade-ingest universe-build            # with ALGOTRADE_MASSIVE_API_KEY set: writes id_map
algotrade-ingest migrate-ids --dry-run     # per-table partition / row counts, writes nothing
algotrade-ingest migrate-ids               # appends the rewritten partitions as new runs
algotrade-ingest migrate-ids --dry-run     # should now report no tables
```
