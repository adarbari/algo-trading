"""``BatchRecorder``: items queued without blocking, drained in batches on one thread, a failed
batch logged and dropped, ids unique per run even within one second, flush and close."""

import logging
import threading
from datetime import UTC, date, datetime

import pytest

from algotrade.storage.recording import BatchRecorder

AT = datetime(2026, 10, 2, 15, tzinfo=UTC)
DAY = date(2026, 10, 2)


class Collect(BatchRecorder[int]):
    """Keeps every batch it is asked to write; ``gate`` holds the thread, ``fail`` breaks it."""

    def __init__(self, batch: int = 100, maxsize: int = 10) -> None:
        self.batches: list[list[int]] = []
        self.ids: list[str] = []
        self.gate: threading.Event | None = None
        self.started = threading.Event()
        self.fail = False
        super().__init__("demo", "numbers", batch, maxsize, clock=lambda: AT)

    def submit(self, item: int) -> bool:
        return self._put(item)

    def _write(self, items: list[int], now: datetime) -> None:
        self.started.set()
        if self.gate is not None:
            self.gate.wait(5)
        if self.fail:
            raise OSError("disk full")
        self.ids.append(self.run_id(DAY, now))
        self.batches.append(items)


def test_items_are_written_in_order_in_batches_and_counted() -> None:
    recorder = Collect(batch=2)
    recorder.gate = threading.Event()
    assert recorder.submit(1)
    assert recorder.started.wait(5)  # the thread holds item 1; the rest queue behind it
    for n in (2, 3, 4, 5):
        recorder.submit(n)
    recorder.gate.set()
    recorder.flush()
    assert recorder.batches == [[1], [2, 3], [4, 5]] and recorder.written == 3
    recorder.close()


def test_run_ids_are_unique_even_within_one_second() -> None:
    recorder = Collect()
    for n in range(3):
        recorder.submit(n)
        recorder.flush()
    assert len(set(recorder.ids)) == 3 and recorder.ids == sorted(recorder.ids)
    assert all(i.startswith("demo-2026-10-02-") for i in recorder.ids)
    recorder.close()


def test_a_full_queue_drops_and_a_failed_batch_is_logged_and_the_thread_lives_on(
    caplog: pytest.LogCaptureFixture,
) -> None:
    recorder = Collect(maxsize=1)
    recorder.gate, recorder.fail = threading.Event(), True
    with caplog.at_level(logging.WARNING):
        assert recorder.submit(1)  # taken by the thread, which waits on the gate
        assert recorder.started.wait(5)
        assert recorder.submit(2)  # waits in the queue
        assert not recorder.submit(3)  # full: dropped, no exception
        assert "queue full" in caplog.text
        recorder.gate.set()
        recorder.flush()
        assert "not recorded" in caplog.text
    assert recorder.written == 0
    recorder.fail = False
    recorder.submit(4)
    recorder.flush()
    assert recorder.batches == [[4]] and recorder.written == 1
    recorder.close()


def test_close_writes_what_is_queued_and_stops_the_thread() -> None:
    recorder = Collect()
    recorder.submit(1)
    recorder.close()
    assert recorder.batches == [[1]] and not recorder._thread.is_alive()
