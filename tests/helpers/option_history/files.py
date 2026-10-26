"""Synthetic HistoricalOptionData zips in a folder, and a main store with the listings they
resolve through (ADR 0086). The vendor's own sample rows are never committed (public repo): the
CSVs under ``tests/fixtures/sources/historicaloptiondata`` are invented, in the vendor's layout."""

import zipfile
from datetime import date
from pathlib import Path

import pandas as pd

from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from tests.conftest import REPO_ROOT

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "sources" / "historicaloptiondata"
DAY_ONE, DAY_TWO = date(2019, 8, 15), date(2019, 8, 16)  # a Thursday and a Friday


def make_zip(path: Path, members: dict[str, str | bytes]) -> Path:
    """A zip of ``members`` (name -> fixture file name, or the bytes themselves)."""
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in members.items():
            data = content if isinstance(content, bytes) else (FIXTURES / content).read_bytes()
            archive.writestr(name, data)
    return path


def session_members(day: str, monthly: bool = False) -> dict[str, str]:
    prefix = "L2_" if monthly else ""
    return {
        f"{prefix}{kind}_{day}.csv": f"{kind}_{day}.csv"
        for kind in ("options", "stockquotes", "optionstats")
    }


def folder(root: Path) -> Path:
    """Day one as a daily zip, day two inside a monthly zip, plus the stock history zip."""
    make_zip(root / "Sample_L2_20190815.zip", session_members("20190815"))
    make_zip(root / "L2_2019_August.zip", session_members("20190816", monthly=True))
    make_zip(
        root / "stockhistory.zip",
        {"dividends.csv": "dividends.csv", "stocksplits.csv": "stocksplits.csv"},
    )
    return root


def main_store() -> StoreWriter:
    """The main store: listings of AAPL and SPY, and A (delisted after day one)."""
    writer = StoreWriter(MemoryBackend())
    day = date(2026, 10, 2)
    now = pd.Timestamp(day, tz="UTC")
    listings = pd.DataFrame(
        [
            ("EQ:AAPL", "AAPL", date(1990, 1, 2), None),
            ("EQ:SPY", "SPY", date(1993, 1, 29), None),
            ("EQ:A", "A", date(1999, 11, 18), DAY_ONE),
        ],
        columns=["instrument_id", "ticker", "start_date", "end_date"],
    ).assign(exchange="NYSE", asset_type="Stock", price_currency="USD", perma_ticker="", ts=now,
             knowledge_ts=now, session_date=day, source="tiingo", run_id="r")  # fmt: skip
    writer.write_table("instruments/listing_history", day, "r", listings)
    return writer
