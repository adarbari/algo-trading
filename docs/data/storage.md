# Storage: data grains, layout, formats, adapters

Decision record: [ADR 0006](../adr/0006-storage-grains-and-adapters.md),
[ADR 0007](../adr/0007-point-in-time-data.md).

## Data grains

"Per ticker" is a **key**, not a folder. The real question for every dataset is its
**grain**: one row is one *what*? Ticker-level, ticker-day and ticker-day-time are three of
the grains below. A few others are needed for a trading system.

| Grain | One row is… | Examples | Updated |
|---|---|---|---|
| **reference** | an instrument, over a validity interval | symbol, name, exchange, asset class, ETF flag, leverage factor, underlying, multiplier, expiry, sector, listing and delisting dates | slowly; stored as history, never overwritten |
| **event** | something that happened to an instrument at a point in time | splits, dividends, earnings dates, symbol changes, index adds and removes, futures first-notice and expiry dates | irregular |
| **bar(interval)** | an instrument × a time bucket | `1d` = ticker-day OHLCV; `1h`, `5m`, `1m` = ticker-day-time | nightly (`1d`), intraday later |
| **curve** | a curve date × a tenor | `rates/treasury`: the Treasury par yield curve, one partition per curve date (ADR 0021) | daily |
| **chain snapshot** | a derivative contract × an observation time | end-of-day option chain: bid, ask, last, volume, open interest, IV, Greeks | nightly |
| **tick** | a single trade or quote | trades, NBBO quotes | reserved; not planned on free data |
| **universe** | an instrument × a date it belongs to a universe | "in S&P 500 on 2026-10-02", "optionable", "leveraged ETF" | daily snapshot |
| **cross-section / market** | a date (or time) for the whole market | breadth, VIX level, sector aggregates | nightly |
| **feature** | an instrument (or market) × as-of time × feature@version | `sma_20@v1`, `iv_rank_252d@v1` | nightly, more often later |
| **result** | a run × an output row | screener hits, backtest equity curves, fills, metrics | per run |

Ticker-day and ticker-day-time are **the same grain (bar) with different intervals**, so
they share one schema, one store and one adapter. Adding `1m` bars later means a new
`interval` value, not a new design.

## Common columns

Every market and feature row carries:

| Column | Meaning |
|---|---|
| `instrument_id` | Stable internal id (see [instruments.md](instruments.md)). Never the ticker, because tickers get reused and renamed. |
| `ts` | Event time, UTC (bar start, observation time or event time). |
| `session_date` | The exchange trading day this row belongs to (futures sessions start the evening before). |
| `knowledge_ts` | When we learned this value (ingestion time, UTC). Used for point-in-time reads. |
| `source` | Which vendor or adapter produced it. |
| `run_id` | Lineage back to the run (and its raw files and run record). |

## Processing tiers

```
raw/          as received from the vendor (JSON/CSV, gzip). Never modified. Kept for a retention
              window (default 90 days, ADR 0014) so recent days can be replayed.
normalized/   validated, canonical schema, Parquet. What readers use.
features/     derived values, versioned by name@version, Parquet.
results/      screener and backtest outputs, keyed by run id, Parquet + a JSON run record.
catalog       run log, dataset and schema versions, data-quality checks (a DuckDB or SQLite file).
```

## Physical layout (local backend, as implemented)

```
$ALGOTRADE_DATA_URL (default file://./var/data, git-ignored)
  tables/<table>/date=YYYY-MM-DD/run=<run_id>.parquet   + _runs.json (knowledge_ts per run;
                                                         {knowledge_ts, restates} for a
                                                         restating run)
  raw/source=<s>/dataset=<d>/date=YYYY-MM-DD/run=<run_id>/<key>.json.gz
  staging/<run_id>/<table>/<key>.parquet                 per-item scratch for resumable jobs
                                                         (cleared on completion; unfinished
                                                         runs purged after 14 days)
  runs/<run_id>.json                                     run records: audit + checkpoint
```

What each nightly run adds, table by table, with sizes: [nightly-footprint.md](nightly-footprint.md).

