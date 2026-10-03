"""Load the committed golden CSVs into a store, through the normal writers.

Writes, for every golden dataset:
- ``bars/1d``: one partition per session date (instrument ids ``EQ:<SYMBOL>``)
- ``instruments/reference``: one snapshot at the first session (multiplier-1 equities)
- ``catalog/golden_datasets``: which instruments make up which dataset

Load into a dedicated fixture store (``make golden-store``), never the production store:
synthetic symbols such as ``AAA`` collide with real tickers.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime

import pandas as pd

from algotrade.core.instruments import AssetClass, instrument_id
from algotrade.storage.runs import RunRecord, RunStatus, new_run_id
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.jobs.common import stamp
from algotrade_ingestion.sources.synthetic.files import GoldenFiles

JOB = "golden_load"
SOURCE = "synthetic"
CATALOG = "catalog/golden_datasets"


def _collect(files: GoldenFiles) -> tuple[pd.DataFrame, pd.DataFrame]:
    bars, catalog = [], []
    for ds in files.manifest().values():
        for symbol in ds.symbols:
            iid = instrument_id(AssetClass.EQUITY, symbol)
            frame = files.read(ds.name, symbol)
            frame.insert(0, "instrument_id", iid)
            bars.append(frame)
            catalog.append({"instrument_id": iid, "symbol": symbol, "dataset": ds.name,
                            "description": ds.description, "tags": ",".join(ds.tags)})  # fmt: skip
    return pd.concat(bars, ignore_index=True), pd.DataFrame(catalog)


def load_golden(
    writer: StoreWriter,
    files: GoldenFiles,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> RunRecord:
    problems = files.verify()
    if problems:
        raise ValueError(f"golden files failed verification: {problems}")
    bars, catalog = _collect(files)
    bars["session_date"] = bars["ts"].dt.date
    first: date = min(bars["session_date"])
    now = clock()
    run_id = new_run_id(JOB, first, now)
    stamped = stamp(bars.drop(columns="session_date"), first, now, SOURCE, run_id)
    stamped["session_date"] = bars["session_date"]  # stamp sets one date; bars span many
    stamped = stamped.sort_values(["session_date", "instrument_id"], kind="stable")
    for key, day in stamped.groupby("session_date", sort=True):
        session = key if isinstance(key, date) else date.fromisoformat(str(key))
        writer.write_table("bars/1d", session, run_id, day.reset_index(drop=True))
    reference = catalog[["instrument_id", "symbol"]].drop_duplicates().assign(
        asset_class=AssetClass.EQUITY.value, security_type="COMMON_STOCK", multiplier=1.0,
        tick_size=0.01, currency="USD", status="ACTIVE",
    )  # fmt: skip
    writer.write_table(
        "instruments/reference", first, run_id, stamp(reference, first, now, SOURCE, run_id)
    )
    writer.write_table(CATALOG, first, run_id, stamp(catalog, first, now, SOURCE, run_id))
    stats = {"datasets": int(catalog["dataset"].nunique()), "instruments": len(reference),
             "sessions": int(bars["session_date"].nunique()), "bars": len(bars)}  # fmt: skip
    record = RunRecord(run_id, JOB, first, now, RunStatus.COMPLETE, now, stats=stats)
    writer.save_run(record)
    return record
