"""Import the monthly master universe CSVs: the universe (coverage) plus L1 reference facts.

Accepts the files produced by the existing monthly refresh process
(``optionable_us_stock_universe.csv``, ``optionable_us_etf_universe.csv``). Only ``ticker``
is required; missing optional columns get conservative defaults. Every row is kept;
strategies choose their subset with selections (``config/site/presets/selections``).
Tickers resolve through the reference as of the snapshot (ADR 0018): known instruments keep
their (FIGI) ids, new ones get symbol ids.
"""

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from algotrade.core.errors import DataValidationError
from algotrade.core.instruments import AssetClass
from algotrade.data.resolver import SymbolResolver
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework import IngestRun, TaskContext

TASK = "universe_import"
SOURCE = "universe_csv"
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
    "is_leveraged",
    "is_inverse",
    "leverage",
    "tracks",
)
_TRUE = {"TRUE", "T", "YES", "Y", "1"}


@dataclass(frozen=True)
class UniverseFile:
    path: Path
    asset_class: str  # "STOCK" or "ETF", as in the original combine step


def read_rows(
    spec: UniverseFile, version: str, resolver: SymbolResolver
) -> list[dict[str, object]]:
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
                instrument_id=resolver.id_for(ticker),
                symbol=ticker,
                asset_class=spec.asset_class,
                security_type=(str(row["security_type"]) or default_type).upper(),
                status=(str(row["status"]) or "ACTIVE").upper(),
                optionable=(str(row["optionable"]) or "TRUE").upper() in _TRUE,
                universe_version=str(row["universe_version"]) or version,
            )
            rows.append(row)
    return rows


def _flag(value: object, is_etf: bool) -> bool | None:
    """CSV flag -> bool. Blank means unknown for ETFs (could be leveraged) and False otherwise."""
    text = str(value or "").strip().upper()
    if text:
        return text in _TRUE
    return None if is_etf else False


def reference_frame(universe: pd.DataFrame) -> pd.DataFrame:
    """L1 ``instruments/reference`` rows for the imported equities, ADRs and ETFs."""
    is_etf = universe["security_type"].eq("ETF")
    flags = {
        col: [_flag(v, e) for v, e in zip(universe[col], is_etf, strict=True)]
        for col in ("is_leveraged", "is_inverse")
    }
    return pd.DataFrame(
        {
            "instrument_id": universe["instrument_id"],
            "symbol": universe["symbol"],
            "name": universe["company_name"],
            "asset_class": AssetClass.EQUITY.value,
            "security_type": universe["security_type"],
            "exchange": universe["exchange"],
            "currency": "USD",
            "multiplier": 1.0,
            "tick_size": 0.01,
            "is_etf": is_etf,
            **flags,
            "leverage": pd.to_numeric(universe["leverage"], errors="coerce"),
            "tracks": universe["tracks"].where(universe["tracks"] != "", None),
            "optionable": universe["optionable"],
            "status": universe["status"],
        }
    )


def import_universe(
    ctx: TaskContext, files: list[UniverseFile], version: str, snapshot: date
) -> RunRecord:
    with IngestRun(ctx, TASK, snapshot) as run:
        resolver = run.resolver()
        frame = pd.DataFrame([r for spec in files for r in read_rows(spec, version, resolver)])
        before = len(frame)
        frame = frame.drop_duplicates(subset="instrument_id", keep="first").reset_index(drop=True)
        run.write("universe", frame, SOURCE)
        run.write("instruments/reference", reference_frame(frame), SOURCE)
        run.stats.update(
            files=[str(f.path) for f in files],
            rows_loaded=before,
            unique_tickers=len(frame),
            duplicates_removed=before - len(frame),
            by_security_type=frame["security_type"].value_counts().to_dict(),
            inactive_or_unoptionable=int(
                (~frame["optionable"] | (frame["status"] != "ACTIVE")).sum()
            ),
        )
    return run.record
