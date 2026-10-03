"""Load the committed golden CSVs into a store, through the normal writers.

Writes, for every golden dataset:
- ``instruments/reference``: one snapshot at the first session (multiplier-1 equities). Ids
  come from the normal id rule (ADR 0018); synthetic symbols have no FIGI, so they are
  symbol ids (``EQ:<SYMBOL>``) and the baseline does not depend on the scheme.
- ``bars/1d``: one partition per session date, ids resolved through that reference
- ``catalog/golden_datasets``: which instruments make up which dataset

Load into a dedicated fixture store (``make golden-store``), never the production store:
synthetic symbols such as ``AAA`` collide with real tickers.
"""

from datetime import date
from pathlib import Path

import pandas as pd

from algotrade.core.instruments import AssetClass
from algotrade.data.resolver import SymbolResolver
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.sources.base import FetchRequest
from algotrade_ingestion.sources.synthetic.files import GoldenFiles
from algotrade_ingestion.sources.synthetic.source import BARS_TABLE, GoldenCsvSource
from algotrade_ingestion.tasks.framework import IngestRun, TaskContext
from algotrade_ingestion.tasks.instrument_ids import assign_ids

TASK = "golden_load"
SOURCE = GoldenCsvSource.name
CATALOG = "catalog/golden_datasets"


def golden_files(directory: Path) -> GoldenFiles:
    return GoldenFiles(directory)


def golden_reference(files: GoldenFiles, session: date) -> pd.DataFrame:
    """``instruments/reference`` rows for every golden symbol (no FIGIs: symbol ids)."""
    symbols = sorted({s for ds in files.manifest().values() for s in ds.symbols})
    listed = pd.DataFrame({"symbol": symbols, "figi": None, "status": "ACTIVE"})
    reference = assign_ids(listed, None, session).reference
    return reference[["instrument_id", "symbol"]].assign(
        asset_class=AssetClass.EQUITY.value,
        security_type="COMMON_STOCK",
        multiplier=1.0,
        tick_size=0.01,
        currency="USD",
        status="ACTIVE",
    )


def _collect(files: GoldenFiles, resolver: SymbolResolver) -> tuple[pd.DataFrame, pd.DataFrame]:
    source = GoldenCsvSource(files)
    bars, catalog = [], []
    for ds in files.manifest().values():
        for symbol in ds.symbols:
            iid = resolver.id_for(symbol)
            request = FetchRequest(f"{ds.name}/{symbol}", iid)
            payload = source.fetch(request)
            normalized = source.normalize(request, payload) if payload is not None else None
            if normalized is None:
                raise ValueError(f"golden file missing or empty: {request.key}")
            bars.append(normalized.tables[BARS_TABLE])
            catalog.append(
                {
                    "instrument_id": iid,
                    "symbol": symbol,
                    "dataset": ds.name,
                    "description": ds.description,
                    "tags": ",".join(ds.tags),
                }
            )
    return pd.concat(bars, ignore_index=True), pd.DataFrame(catalog)


def load_golden(ctx: TaskContext, files: GoldenFiles) -> RunRecord:
    problems = files.verify()
    if problems:
        raise ValueError(f"golden files failed verification: {problems}")
    reference = golden_reference(files, date.min)
    bars, catalog = _collect(files, SymbolResolver.from_reference(reference))
    bars["session_date"] = bars["ts"].dt.date
    first: date = min(bars["session_date"])
    with IngestRun(ctx, TASK, first) as run:
        bars = bars.sort_values(["session_date", "instrument_id"], kind="stable")
        for key, day in bars.groupby("session_date", sort=True):
            session = key if isinstance(key, date) else date.fromisoformat(str(key))
            frame = day.drop(columns="session_date").reset_index(drop=True)
            run.write("bars/1d", frame, SOURCE, session=session)
        run.write("instruments/reference", reference, SOURCE)
        run.write(CATALOG, catalog, SOURCE)
        run.stats.update(
            datasets=int(catalog["dataset"].nunique()),
            instruments=len(reference),
            sessions=int(bars["session_date"].nunique()),
            bars=len(bars),
        )
    return run.record
