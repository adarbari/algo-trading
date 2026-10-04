"""``LiveRecorder``: snapshots queued by the API, written on a thread to live/option_quotes,
one atomic run per batch, stamped with the session the quote was taken in."""

import logging
import threading
from datetime import UTC, date, datetime

import pandas as pd
import pytest

from algotrade.data import StoreReader
from algotrade.data.chains import live_option_quotes
from algotrade.services.live.recorder import LiveRecorder, open_recorder, quote_session
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.live_writer import LiveWriter

FRIDAY = datetime(2026, 10, 2, 15, tzinfo=UTC)
SATURDAY = datetime(2026, 10, 3, 15, tzinfo=UTC)


def snapshot(at: datetime, strike: float = 100.0) -> pd.DataFrame:
    return pd.DataFrame(
        [{"instrument_id": f"OPT:A:{strike}", "underlying_id": "EQ:A", "symbol": "A",
          "ts": pd.Timestamp(at), "expiry": date(2026, 11, 20), "right": "C", "strike": strike,
          "bid": 1.0, "ask": 1.1, "last": None, "close": 1.0, "volume": 3.0, "iv": 0.3,
          "delta": 0.5, "conid": 7, "market_data_type": 3}]
    )  # fmt: skip


def test_quote_session_is_the_exchange_session_or_the_last_one() -> None:
    assert quote_session(FRIDAY) == date(2026, 10, 2)
    assert quote_session(SATURDAY) == date(2026, 10, 2)
    assert quote_session(datetime(2026, 10, 3, 1, tzinfo=UTC)) == date(2026, 10, 2)  # Fri 9pm NY


def test_submitted_snapshots_are_written_stamped_and_committed() -> None:
    backend = MemoryBackend()
    recorder = LiveRecorder(LiveWriter(backend), clock=lambda: FRIDAY)
    # one submit (one batch, one run): two submits may be drained as one batch or two
    assert recorder.submit(pd.concat([snapshot(FRIDAY), snapshot(SATURDAY, 105.0)]))
    assert not recorder.submit(snapshot(FRIDAY).iloc[0:0])  # nothing to record
    recorder.flush()
    frame = live_option_quotes(StoreReader(backend), date(2026, 10, 2))
    assert frame is not None and sorted(frame["strike"]) == [100.0, 105.0]
    assert set(frame["source"]) == {"ibkr"} and set(frame["session_date"]) == {date(2026, 10, 2)}
    assert (frame["knowledge_ts"] == frame["ts"]).all()
    assert frame["run_id"].str.startswith("live_quotes-2026-10-02-").all()
    recorder.submit(snapshot(datetime(2026, 10, 2, 15, 1, tzinfo=UTC)))
    recorder.flush()  # a second run in the same second gets its own id
    again = live_option_quotes(StoreReader(backend), date(2026, 10, 2))
    assert again is not None and len(again) == 3 and again["run_id"].nunique() == 2
    assert recorder.written == 2
    recorder.close()


def test_a_full_queue_drops_and_a_failed_write_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    started, release = threading.Event(), threading.Event()

    class Stuck(LiveWriter):
        def write_live(self, *args: object) -> None:
            started.set()
            release.wait(5)
            raise OSError("disk full")

    recorder = LiveRecorder(Stuck(MemoryBackend()), maxsize=1)
    with caplog.at_level(logging.WARNING):
        assert recorder.submit(snapshot(FRIDAY))  # taken by the thread, which is stuck
        assert started.wait(5)
        assert recorder.submit(snapshot(FRIDAY, 105.0))  # waits in the queue
        assert not recorder.submit(snapshot(FRIDAY, 110.0))  # the queue is full: dropped
        assert "queue full" in caplog.text
        release.set()
        recorder.flush()
        assert "not recorded" in caplog.text
    recorder.close()
    assert recorder.written == 0


def test_open_recorder_writes_to_the_store_at_a_url() -> None:
    recorder = open_recorder("memory://")
    recorder.close()
