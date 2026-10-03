# What one nightly run stores

Everything `algotrade-ingest nightly` adds to the store for one session, where it goes, in
what format, and roughly how big it is. Layout and rules: [storage.md](storage.md). Sources:
[vendors.md](vendors.md).

Sizes were measured on 2026-10-02 (13,295 listings, 4,222 optionable underlyings, about
1.67M listed option series) unless marked *est.* Reference, universe, bars, events and raw
sizes were re-measured on the local store after the FIGI rebuild (33 backfilled sessions of
bars). Re-measure when the universe changes a lot.

## Where it goes

Everything lives under `$ALGOTRADE_DATA_URL` (set it in `.env`; default `file://./var/data`).
There are four areas, and only the backend (`storage/backends/`) knows these paths:

| Area | Path | Format | Kept |
|---|---|---|---|
| Tables | `tables/<table>/date=<session>/run=<run_id>.parquet` | Parquet, zstd, rows sorted by `instrument_id`, written atomically | forever (point-in-time history) |
| Table index | `tables/<table>/date=<session>/_runs.json` | JSON `{run_id: knowledge_ts}` so readers pick the run known at `as_of` | forever |
| Raw | `raw/source=<s>/dataset=<d>/date=<session>/run=<run_id>/<key>.json.gz` | the vendor's bytes exactly as received, gzipped (the name says `.json.gz` even for text and xlsx payloads) | per source: its section's `raw_retention_days` (`sec_edgar`: 7), else the global `raw_retention_days` (90) |
| Staging | `staging/<run_id>/<table>/<key>.parquet` | per-ticker Parquet pieces of the chain job | dropped when the run finishes with nothing left to retry (COMPLETE, or PARTIAL without FETCH_ERROR items); otherwise kept for a resume and purged after `staging_retention_days` (14) |
| Run records | `runs/<run_id>.json` | JSON: job, status, per-item statuses, stats | forever (the audit trail every row's `run_id` points to) |

Equity and ETF ids are `EQ:<composite FIGI>` when known, else `EQ:<symbol>` (ADR 0018).
Every table row also carries `session_date`, `knowledge_ts`, `source` and `run_id`
(ADR 0007). Re-running a session adds another `run=` file beside the first one and does not
replace it. Readers take the latest run, and the earlier file stays as history.

## Tables written each night

Nightly order: universe → company details → earnings → bars → rates → corporate actions →
chains → rollups → screens → quality → purge.

| Step | Table | One row is | Rows / night | Parquet / night | Main columns (beyond the common four) |
|---|---|---|---|---|---|
| universe build | `instruments/reference` | every listed security, plus carried-forward delistings (full snapshot) | ~13.3k, grows with delistings | ~0.57 MB (43 B/row) | `symbol`, `name`, `exchange`, `security_type`, `security_type_source`, `is_etf`, `is_test_issue`, `optionable`, `in_sp500`, `status`, `first_seen`, `delisted_on`, `figi`, `share_class_figi`, `cik`, `is_leveraged`, `is_inverse`, `leverage`, `tracks`, `leverage_source`, `multiplier`, `tick_size`, `currency` |
| | `universe` | a covered instrument (full snapshot) | ~11.4k | ~0.31 MB | `symbol`, `company_name`, `security_type`, `asset_class`, `exchange`, `status`, `optionable`, `universe_version`, `last_verified` |
| | `instruments/symbol_history` | a FIGI × symbol validity interval (full history every night) | ~10.8k, grows slowly | ~0.2 MB | `figi`, `symbol`, `valid_from`, `valid_to` |
| | `instruments/id_map` | a symbol id → FIGI id upgrade (cumulative, full map every night; ADR 0018) | ~10.8k (one per FIGI upgrade so far), grows slowly | ~0.26 MB | `old_id`, `new_id`, `symbol`, `effective`, `known_at` |
| | `events/reference_change` | an add / remove / rename / type, optionable, exchange, ticker or id change | usually 0–50 (one-offs: ~13k on the first build, ~10.8k `id_changed` on the FIGI switch) | tiny; skipped when empty | `change`, `old`, `new`, `ts` |
| | `events/index_change` | an S&P 500 add or remove | usually 0 | tiny; skipped when empty | `change`, `old`, `new`, `ts` |
| company details | `instruments/company` | an instrument with a known company (full snapshot) | ~7.5k *est.* (instruments with a CIK) | ~0.3 MB *est.* | `cik`, `name`, `entity_type`, `sic`, `sic_description`, `sector`, `industry`, `state_of_incorporation`, `fiscal_year_end`, `website`, `fetched_on`, … |
| shares | `instruments/shares` | a new share-count fact or a `checked` marker, per instrument of each CIK refetched (~1/30 of CIKs a night) | ~250 markers + new facts *est.* (backfill: ~1.5M rows *est.*) | small *est.* | `cik`, `concept`, `period_end`, `filed`, `form`, `accn`, `shares`, `fetched_on`, … |
| earnings | `events/earnings` | a company × report date in the next 60 days | ~4.4k | ~0.06 MB | `earnings_date`, `time`, `fiscal_quarter`, `eps_forecast`, `estimates`, `eps_reported`, `surprise_pct` |
| bars | `bars/1d` | an instrument × session, unadjusted OHLCV | ~10.7k | ~0.42 MB (39 B/row) | `ts`, `open`, `high`, `low`, `close`, `volume`, `vwap`, `trades` |
| corporate actions | `events/split`, `events/dividend` | a split / dividend in the window −7…+30 days | ~5k dividends, ~150 splits | ~0.06 MB | split: `split_from`, `split_to`, `ratio`; dividend: `cash_amount`, `pay_date`, `record_date`, `frequency`, … |
| chains | **`chains/option_quotes`** | an option contract × session | **~1.5M** | **~55 MB** (measured 37 B/row) | `underlying_id`, `ts`, `root`, `expiry`, `right`, `strike`, `last`, `bid`, `ask`, `bid_size`, `ask_size`, `volume`, `open_interest`, `iv`, `delta`, `gamma`, `vega`, `theta`, `rho`, `theo` |
| | `chains/underlying_quotes` | an underlying × session | ~4.2k | ~0.3 MB *est.* | `price`, `open`, `high`, `low`, `close`, `prev_close`, `volume`, `iv30` |
| | `chains/status` | every universe underlying, fetched or not | ~4.2k | tiny | `status` (OK, NO_CHAIN, NO_STANDARD_SERIES, STALE_DATA, FETCH_ERROR) |
| rollups | `rollups/instrument/option_liquidity@v1` | an underlying × session | ~4.2k | ~0.3 MB *est.* | `liq_status`, `put_tier`, `call_tier`, `chain_oi`, `chain_volume`, `expiries_within_60d`, `underlying_price`, `iv30`, … |
| | `rollups/instrument/price_stats@v1` | an instrument with a bar that session | ~12.6k (measured 2026-10-02) | ~1 MB *est.* | `close`, `sma_20/50/200`, `ret_20d/60d`, `high_52w`, `low_52w`, `pct_from_high/low_52w`, `hv20`, `hv30`, `hv20_yz`, `adv_usd_20d`, `history_days` |
| | `rollups/instrument/earnings@v1` | an instrument with a known next / last report | ~4.4k | ~0.05 MB *est.* | `next_earnings_date`, `earnings_time`, `days_to_earnings`, `date_confirmed`, `last_earnings_date` |
| screens | `results/<screener>` | an instrument the screener evaluated | up to ~4.2k per screener | small | defined by the screener |

**About 58 MB of tables per night, which is about 14.6 GB a year** (252 sessions). Option
quotes are about 95% of that; everything else together is about 3 MB. Reference, universe,
symbol history, id map and company are full snapshots every night, so they repeat mostly
unchanged rows. That costs about 1.6 MB a night (about 0.4 GB a year) and keeps "as of D"
reads to one file each.

Screener CSV exports go to `--export-dir` (outside the store) and are not counted here.

## Raw responses saved each night (purged after 90 days; SEC after 7)

| Source / dataset | Files per night | Size per night (gzipped) |
|---|---|---|
| `cboe` / option chain | one per underlying, ~4.2k | **~90 MB** (measured ~60 B per contract) |
| `nasdaq_trader` / symbol_directory | 3 (`nasdaqlisted`, `otherlisted`, `options`) | ~5.1 MB, almost all of it the `options` file |
| `ssga_spy` / spy_holdings | 1 | ~55 KB |
| `massive` / tickers, grouped_daily, corporate_actions | 1 + 1 + 2 | ~0.9 MB (grouped daily 0.3, tickers 0.25, corporate-action window ~0.35) |
| `nasdaq_earnings` / earnings_calendar | 60 (one per calendar day ahead) | ~0.25 MB |
| `sec_edgar` / company_tickers + submissions + companyfacts | 1 + the CIKs due a refresh (about 1/30 of companies a night, each for submissions and company facts) | ~30 MB (~36 KB per submission and ~115 KB per company-facts file, measured on the 2026-10-02 full load: 6,280 + 6,032 files, 116 + 690 MB), kept 7 days |

**About 125 MB of raw responses per night**, ~70% of it Cboe chains. Retention is per source
(`raw_retention_days` in a `sources.toml` vendor section overrides the global 90 days): the
SEC responses (submissions, company tickers, company facts) are kept 7 days (~5 sessions,
~0.15 GB), everything else 90 days (about 62–64 sessions, ~6 GB, Cboe ~5.7 GB of it). The raw
area settles at **about 6 GB** and stops growing. To shrink it further, give `[cboe]` its own
`raw_retention_days`, or skip saving the Nasdaq `options` file (only its ~4.2k distinct
underlyings are used).

## Run records and scratch

- `runs/`: about 10 JSON files a night (one per step, plus each screener). The chain run
  lists a status for every underlying, so it is the largest at about 200 KB *est.*
- `staging/`: empty after every chain run that finishes with nothing to retry (COMPLETE, or
  PARTIAL from stale or missing chains only). A run with FETCH_ERROR items, or a FAILED run,
  keeps its pieces (up to the size of that night's option quotes) so a re-run can resume;
  the resume drops them when it finishes, else `staging_retention_days` does.

## One-off loads

| Load | Tables | Raw |
|---|---|---|
| 2-year bars backfill (~500 sessions) | ~210 MB | ~150 MB; partitions are dated by the bar's session, so the next nightly purge removes them |
| Corporate actions backfill (26 months) | ~1.2 MB (113k dividends, 3.3k splits) | ~7.6 MB, purged after 90 days |
| First SEC company load (~6k CIKs) | ~0.3 MB | ~215 MB, purged after 7 days |
| `migrate-ids` (ADR 0018) | rewrites each migrated partition as a new run beside the old one: ~15 MB for 33 sessions of bars plus the event backfills | none |

Running `migrate-ids` after the full backfill would duplicate every bars partition (~0.2 GB),
so migrate before backfilling, as was done here.

## Total

| | Per night | Steady state / growth |
|---|---|---|
| Tables | ~58 MB | +14.6 GB a year |
| Raw | ~125 MB | ~6 GB rolling (90 days; SEC 7 days) |
| Runs | ~0.5 MB | +0.1 GB a year |

Tables are never deleted (point-in-time history), so the store has no ceiling: it grows by
about 14.6 GB a year on top of a raw area that levels off at about 6 GB.

| After | Tables | Raw | Total |
|---|---|---|---|
| Backfill only (no chains yet) | ~0.25 GB | ~0.4 GB briefly, then <0.1 GB | **~0.3 GB** |
| 1 year of nightly runs | ~15 GB | ~6 GB | **~21 GB** |
| 3 years | ~44 GB | ~6 GB | **~50 GB** |
| 5 years | ~73 GB | ~6 GB | **~79 GB** |

The only lever that matters is option quotes (~14 GB a year). Ways to cap it, if needed:
keep only expiries within N days or strikes within a delta band, or move older partitions to
S3 (see [storage.md](storage.md)). Without chains, the store grows by under 1 GB a year.
