"""``UsageWriter``: only ``usage/*`` tables, every write pending until its run commits (ADR 0022,
ADR 0057); the table's schema keeps unknown tokens and cost null."""

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from algotrade.core.model.errors import ConfigurationError, DataValidationError
from algotrade.data import StoreReader
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.usage_writer import UsageWriter
from tests.helpers.stored_frames import stamped

DAY = date(2026, 10, 2)
AT = datetime(2026, 10, 2, 15, tzinfo=UTC)
TABLE = "usage/llm_calls"
ROW = {"ts": pd.Timestamp(AT), "provider": "gemini", "model": "gemini-2.5-flash",
       "use_case": "screener-draft", "user": None, "input_tokens": None, "output_tokens": None,
       "latency_s": 1.5, "cost_usd": None, "cost_basis": "unknown", "outcome": "failed",
       "fell_back_from": None}  # fmt: skip


def test_writes_publish_when_the_run_commits_and_vanish_when_it_fails() -> None:
    backend = MemoryBackend()
    writer, reader = UsageWriter(backend), StoreReader(backend)
    with writer.publishing("r1", AT):
        writer.write_usage(TABLE, DAY, "r1", stamped([ROW], DAY, "r1"))
        assert reader.table(TABLE, DAY) is None  # pending
    frame = reader.table(TABLE, DAY)
    assert frame is not None and list(frame["provider"]) == ["gemini"]
    # unknown is null, never 0
    assert frame["input_tokens"].isna().all() and frame["cost_usd"].isna().all()
    with pytest.raises(RuntimeError), writer.publishing("r2", AT):
        later = {**ROW, "ts": pd.Timestamp(AT) + pd.Timedelta(minutes=1)}
        writer.write_usage(TABLE, DAY, "r2", stamped([later], DAY, "r2"))
        raise RuntimeError("boom")
    after = reader.table(TABLE, DAY)
    assert after is not None and len(after) == 1


def test_refuses_tables_outside_usage() -> None:
    writer = UsageWriter(MemoryBackend())
    for table in ("live/option_quotes", "chains/option_quotes", "results/x"):
        with pytest.raises(ConfigurationError, match="only writes usage/"):
            writer.write_usage(table, DAY, "r", pd.DataFrame())


def test_an_undeclared_column_is_refused() -> None:
    writer = UsageWriter(MemoryBackend())
    with pytest.raises(DataValidationError, match="undeclared columns"):
        writer.write_usage(TABLE, DAY, "r", stamped([{**ROW, "prompt": "secret text"}], DAY, "r"))