Implemented tables (layers per [layers.md](layers.md)):
L1 `instruments/reference`, `instruments/symbol_history`, `instruments/id_map` (symbol id →
FIGI id upgrades, ADR 0018), `instruments/company`; L2 `bars/<interval>` (1d, 1h, 30m, 15m, 5m, 1m; OHLCV
sanity-checked on write), `chains/underlying_quotes`, `chains/option_quotes`,
`chains/status`, `events/<type>`, `rates/treasury` (one partition per curve date); rollups `rollups/daily/*` and `rollups/instrument/*`
(e.g. `rollups/instrument/option_liquidity@v1`); `universe`; `catalog/*`; `results/<name>`.
## Column types and schema version

`storage/tables/schemas.py` is the data contract. Every **fixed** table (`universe`,
`instruments/*`, `chains/*`, `bars/<interval>`) declares every column with an abstract type
and nullability; open tables (`events/*`, `rollups/*`, `results/*`, `catalog/*`) declare the
point-in-time columns and their keys (`instrument_id`, `ts` for events), and the producer
defines the rest.

| Abstract type | Parquet / Arrow (local backend) | pandas on read |
|---|---|---|
| `string` | `large_string` | `str` |
| `float64` | `double` | `float64` |
| `int64` | `int64` | `int64` (`float64` with nulls) |
| `bool` | `bool` | `bool` (`object` with nulls) |
| `date` | `date32` | `datetime.date` objects |
| `timestamp_utc` | `timestamp[us, tz=UTC]` | `datetime64[us, UTC]` |

On **write**, `StoreWriter` / `ResultWriter` validate (required and undeclared columns, null
point-in-time columns or keys, duplicate keys, OHLCV sanity) and every backend casts through
`storage/backends/arrow.py`: each declared column to its type (ints → floats, `string` vs
`large_string`, all-null columns, second- or millisecond timestamps all become the declared
type). Uncastable data (`multiplier = "one"`), nulls in a non-nullable column and undeclared
columns of a fixed table fail with `DataValidationError`. The memory backend stores the same
typed frame, so both backends return identical dtypes.

Each Parquet file's schema metadata carries `algotrade.table` and
`algotrade.schema_version` (`SCHEMA_VERSION`, now 1; files written before had none). On
**read**, each file's declared columns are cast to today's types, so older files (e.g.
`bars/1d` partitions whose `instrument_id` was `string` while others were `large_string`,
or all-null `delisted_on` columns) read exactly like new ones, and fixed tables concatenate
without type widening. Only open tables still use `promote_options="permissive"`, because
their producer-defined columns may legitimately differ between runs. Changing a declared
type is a schema change: bump `SCHEMA_VERSION`, keep reads of older files working, and
record why.

**Row groups.** Files are written with `row_group_size` ≈ 64k rows, zstd and a page index
(`write_page_index=True`), so filtered reads (`instrument_id`, `underlying_id`) skip row
groups and pages whose statistics cannot match (tested in
`tests/contract/storage/test_typed_tables.py`). Producers write rows clustered by key (bars
by instrument, option quotes by underlying through per-underlying staging), which is what
makes the statistics selective.

## Reading

Consumers (services, engines, apps) read market data only through `algotrade.data`
(ADR 0019 R1, an import-linter contract); `storage/tables/readers.py` is the generic reader it
builds on: `table`, `table_range` (date range, each partition resolved point-in-time),
`dates`, `latest_date`, `runs` and `table_names` (every table with data; backends implement
`TableStore.names()`). Storage holds no domain rules (R2).

