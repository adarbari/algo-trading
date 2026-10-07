"""A small store for the event read objects, read as of ``D1`` (2026-10-01, the latest session
with bars): a stock (AAA, optionable), a leveraged fund tracking it (AAAU) and a plain ETF
(ETFX) in the reference snapshot of D0; ``earnings@v1`` and ``fund_reference@v1`` partitions
for D0 (older, never shown for D1) and D1; the macro calendar with a release known before D1,
one learned after it, one released and one moved; AAA's 8-Ks (one accepted after D1); an
option chain of AAA for D1 only. ``store_with(*writes)`` adds more."""

from collections.abc import Callable
from datetime import UTC, date, datetime, time

import pandas as pd

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext, open_context
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.rollup_store import chain_rows, write_chains, write_rows
from tests.helpers.stored_frames import stamped

D0, D1 = date(2026, 9, 30), date(2026, 10, 1)
EARNINGS = "rollups/instrument/earnings@v1"
FUND_REFERENCE = "rollups/instrument/fund_reference@v1"
MACRO, FILING = "events/macro_release", "events/filing"
REPORT = date(2026, 10, 23)  # AAA reports after the close on an expiry Friday
EXPIRIES = (date(2026, 10, 6), date(2026, 10, 9), date(2026, 10, 16), REPORT, date(2027, 2, 19))


def _reference(writer: StoreWriter) -> None:
    base = {"asset_class": "EQ", "multiplier": 1.0, "status": "ACTIVE", "exchange": "NYSE"}
    kinds = {  # symbol -> (security type, optionable, leveraged)
        "AAA": ("COMMON_STOCK", True, False), "AAAU": ("ETF", True, True),
        "ETFX": ("ETF", False, False),
    }  # fmt: skip
    rows = [
        {"instrument_id": f"EQ:{s}", "symbol": s, "name": f"{s} Inc", "security_type": t,
         "is_etf": t == "ETF", "optionable": o, "is_leveraged": lev, "is_inverse": False, **base}
        for s, (t, o, lev) in kinds.items()
    ]  # fmt: skip
    write_rows(writer, "instruments/reference", D0, rows)
    company = {"instrument_id": "EQ:AAA", "symbol": "AAA", "cik": "1", "name": "AAA Holdings",
               "sic": "3571", "sector": "Technology", "fetched_on": D0}  # fmt: skip
    write_rows(writer, "instruments/company", D0, [company])


def _rollups(writer: StoreWriter) -> None:
    for day in (D0, D1):
        bar = {"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}
        row = {"instrument_id": "EQ:AAA", "ts": pd.Timestamp(day, tz="UTC"), **bar}
        write_rows(writer, "bars/1d", day, [row])
    old = {"instrument_id": "EQ:AAA", "next_earnings_date": date(2026, 10, 2),
           "earnings_time": "pre", "date_confirmed": False}  # fmt: skip
    write_rows(writer, EARNINGS, D0, [old])
    now = {"instrument_id": "EQ:AAA", "next_earnings_date": REPORT, "earnings_time": "post",
           "date_confirmed": True}  # fmt: skip
    write_rows(writer, EARNINGS, D1, [now])
    link = {"instrument_id": "EQ:AAAU", "reference_instrument_id": "EQ:AAA",
            "reference_kind": "single_stock", "reference_source": "holdings",
            "reference_status": "LINKED"}  # fmt: skip
    write_rows(writer, FUND_REFERENCE, D1, [link])


def macro_row(key: str, day: date, status: str, known: date) -> dict[str, object]:
    return {"instrument_id": f"MACRO:{key}", "ts": pd.Timestamp(f"{day} 12:30", tz="UTC"),
            "known_from": known, "release_key": key, "release_name": f"{key} release",
            "release_date": day, "time_et": "08:30", "status": status}  # fmt: skip


def write_macro(writer: StoreWriter, stored: date, rows: list[dict[str, object]]) -> None:
    run, knowledge = f"macro-{stored}", datetime.combine(stored, time(23), UTC)
    writer.write_table(MACRO, stored, run, stamped(rows, stored, run, knowledge, source="fred"))


def _macro(writer: StoreWriter) -> None:
    write_macro(writer, D0, [
        macro_row("CPI", date(2026, 10, 14), "scheduled", D0),
        macro_row("PPI", date(2026, 10, 1), "scheduled", D0),
        macro_row("GDP", date(2026, 10, 7), "scheduled", D0),
    ])  # fmt: skip
    write_macro(writer, D1, [
        macro_row("PPI", date(2026, 10, 1), "released", D1),  # out on the session: behind us
        macro_row("GDP", date(2026, 10, 7), "moved", D1),  # no longer on the 7th
        macro_row("GDP", date(2026, 10, 29), "scheduled", D1),
    ])  # fmt: skip
    later = date(2026, 10, 5)  # a date published after the session: invisible to it
    write_macro(writer, later, [macro_row("FOMC", date(2026, 10, 28), "scheduled", later)])


def filing_row(accepted: str, items: str, known: date) -> dict[str, object]:
    ts = pd.Timestamp(accepted, tz="UTC")
    return {"instrument_id": "EQ:AAA", "ts": ts, "known_from": known, "cik": "1", "form": "8-K",
            "accession": f"0001-{accepted[:10]}", "filing_date": known, "items": items,
            "report_date": None, "primary_document": "x.htm"}  # fmt: skip


def _filings(writer: StoreWriter) -> None:
    rows = [
        filing_row("2024-02-01 21:05", "2.02,9.01", date(2024, 2, 1)),  # before the window
        filing_row("2026-07-30 20:10", "2.02,9.01", date(2026, 7, 30)),
        filing_row("2026-09-15 13:00", "5.02", date(2026, 9, 15)),
        filing_row("2026-10-02 20:00", "1.01,9.01", date(2026, 10, 2)),  # after the session
    ]
    run = "filings"
    writer.write_table(FILING, D1, run, stamped(rows, D1, run, source="sec"))


def _chain(writer: StoreWriter) -> None:
    rows = chain_rows("EQ:AAA", D1, 100.0, dict.fromkeys(EXPIRIES, 0.25), 0.03, strikes=(100,))
    write_chains(writer, D1, rows, {"EQ:AAA": 100.0})


def store_with(*writes: Callable[[StoreWriter], None]) -> StoreReader:
    """This store plus what each of ``writes`` writes."""
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    for write in (_reference, _rollups, _macro, _filings, _chain, *writes):
        write(writer)
    return StoreReader(backend)


def context(reader: StoreReader, day: date | None = None) -> ReadContext:
    """The read context of ``reader`` for ``day`` (None: the latest session, D1)."""
    return open_context(reader, MemoryConfigStore({}), UserContext("local"), day)
