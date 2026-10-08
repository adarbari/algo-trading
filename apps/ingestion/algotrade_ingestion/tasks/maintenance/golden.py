"""Load the committed golden CSVs into a store, through the normal writers.

Writes, for every golden dataset:
- ``instruments/reference``: one snapshot at the first session (multiplier-1 equities). Ids
  come from the normal id rule (ADR 0018); synthetic symbols have no FIGI, so they are
  symbol ids (``EQ:<SYMBOL>``) and the baseline does not depend on the scheme.
- ``universe``: the same instruments as one snapshot at the first session (what the edge harness's
  universe selection reads); ``optionable`` and ``security_type`` are synthetic facts
- ``bars/1d``: one partition per session date, ids resolved through that reference
- ``catalog/golden_datasets``: which instruments make up which dataset

Load into a dedicated fixture store (``make golden-store``), never the production store:
synthetic symbols such as ``AAA`` collide with real tickers.
"""

from datetime import date

import pandas as pd

from algotrade.core.model.instruments import AssetClass
from algotrade.data.resolver import SymbolResolver
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext
from algotrade_ingestion.tasks.reference.instrument_ids import assign_ids
from algotrade_sources.framework.base import FetchRequest, FixtureSource

TASK = "golden_load"
SOURCE = "synthetic"  # the fixture source's registry name (``sources/registry.FIXTURES``)
BARS = "bars/1d"
CATALOG = "catalog/golden_datasets"


def golden_reference(source: FixtureSource, session: date) -> pd.DataFrame:
    """``instruments/reference`` rows for every golden symbol (no FIGIs: symbol ids)."""
    symbols = sorted({s for ds in source.datasets().values() for s in ds.symbols})
    listed = pd.DataFrame({"symbol": symbols, "figi": None, "status": "ACTIVE"})
    reference = assign_ids(listed, None, session).reference
    return reference[["instrument_id", "symbol"]].assign(
        asset_class=AssetClass.EQUITY.value,
        security_type="COMMON_STOCK",
        optionable=True,
        multiplier=1.0,
        tick_size=0.01,
        currency="USD",
        status="ACTIVE",
    )


def golden_universe(reference: pd.DataFrame, session: date) -> pd.DataFrame:
    """The ``universe`` snapshot of the golden instruments (all active, optionable stocks)."""
    columns = ["instrument_id", "symbol", "asset_class", "security_type", "optionable", "status"]
    return reference[columns].assign(universe_version=session.isoformat())


def _collect(source: FixtureSource, resolver: SymbolResolver) -> tuple[pd.DataFrame, pd.DataFrame]:
    bars, catalog = [], []
    for ds in source.datasets().values():
        for symbol in ds.symbols:
            iid = resolver.id_for(symbol)
            request = FetchRequest(f"{ds.name}/{symbol}", iid)
            payload = source.fetch(request)
            normalized = source.normalize(request, payload) if payload is not None else None
            if normalized is None:
                raise ValueError(f"golden file missing or empty: {request.key}")
            bars.append(normalized.tables[BARS])
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


def load_golden(ctx: TaskContext, source: FixtureSource) -> RunRecord:
    problems = source.verify()
    if problems:
        raise ValueError(f"golden files failed verification: {problems}")
    reference = golden_reference(source, date.min)
    bars, catalog = _collect(source, SymbolResolver.from_reference(reference))
    bars["session_date"] = bars["ts"].dt.date
    first: date = min(bars["session_date"])
    with IngestRun(ctx, TASK, first) as run:
        bars = bars.sort_values(["session_date", "instrument_id"], kind="stable")
        for key, day in bars.groupby("session_date", sort=True):
            session = key if isinstance(key, date) else date.fromisoformat(str(key))
            frame = day.drop(columns="session_date").reset_index(drop=True)
            run.write(BARS, frame, SOURCE, session=session)
        run.write("instruments/reference", reference, SOURCE)
        run.write("universe", golden_universe(reference, first), SOURCE)
        run.write(CATALOG, catalog, SOURCE)
        run.stats.update(
            datasets=int(catalog["dataset"].nunique()),
            instruments=len(reference),
            sessions=int(bars["session_date"].nunique()),
            bars=len(bars),
        )
    return run.record
