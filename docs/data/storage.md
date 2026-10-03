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
| `ingest_run_id` | Lineage back to the ingestion run and its raw file. |

## Processing tiers

```
raw/          as received from the vendor (JSON/CSV, gzip). Never modified, kept forever. Allows replays.
normalized/   validated, canonical schema, Parquet. What readers use.
features/     derived values, versioned by name@version, Parquet.
results/      screener and backtest outputs, keyed by run id, Parquet + a JSON run record.
catalog       run log, dataset and schema versions, data-quality checks (a DuckDB or SQLite file).
```

## Physical layout (local backend)

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
- **DuckDB** (embedded, free, no server) as the query engine and the catalog. It reads
  Parquet on local disk or in S3-compatible storage with the same SQL.
- **Rough size:** end-of-day option chains for about 4k optionable underlyings are about
  1–1.5M rows a day, roughly 10–20 GB a year as Parquet. Daily bars for about 10k
  instruments are tiny.

## Adapters: changing storage without touching callers

```
storage/
  interfaces.py        Protocols per grain: ReferenceStore, EventStore, BarStore, ChainStore,
                       UniverseStore, FeatureStore, ResultStore, Catalog
  schemas.py           canonical column schemas + validation (the data contract)
  readers.py           read-only facade handed to backtest / api / engines
  writers.py           write facade. Only apps/ingestion may import this (import-linter).
  backends/
    parquet_local.py   now: Parquet + DuckDB on the local filesystem
    (s3_parquet.py)    later: same files in S3-compatible object storage
    (postgres.py, clickhouse.py, ...)  only if ever needed
  factory.py           open_stores(url) picks the backend from ALGOTRADE_DATA_URL
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

## Rules

1. Writes are **idempotent** per (dataset, partition, source). Re-running a day replaces that
   day's rows, never duplicates them.
2. Corrections are new rows with a later `knowledge_ts`. Readers asking `as_of=T` get what
   was known at T.
3. Schemas are versioned in `schemas.py`. Breaking changes need a migration plus an ADR.
4. No caller builds file paths. Paths exist only inside `storage/backends/`.
