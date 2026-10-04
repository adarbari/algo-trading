"""``LiveWriter``: only ``live/*`` tables, every write pending until its run commits (ADR 0022,
ADR 0028)."""

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.data import StoreReader
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.live_writer import LiveWriter
from tests.helpers.stored_frames import stamped

DAY = date(2026, 10, 2)
AT = datetime(2026, 10, 2, 15, tzinfo=UTC)
ROW = {"instrument_id": "OPT:A", "underlying_id": "EQ:A", "ts": pd.Timestamp(AT),
       "expiry": date(2026, 11, 20), "right": "C", "strike": 100.0, "bid": 1.0}  # fmt: skip


def test_writes_publish_when_the_run_commits_and_vanish_when_it_fails() -> None:
    backend = MemoryBackend()
    writer, reader = LiveWriter(backend), StoreReader(backend)
    with writer.publishing("r1", AT):
        writer.write_live("live/option_quotes", DAY, "r1", stamped([ROW], DAY, "r1"))
        assert reader.table("live/option_quotes", DAY) is None  # pending
    frame = reader.table("live/option_quotes", DAY)
    assert frame is not None and list(frame["instrument_id"]) == ["OPT:A"]
    with pytest.raises(RuntimeError), writer.publishing("r2", AT):
        later = {**ROW, "ts": pd.Timestamp(AT) + pd.Timedelta(minutes=1)}
        writer.write_live("live/option_quotes", DAY, "r2", stamped([later], DAY, "r2"))
        raise RuntimeError("boom")
    after = reader.table("live/option_quotes", DAY)
    assert after is not None and len(after) == 1


def test_refuses_tables_outside_live() -> None:
    writer = LiveWriter(MemoryBackend())
    with pytest.raises(ConfigurationError, match="only writes live/"):
        writer.write_live("chains/option_quotes", DAY, "r", pd.DataFrame())
