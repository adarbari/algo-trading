# What one nightly run stores

Everything `algotrade-ingest nightly` adds to the store for one session, where it goes, in
what format, and roughly how big it is. Layout and rules: [storage.md](storage.md). Sources:
[vendors.md](vendors.md).

Sizes were measured on 2026-10-02 (13,295 listings, 4,222 optionable underlyings, about
1.67M listed option series) unless marked *est.* Re-measure when the universe changes a lot.

## Where it goes

Everything lives under `$ALGOTRADE_DATA_URL` (set it in `.env`; default `file://./var/data`).
There are four areas, and only the backend (`storage/backends/`) knows these paths:

| Area | Path | Format | Kept |
|---|---|---|---|
| Tables | `tables/<table>/date=<session>/run=<run_id>.parquet` | Parquet, zstd, rows sorted by `instrument_id`, written atomically | forever (point-in-time history) |
| Table index | `tables/<table>/date=<session>/_runs.json` | JSON `{run_id: knowledge_ts}` so readers pick the run known at `as_of` | forever |
| Raw | `raw/source=<s>/dataset=<d>/date=<session>/run=<run_id>/<key>.json.gz` | the vendor's bytes exactly as received, gzipped (the name says `.json.gz` even for text and xlsx payloads) | `raw_retention_days` (90) |
| Staging | `staging/<run_id>/<table>/<key>.parquet` | per-ticker Parquet pieces of the chain job | cleared when the run completes; unfinished runs purged after `staging_retention_days` (14) |
| Run records | `runs/<run_id>.json` | JSON: job, status, per-item statuses, stats | forever (the audit trail every row's `run_id` points to) |

Equity and ETF ids are `EQ:<composite FIGI>` when known, else `EQ:<symbol>` (ADR 0018).
Every table row also carries `session_date`, `knowledge_ts`, `source` and `run_id`
(ADR 0007). Re-running a session adds another `run=` file beside the first one and does not
replace it. Readers take the latest run, and the earlier file stays as history.

## Tables written each night

Nightly order: universe → company details → earnings → bars → corporate actions → chains →
features → screens → quality → purge.

| Step | Table | One row is | Rows / night | Parquet / night | Main columns (beyond the common four) |
|---|---|---|---|---|---|
| universe build | `instruments/reference` | every listed security, plus carried-forward delistings (full snapshot) | ~13.3k, grows with delistings | ~1 MB *est.* | `symbol`, `name`, `exchange`, `security_type`, `security_type_source`, `is_etf`, `is_test_issue`, `optionable`, `in_sp500`, `status`, `first_seen`, `delisted_on`, `figi`, `share_class_figi`, `cik`, `is_leveraged`, `is_inverse`, `leverage`, `tracks`, `leverage_source`, `multiplier`, `tick_size`, `currency` |
| | `universe` | a covered instrument (full snapshot) | ~10–11k *est.* | ~0.3 MB *est.* | `symbol`, `company_name`, `security_type`, `asset_class`, `exchange`, `status`, `optionable`, `universe_version`, `last_verified` |
| | `instruments/symbol_history` | a FIGI × symbol validity interval (full history every night) | ~11k, grows slowly | ~0.5 MB *est.* | `figi`, `symbol`, `valid_from`, `valid_to` |
| | `instruments/id_map` | a symbol id → FIGI id upgrade (cumulative, full map every night; ADR 0018) | grows as instruments gain FIGIs | tiny | `old_id`, `new_id`, `symbol`, `effective`, `known_at` |
| | `events/reference_change` | an add / remove / rename / type, optionable, exchange, ticker or id change | usually 0–50 | tiny; skipped when empty | `change`, `old`, `new`, `ts` |
| | `events/index_change` | an S&P 500 add or remove | usually 0 | tiny; skipped when empty | `change`, `old`, `new`, `ts` |
| company details | `instruments/company` | an instrument with a known company (full snapshot) | ~6–8k *est.* | ~1 MB *est.* | `cik`, `name`, `entity_type`, `sic`, `sic_description`, `sector`, `industry`, `state_of_incorporation`, `fiscal_year_end`, `website`, `fetched_on`, … |
| earnings | `events/earnings` | a company × report date in the next 60 days | a few thousand *est.* | ~0.2 MB *est.* | `earnings_date`, `time`, `fiscal_quarter`, `eps_forecast`, `estimates`, `eps_reported`, `surprise_pct` |
| bars | `bars/1d` | an instrument × session, unadjusted OHLCV | ~11–12k *est.* | ~0.5 MB *est.* | `ts`, `open`, `high`, `low`, `close`, `volume`, `vwap`, `trades` |
| corporate actions | `events/split`, `events/dividend` | a split / dividend in the window −7…+30 days | tens to a few thousand | tiny | split: `split_from`, `split_to`, `ratio`; dividend: `cash_amount`, `pay_date`, `record_date`, `frequency`, … |
| chains | **`chains/option_quotes`** | an option contract × session | **~1.5M** | **~55 MB** (measured 37 B/row) | `underlying_id`, `ts`, `root`, `expiry`, `right`, `strike`, `last`, `bid`, `ask`, `bid_size`, `ask_size`, `volume`, `open_interest`, `iv`, `delta`, `gamma`, `vega`, `theta`, `rho`, `theo` |
| | `chains/underlying_quotes` | an underlying × session | ~4.2k | ~0.3 MB *est.* | `price`, `open`, `high`, `low`, `close`, `prev_close`, `volume`, `iv30` |
| | `chains/status` | every universe underlying, fetched or not | ~4.2k | tiny | `status` (OK, NO_CHAIN, NO_STANDARD_SERIES, STALE_DATA, FETCH_ERROR) |
| features | `rollups/instrument/option_liquidity@v1` | an underlying × session | ~4.2k | ~0.3 MB *est.* | `liq_status`, `put_tier`, `call_tier`, `chain_oi`, `chain_volume`, `expiries_within_60d`, `underlying_price`, `iv30`, … |
| screens | `results/<screener>` | an instrument the screener evaluated | up to ~4.2k per screener | small | defined by the screener |

**About 60 MB of tables per night, which is about 15 GB a year** (252 sessions). Option quotes
are over 90% of that. Reference, universe, symbol history, id map and company are full snapshots every
night, so they repeat mostly unchanged rows. That costs about 3 MB a night (under 1 GB a year)
and keeps "as of D" reads to one file each.

Screener CSV exports go to `--export-dir` (outside the store) and are not counted here.

## Raw responses saved each night (purged after 90 days)

| Source / dataset | Files per night | Size per night (gzipped) |
|---|---|---|
| `cboe` / option chain | one per underlying, ~4.2k | **~90 MB** (measured ~60 B per contract) |
| `nasdaq_trader` / symbol_directory | 3 (`nasdaqlisted`, `otherlisted`, `options`) | ~5.8 MB, of which `options` is 5.6 MB |
| `ssga_spy` / spy_holdings | 1 | ~55 KB |
| `massive` / tickers, grouped_daily, corporate_actions | 1 + 1 + 2 | ~1–2 MB *est.* |
| `nasdaq_earnings` / earnings_calendar | 60 (one per calendar day ahead) | ~1 MB *est.* |
| `sec_edgar` / company_tickers + submissions | 1 + the CIKs due a refresh (about 1/30 of companies a night) | ~10–20 MB *est.* |

**About 110 MB of raw responses per night.** With 90-day retention (about 64 sessions) that
settles at **about 7 GB**. To shrink it, shorten `raw_retention_days`, or skip saving the
Nasdaq `options` file (only its ~4.2k distinct underlyings are used).

## Run records and scratch

- `runs/`: about 10 JSON files a night (one per step, plus each screener). The chain run
  lists a status for every underlying, so it is the largest at about 200 KB *est.*
- `staging/`: empty after a complete chain run. A partial run keeps its pieces (up to the
  size of that night's option quotes) so a re-run can resume, until `staging_retention_days`.

## Total

| | Per night | Steady state / growth |
|---|---|---|
| Tables | ~60 MB | +15 GB a year |
| Raw | ~110 MB | ~7 GB rolling (90 days) |
| Runs | ~0.5 MB | +0.1 GB a year |
