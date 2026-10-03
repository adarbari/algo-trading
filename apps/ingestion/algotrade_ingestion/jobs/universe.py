"""Import the monthly master universe CSVs into a dated universe snapshot.

Accepts the files produced by the existing monthly refresh process
(``optionable_us_stock_universe.csv``, ``optionable_us_etf_universe.csv``). Only ``ticker``
is required; missing optional columns get conservative defaults. Every row is kept;
filtering to production rows happens at read time (``services.views.load_universe``).
"""

import csv
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from algotrade.core.errors import DataValidationError
from algotrade.core.instruments import AssetClass, instrument_id
from algotrade.storage.runs import RunRecord, RunStatus, new_run_id
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.jobs.common import stamp

JOB = "universe_import"
OPTIONAL = (
    "company_name",
    "security_type",
    "exchange",
    "status",
    "optionable",
    "last_verified",
    "source_crosscheck",
    "notes",
    "universe_version",
)
_TRUE = {"TRUE", "T", "YES", "Y", "1"}


@dataclass(frozen=True)
class UniverseFile:
    path: Path
    asset_class: str  # "STOCK" or "ETF", as in the original combine step


def read_rows(spec: UniverseFile, version: str) -> list[dict[str, object]]:
    with spec.path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None or "ticker" not in reader.fieldnames:
            raise DataValidationError(str(spec.path), ["missing required column 'ticker'"])
        rows = []
        for raw in reader:
            ticker = (raw.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            row: dict[str, object] = {k: (raw.get(k) or "").strip() for k in OPTIONAL}
            default_type = "ETF" if spec.asset_class == "ETF" else "COMMON_STOCK"
            row.update(
                instrument_id=instrument_id(AssetClass.EQUITY, ticker),
                symbol=ticker,
                asset_class=spec.asset_class,
                security_type=(str(row["security_type"]) or default_type).upper(),
                status=(str(row["status"]) or "ACTIVE").upper(),
                optionable=(str(row["optionable"]) or "TRUE").upper() in _TRUE,
                universe_version=str(row["universe_version"]) or version,
            )
            rows.append(row)
    return rows


def import_universe(
    writer: StoreWriter, files: list[UniverseFile], version: str, snapshot: date, now: datetime
) -> RunRecord:
    rows = [r for spec in files for r in read_rows(spec, version)]
    frame = pd.DataFrame(rows)
    before = len(frame)
    frame = frame.drop_duplicates(subset="instrument_id", keep="first").reset_index(drop=True)
    run_id = new_run_id(JOB, snapshot, now)
    writer.write_table(
        "universe", snapshot, run_id, stamp(frame, snapshot, now, "universe_csv", run_id)
    )
    stats = {
        "files": [str(f.path) for f in files],
        "rows_loaded": before,
        "unique_tickers": len(frame),
        "duplicates_removed": before - len(frame),
        "by_security_type": frame["security_type"].value_counts().to_dict(),
        "inactive_or_unoptionable": int(
            (~frame["optionable"] | (frame["status"] != "ACTIVE")).sum()
        ),
    }
    record = RunRecord(run_id, JOB, snapshot, now, RunStatus.COMPLETE, now, stats=stats)
    writer.save_run(record)
    return record
