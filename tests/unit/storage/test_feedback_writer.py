"""``FeedbackWriter``: only ``feedback/*`` tables, every write pending until its run commits
(ADR 0022, ADR 0066); the table's schema keeps the optional columns null and refuses an
undeclared one (no prompt, no answer: only what the schema names)."""

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from algotrade.core.model.errors import ConfigurationError, DataValidationError
from algotrade.data import StoreReader
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.feedback_writer import FeedbackWriter
from tests.helpers.stored_frames import stamped

DAY = date(2026, 10, 2)
AT = datetime(2026, 10, 2, 15, tzinfo=UTC)
TABLE = "feedback/drafting_events"
ROW = {"event_id": "e1", "draft_session_id": "s1", "ts": pd.Timestamp(AT), "user": "abhi",
       "doc_kind": "screen", "doc_id": "mine", "event": "draft_requested"}  # fmt: skip


def test_writes_publish_when_the_run_commits_and_vanish_when_it_fails() -> None:
    backend = MemoryBackend()
    writer, reader = FeedbackWriter(backend), StoreReader(backend)
    with writer.publishing("r1", AT):
        writer.write_feedback(TABLE, DAY, "r1", stamped([ROW], DAY, "r1"))
        assert reader.table(TABLE, DAY) is None  # pending
    frame = reader.table(TABLE, DAY)
    assert frame is not None and list(frame["event"]) == ["draft_requested"]
    with pytest.raises(RuntimeError), writer.publishing("r2", AT):
        writer.write_feedback(TABLE, DAY, "r2", stamped([{**ROW, "event_id": "e2"}], DAY, "r2"))
        raise RuntimeError("boom")
    after = reader.table(TABLE, DAY)
    assert after is not None and len(after) == 1


def test_refuses_tables_outside_feedback() -> None:
    writer = FeedbackWriter(MemoryBackend())
    for table in ("usage/llm_calls", "live/option_quotes", "results/x"):
        with pytest.raises(ConfigurationError, match="only writes feedback/"):
            writer.write_feedback(table, DAY, "r", pd.DataFrame())


def test_an_undeclared_column_is_refused() -> None:
    writer = FeedbackWriter(MemoryBackend())
    with pytest.raises(DataValidationError, match="undeclared columns"):
        writer.write_feedback(TABLE, DAY, "r", stamped([{**ROW, "answer": "secret"}], DAY, "r"))


def test_an_older_partition_without_the_optional_columns_still_reads() -> None:
    backend = MemoryBackend()
    writer, reader = FeedbackWriter(backend), StoreReader(backend)
    with writer.publishing("r1", AT):  # a partition written before payload / hashes existed
        writer.write_feedback(TABLE, DAY, "r1", stamped([ROW], DAY, "r1"))
    frame = reader.table_range(TABLE, DAY, DAY)
    assert frame is not None and list(frame["event"]) == ["draft_requested"]
    assert "payload" not in frame.columns or frame["payload"].isna().all()  # null, not an error
