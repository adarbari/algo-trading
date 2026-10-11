"""``read_drafting_events``: the events of a date range, ``None`` when nothing was recorded."""

from datetime import UTC, date, datetime

from algotrade.data import StoreReader
from algotrade.data.feedback import read_drafting_events
from algotrade.services.feedback.events import row_of
from algotrade.services.feedback.recorder import FeedbackRecorder
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.feedback_writer import FeedbackWriter

NOON = datetime(2026, 10, 2, 16, tzinfo=UTC)


def test_a_range_without_a_partition_has_nothing() -> None:
    reader = StoreReader(MemoryBackend())
    assert read_drafting_events(reader, date(2026, 10, 1), date(2026, 10, 2)) is None


def test_the_range_is_inclusive_and_rows_come_unfiltered() -> None:
    backend = MemoryBackend()
    recorder = FeedbackRecorder(FeedbackWriter(backend), clock=lambda: NOON)
    for user in ("abhi", "alice"):
        recorder.submit(row_of("draft_requested", "s", user, "screen", "m", at=NOON))
    recorder.flush()
    frame = read_drafting_events(StoreReader(backend), date(2026, 10, 2), date(2026, 10, 2))
    assert frame is not None and sorted(frame["user"]) == ["abhi", "alice"]
    recorder.close()