| Module | Reads | Rule |
|---|---|---|
| `data/reference.py` | `instruments`, `instrument_terms`, `instrument_view` (`InstrumentView`), `load_universe`, `resolver` | **one snapshot rule**, `snapshot(reader, table, on)`: the latest snapshot on or before `on`, else the earliest, with `pre_snapshot = True` (survivorship bias: a later instrument list). Used for reference, company, universe and id map |
| `data/prices.py` | `bars`, `load_price_data` (+ `adjust_bars`) | bars by session date; splits / dividends applied at read time |
| `data/events.py` | `read_events` | by **event date** (`ts`) from any partition (each partition's runs already merged), latest `knowledge_ts` per event key |
| `data/chains.py` | `option_quotes` (filter by `underlying_ids`), `underlying_quotes`, `chain_status` | one session's chain snapshot |

Every read takes `as_of`, a **version pin** (ADR 0007): only runs known at `as_of` count.
Backtests pass their launch time and record it with the run ids read.

## How runs combine

A partition (`table`, `session_date`) can hold several runs (a backfill, then nightly runs
into the same session, a `migrate_ids` rewrite). Each table declares in its `TableSpec`
(`runs`, `storage/tables/schemas.py`) how they combine, and the backends apply it through
`storage/backends/run_selection.py` (the one owner; ADR 0007 "How runs combine"), so
`table` and `table_range` return the combined view on every backend:

| Mode | Tables | A read at `as_of` sees |
|---|---|---|
| `snapshot` | `universe`, `instruments/reference`, `instruments/company`, `bars/<interval>` (a re-fetch replaces the session), `chains/*`, `rates/treasury`, `rollups/*`, `catalog/*`, `results/*` | the one run with the latest `knowledge_ts` <= `as_of` (ties: run id) |
| `merge` | `events/*` (`dividend`, `split`, `earnings`, `reference_change`, `index_change`, …) | the union of every run with `knowledge_ts` <= `as_of`, from the latest **restating** run on; per table key (`instrument_id`, `ts`, + `change`) the latest run's row wins |
| `merge` | `instruments/id_map` (key `old_id`, `new_id`), `instruments/symbol_history` (key `figi`, `symbol`, `valid_from`) | as above, on the table's own key (`TableSpec.key`). Both are cumulative and a build only adds to them (an upgrade, an opened or closed row), so a re-run that saw less cannot hide what an earlier run of the session recorded (2026-10-03: a 3-row id map hid 10,817 upgrades) |

- **Restating runs**: `StoreWriter.write_table(..., restates=True)` (used by
  `IngestRun.rewrite`, i.e. `migrate_ids`) says the frame is the whole partition as read
  now. The local backend records it in `_runs.json` as `{"knowledge_ts": …, "restates":
  true}` (plain runs keep `run -> knowledge_ts`); snapshot tables ignore it. `migrate_ids`
  rewrites a merge partition as the full remapped union (an old-id row landing on a key a
  new-id row already holds yields to the later-known row), so old-id rows are not
  resurrected; reads pinned before the rewrite still see the old union.
- **No deletes**: a later merge run that lacks an event does not remove it (a cancelled
  dividend, an earnings date rescheduled within one session); a later row for the same key
  replaces it. Tombstones are future work (ADR 0007).
- Runs merge **within** a partition; `data/events.py` still filters by event date and keeps
  the latest `knowledge_ts` per event key **across** partitions.

## Target physical layout (as more grains arrive)

Partition by **time**, and sort by `instrument_id` inside each file. Partitioning by ticker
would create hundreds of thousands of tiny files once the universe is around 10k
instruments. Sorting plus Parquet row-group statistics keeps single-ticker reads fast.

```
$ALGOTRADE_DATA_URL (default file://./var/data, git-ignored)
  raw/source=<vendor>/dataset=<name>/date=YYYY-MM-DD/<run_id>.json.gz
  normalized/reference/instruments/valid_from=YYYY-MM-DD/part-*.parquet
  normalized/events/type=<split|dividend|earnings|...>/year=YYYY/part-*.parquet
  normalized/bars/interval=1d/year=YYYY/month=MM/date=YYYY-MM-DD.parquet
  normalized/bars/interval=1m/date=YYYY-MM-DD/part-*.parquet
  normalized/chains/asset=option/date=YYYY-MM-DD/part-*.parquet
  normalized/universe/date=YYYY-MM-DD.parquet
  features/<feature>@<version>/date=YYYY-MM-DD.parquet
  results/<kind>/run_id=<id>/{rows.parquet, run.json}
  catalog.duckdb
```

A compaction job can later merge daily files into monthly ones. The partition layout is an
internal detail of the backend; nothing outside `storage/backends/` relies on it.

## Format and engine

- **Parquet** (columnar, compressed, free, readable by every tool) for all normalized,
  feature and result data.
- **DuckDB** (embedded, free, no server) as the query engine and the catalog: **planned, not
  used yet** (tables are read with pyarrow today). It reads
  Parquet on local disk or in S3-compatible storage with the same SQL.
- **Rough size:** end-of-day option chains for about 4k optionable underlyings are about
  1–1.5M rows a day, roughly 10–20 GB a year as Parquet. Daily bars for about 10k
  instruments are tiny.

## Adapters: changing storage without touching callers

```
storage/
  tables/
    interfaces.py      Protocols per grain: ReferenceStore, EventStore, BarStore, ChainStore,
                       UniverseStore, FeatureStore, ResultStore, Catalog
    schemas.py         canonical column schemas, declared types + validation (the data contract)
    readers.py         generic read-only facade (tables, ranges, dates, runs); domain reads are
                       algotrade/data/ (reference, prices, events, chains, resolver)
    writers.py         write facade. Only apps/ingestion may import this (import-linter).
    result_writer.py   results/<name> + run records for screens and backtests
  backends/
    local.py           now: Parquet on the local filesystem (DuckDB-readable)
    memory.py          in-memory backend for tests
    arrow.py           casts to declared types, schema_version, row groups
    run_selection.py   which runs a read sees (snapshot / merge, restating runs), merging
                       rows per table key, instrument selection: shared by the backends
    (s3_parquet.py)    later: same files in S3-compatible object storage
    (postgres.py, clickhouse.py, ...)  only if ever needed
  configs/             config documents only (never imports tables/ or backends/)
    store.py           the ConfigStore protocol
    files.py           file and memory config stores
  runs.py, locks.py    run records; named locks
  factory.py           open_backend(url) picks the backend; the URL comes from
                       config/env.py (ALGOTRADE_DATA_URL), storage reads no environment
```

Interface shape (illustrative):

```python
class BarStore(Protocol):
    def read(self, instruments: Sequence[str], interval: str, start: date, end: date,
             as_of: datetime | None = None) -> BarFrame: ...
    def write(self, bars: BarFrame, run: IngestRun) -> None: ...   # writers only
```

**Contract tests:** `tests/contract/storage/` holds one shared test suite that every
backend must pass (round-trip, point-in-time `as_of`, idempotent re-writes, schema
rejection, partition pruning). A new backend counts as done only when it passes the same
suite as `parquet_local`. That is what makes swapping backends safe.

**Golden data uses the same adapters.** Tests point `ALGOTRADE_DATA_URL` at a fixture
store built from the golden datasets, so backtests in CI go through exactly the code path
production uses.

## Moving to S3

The location is a URL, so moving is a configuration change once an S3 backend exists:
copy the store (`aws s3 sync var/data s3://bucket/prefix`), then set
`ALGOTRADE_DATA_URL=s3://bucket/prefix` in `.env`. The object keys stay the same as the local
paths, so DuckDB and other tools read them unchanged. Nothing outside `storage/backends/` changes.

Not built yet. An `s3_parquet` backend needs to:

- **Pass `tests/contract/storage/`** (against a local S3 emulator in CI; no network).
- **Write objects directly.** An S3 PUT is atomic per object, so the local backend's
  temp-file-then-rename step is not needed.
- **Avoid the `_runs.json` read-modify-write.** Two writers to the same partition could
  lose an entry. Either keep a single writer per partition (true today: one nightly job), or
  drop the index and resolve runs by listing `run=*.parquet` and reading `knowledge_ts` from
  each file's metadata.
- **List by prefix and delete in batches** for `dates()` and the purges, instead of
  directory walks. S3 lifecycle rules on `raw/` (90 days) and `staging/` (14 days) can
  replace the nightly purge.
- **Take credentials from the standard AWS environment** (`AWS_PROFILE` or keys in `.env`),
  never from the URL. Put the SDK dependency in the library's pyproject, as an optional extra.

## Rules

1. Writes are **idempotent** per (dataset, partition, source). Re-running a day replaces that
   day's rows, never duplicates them.
2. Corrections are new rows with a later `knowledge_ts`. Readers asking `as_of=T` get what
   was known at T.
3. Schemas are typed and versioned in `schemas.py` (`SCHEMA_VERSION`, stamped in every file).
   Breaking changes need a migration plus an ADR.
4. No caller builds file paths. Paths exist only inside `storage/backends/`.
