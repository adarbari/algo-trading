"""Chain reads filter by underlying (``algotrade.data.chains``)."""

from datetime import date

import pandas as pd
import pytest

from algotrade.core.model.errors import MissingDataError
from algotrade.data import StoreReader
from algotrade.data.chains import (
    chain_expiries,
    chain_status,
    live_option_quotes,
    option_quotes,
    underlying_quotes,
)
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.live_writer import LiveWriter
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped

DAY = date(2026, 10, 1)
TS = pd.Timestamp("2026-10-01T20:00", tz="UTC")


def option(contract: str, underlying: str) -> dict[str, object]:
    return {
        "instrument_id": contract,
        "underlying_id": underlying,
        "ts": TS,
        "expiry": date(2026, 11, 20),
        "right": "P",
        "strike": 100.0,
        "bid": 1.0,
        "ask": 1.1,
        "volume": 10.0,
        "open_interest": 100.0,
        "iv": 0.3,
        "delta": -0.3,
    }


def test_option_quotes_filter_on_the_underlying() -> None:
    backend = MemoryBackend()
    writer, reader = StoreWriter(backend), StoreReader(backend)
    assert option_quotes(reader, DAY, ["EQ:A"]) is None
    rows = [option("OPT:A1", "EQ:A"), option("OPT:A2", "EQ:A"), option("OPT:B1", "EQ:B")]
    writer.write_table("chains/option_quotes", DAY, "c", stamped(rows, DAY, "c"))
    only_a = option_quotes(reader, DAY, ["EQ:A"])
    assert only_a is not None and list(only_a["instrument_id"]) == ["OPT:A1", "OPT:A2"]
    every = option_quotes(reader, DAY)
    assert every is not None and len(every) == 3


def test_underlying_quotes_and_status() -> None:
    backend = MemoryBackend()
    writer, reader = StoreWriter(backend), StoreReader(backend)
    with pytest.raises(MissingDataError, match="algotrade-ingest chains"):
        chain_status(reader, DAY, hint="algotrade-ingest chains")
    assert chain_status(reader, DAY) is None
    status = [{"instrument_id": i, "status": "OK"} for i in ("EQ:A", "EQ:B")]
    writer.write_table("chains/status", DAY, "c", stamped(status, DAY, "c"))
    quote = {"symbol": "A", "ts": TS, "price": 1.0, "close": 1.0, "volume": 1.0, "iv30": 0.2}
    quotes = [{"instrument_id": i, **quote} for i in ("EQ:A", "EQ:B")]
    writer.write_table("chains/underlying_quotes", DAY, "c", stamped(quotes, DAY, "c"))
    got = chain_status(reader, DAY, ["EQ:B"])
    assert got is not None and list(got["instrument_id"]) == ["EQ:B"]
    under = underlying_quotes(reader, DAY, ["EQ:A"])
    assert under is not None and list(under["instrument_id"]) == ["EQ:A"]


def test_chain_expiries_one_pruned_read_per_underlying_in_the_session_only() -> None:
    backend = MemoryBackend()
    writer, reader = StoreWriter(backend), StoreReader(backend)
    assert chain_expiries(reader, DAY, ["EQ:A"]) == {}
    near, far = date(2026, 10, 9), date(2026, 11, 20)
    rows = [option("OPT:A1", "EQ:A"), option("OPT:A2", "EQ:A"), option("OPT:B1", "EQ:B")]
    rows[1]["expiry"] = near
    writer.write_table("chains/option_quotes", DAY, "c", stamped(rows, DAY, "c"))
    later = date(2026, 10, 2)
    writer.write_table(
        "chains/option_quotes", later, "d", stamped([option("OPT:C", "EQ:C")], later, "d")
    )
    assert chain_expiries(reader, DAY, ["EQ:A", "EQ:C"]) == {"EQ:A": [near, far]}


def test_live_option_quotes_keep_every_snapshot_and_filter_on_the_underlying() -> None:
    backend = MemoryBackend()
    writer, reader = LiveWriter(backend), StoreReader(backend)
    assert live_option_quotes(reader, DAY) is None
    for n, run in enumerate(("l1", "l2")):
        rows = [
            {**option(c, u), "ts": TS + pd.Timedelta(minutes=n), "close": None}
            for c, u in (("OPT:A1", "EQ:A"), ("OPT:B1", "EQ:B"))
        ]
        for row in rows:
            row.pop("open_interest")
        with writer.publishing(run, TS.to_pydatetime()):
            writer.write_live("live/option_quotes", DAY, run, stamped(rows, DAY, run))
    only_a = live_option_quotes(reader, DAY, ["EQ:A"])
    assert only_a is not None and list(only_a["instrument_id"]) == ["OPT:A1", "OPT:A1"]
    every = live_option_quotes(reader, DAY)
    assert every is not None and len(every) == 4
