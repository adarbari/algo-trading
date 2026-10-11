"""``FeedbackRecorder``: events queued by the API, written on a thread to
``feedback/drafting_events``, one atomic run per batch, stamped with the exchange date of the
event; it never blocks or raises into the request path (ADR 0066)."""

import logging
import threading
from datetime import UTC, date, datetime
from typing import Any

import pytest

from algotrade.data import StoreReader
from algotrade.data.feedback import read_drafting_events
from algotrade.services.feedback.events import row_of
from algotrade.services.feedback.recorder import FeedbackRecorder, open_recorder
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.feedback_writer import FeedbackWriter

LATE = datetime(2026, 10, 3, 1, tzinfo=UTC)  # Fri 9pm in New York
NEXT = datetime(2026, 10, 3, 15, tzinfo=UTC)
RANGE = (date(2026, 10, 2), date(2026, 10, 3))


def event(at: datetime, name: str = "draft_requested", **over: Any) -> dict[str, Any]:
    return row_of(name, "sess", "abhi", "screen", "mine", at=at, sentence="cheap stocks") | over


def test_rows_are_written_stamped_with_the_exchange_date_and_committed() -> None:
    backend = MemoryBackend()
    recorder = FeedbackRecorder(FeedbackWriter(backend), clock=lambda: NEXT)
    assert recorder.submit(event(LATE))
    assert recorder.submit(event(NEXT, "draft_saved", payload='{"a":1}', saved_hash="h"))
    recorder.flush()
    frame = read_drafting_events(StoreReader(backend), *RANGE)
    assert frame is not None and len(frame) == 2
    by = frame.set_index("event")
    assert by.loc["draft_requested", "session_date"] == date(2026, 10, 2)  # 21:00 in New York
    assert by.loc["draft_saved", "session_date"] == date(2026, 10, 3)
    assert set(frame["source"]) == {"drafting_feedback"}
    assert (frame["knowledge_ts"] == frame["ts"]).all()
    assert frame["run_id"].str.startswith("drafting_feedback-").all()
    assert by.loc["draft_requested", ["draft_hash", "payload", "call_ids"]].isna().all()  # null
    assert by.loc["draft_saved", "payload"] == '{"a":1}'
    recorder.close()


def test_one_event_submitted_twice_is_one_row_but_two_events_of_a_session_are_two() -> None:
    backend = MemoryBackend()
    recorder = FeedbackRecorder(FeedbackWriter(backend), clock=lambda: NEXT)
    once = event(NEXT, "draft_returned")
    recorder.submit(once)
    recorder.submit(dict(once))  # the same event id and event: one row
    recorder.submit(event(NEXT, "draft_returned"))  # another event of the session
    recorder.submit(event(NEXT, "draft_saved"))
    recorder.flush()
    frame = read_drafting_events(StoreReader(backend), *RANGE)
    assert frame is not None and sorted(frame["event"]) == [
        "draft_returned", "draft_returned", "draft_saved",
    ]  # fmt: skip
    recorder.close()


def test_a_full_queue_drops_the_row_and_logs_never_raises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    gate = threading.Event()

    class Slow(FeedbackWriter):
        def publishing(self, run_id: str, at: datetime) -> Any:
            gate.wait(5)
            return super().publishing(run_id, at)

    recorder = FeedbackRecorder(Slow(MemoryBackend()), maxsize=1, clock=lambda: NEXT)
    with caplog.at_level(logging.WARNING):
        results = [recorder.submit(event(NEXT)) for _ in range(6)]
    assert False in results  # the queue filled while the thread was held
    assert "queue full" in caplog.text
    gate.set()
    recorder.close()


def test_a_failing_writer_is_logged_and_the_thread_lives_on(
    caplog: pytest.LogCaptureFixture,
) -> None:
    backend = MemoryBackend()

    class Flaky(FeedbackWriter):
        fail = True

        def write_feedback(self, *args: Any, **kwargs: Any) -> None:
            if Flaky.fail:
                raise RuntimeError("disk full")
            super().write_feedback(*args, **kwargs)

    recorder = FeedbackRecorder(Flaky(backend), clock=lambda: NEXT)
    with caplog.at_level(logging.ERROR):
        assert recorder.submit(event(NEXT))  # accepted: the request is never told
        recorder.flush()
    assert "not recorded" in caplog.text
    assert read_drafting_events(StoreReader(backend), *RANGE) is None  # dropped, not half-written
    Flaky.fail = False
    recorder.submit(event(NEXT, "draft_saved"))
    recorder.flush()
    frame = read_drafting_events(StoreReader(backend), *RANGE)
    assert frame is not None and list(frame["event"]) == ["draft_saved"]
    recorder.close()


def test_open_recorder_writes_to_the_store_at_the_url() -> None:
    recorder = open_recorder("memory://")
    assert recorder.submit(event(NEXT))
    recorder.close()
