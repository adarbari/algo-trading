"""``UsageRecorder``: rows queued by the chain, written on a thread to usage/llm_calls, one atomic
run per batch, stamped with the exchange date of the call; it never blocks or raises into the
request path."""

import logging
import threading
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd
import pytest

from algotrade.data import StoreReader
from algotrade.data.usage import read_llm_calls
from algotrade.services.text_model.usage import UsageRecorder, open_recorder, store_seed
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.usage_writer import UsageWriter

LATE = datetime(2026, 10, 3, 1, tzinfo=UTC)  # Fri 9pm in New York
NEXT = datetime(2026, 10, 3, 15, tzinfo=UTC)


def call(at: datetime, provider: str = "gemini", **over: Any) -> dict[str, Any]:
    row = {"ts": at, "provider": provider, "model": "m", "use_case": "screener-draft",
           "user": "abhi", "input_tokens": 10, "output_tokens": 5, "latency_s": 0.4,
           "cost_usd": 0.0, "cost_basis": "free", "outcome": "ok",
           "fell_back_from": None}  # fmt: skip
    return row | over


def test_rows_are_written_stamped_with_the_exchange_date_and_committed() -> None:
    backend = MemoryBackend()
    recorder = UsageRecorder(UsageWriter(backend), clock=lambda: NEXT)
    assert recorder.submit(call(LATE))
    assert recorder.submit(call(NEXT, "claude", input_tokens=None, output_tokens=None,
                                cost_usd=None, cost_basis="unknown", outcome="failed"))  # fmt: skip
    recorder.flush()
    frame = read_llm_calls(StoreReader(backend), date(2026, 10, 2), date(2026, 10, 3))
    assert frame is not None and len(frame) == 2
    by = frame.set_index("provider")
    assert by.loc["gemini", "session_date"] == date(2026, 10, 2)  # 21:00 in New York, a Friday
    assert by.loc["claude", "session_date"] == date(2026, 10, 3)  # Saturday: no weekend gap
    assert set(frame["source"]) == {"text_model"}
    assert (frame["knowledge_ts"] == frame["ts"]).all()
    assert frame["run_id"].str.startswith("llm_usage-").all()
    assert by.loc["claude", ["input_tokens", "cost_usd"]].isna().all()  # unknown, not 0
    recorder.close()


def test_the_metering_columns_round_trip_and_absent_ones_are_null_never_zero() -> None:
    backend = MemoryBackend()
    recorder = UsageRecorder(UsageWriter(backend), clock=lambda: NEXT)
    recorder.submit(call(LATE, "claude", cache_read_tokens=98_000, cache_write_tokens=None,
                         call_id="abc", prompt_version="1", call_stage="repair"))  # fmt: skip
    recorder.submit(call(NEXT, "gemini"))  # a row with none of them
    recorder.flush()
    frame = read_llm_calls(StoreReader(backend), date(2026, 10, 2), date(2026, 10, 3))
    assert frame is not None
    by = frame.set_index("provider")
    assert by.loc["claude", "cache_read_tokens"] == 98_000
    assert pd.isna(by.loc["claude", "cache_write_tokens"])
    assert (by.loc["claude", "call_id"], by.loc["claude", "call_stage"]) == ("abc", "repair")
    assert by.loc["claude", "prompt_version"] == "1"
    assert by.loc["gemini", ["cache_read_tokens", "cache_write_tokens", "call_id"]].isna().all()
    recorder.close()


def test_a_full_queue_drops_and_a_failed_write_is_logged_never_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    started, release = threading.Event(), threading.Event()

    class Stuck(UsageWriter):
        def write_usage(self, *args: object) -> None:
            started.set()
            release.wait(5)
            raise OSError("disk full")

    recorder = UsageRecorder(Stuck(MemoryBackend()), maxsize=1)
    with caplog.at_level(logging.WARNING):
        assert recorder.submit(call(NEXT))  # taken by the thread, which is stuck
        assert started.wait(5)
        assert recorder.submit(call(NEXT, "b"))  # waits in the queue
        assert not recorder.submit(call(NEXT, "c"))  # full: dropped, no exception
        assert "queue full" in caplog.text
        release.set()
        recorder.flush()
        assert "not recorded" in caplog.text
    recorder.close()
    assert recorder.written == 0


def test_a_batch_is_one_run_and_the_next_gets_its_own_id() -> None:
    backend = MemoryBackend()
    recorder = UsageRecorder(UsageWriter(backend), clock=lambda: NEXT)
    recorder.submit(call(NEXT))
    recorder.flush()
    recorder.submit(call(NEXT, "claude"))
    recorder.flush()
    frame = read_llm_calls(StoreReader(backend), date(2026, 10, 3), date(2026, 10, 3))
    assert frame is not None and frame["run_id"].nunique() == 2 and recorder.written == 2
    recorder.close()


def test_the_store_seed_reads_the_spend_back() -> None:
    recorder = open_recorder("memory://")
    recorder.close()
    assert store_seed("memory://")(date(2026, 10, 1), date(2026, 10, 3)) == {}


def test_failure_columns_are_stored_and_other_rows_hold_null() -> None:
    backend = MemoryBackend()
    recorder = UsageRecorder(UsageWriter(backend), clock=lambda: NEXT)
    recorder.submit(call(LATE))  # a row with none of the failure columns
    recorder.submit(call(NEXT, "claude", outcome="rejected", cost_usd=None, cost_basis="unknown",
                         error="not JSON", stage="answer", sentence="typed", answer="Sure!",
                         prompt_chars=1234))  # fmt: skip
    recorder.flush()
    frame = read_llm_calls(StoreReader(backend), date(2026, 10, 2), date(2026, 10, 3))
    assert frame is not None
    by = frame.set_index("provider")
    assert by.loc["claude", ["error", "stage", "sentence", "answer"]].tolist() == [
        "not JSON", "answer", "typed", "Sure!"]  # fmt: skip
    assert by.loc["claude", "prompt_chars"] == 1234
    assert by.loc["gemini", ["error", "stage", "sentence", "answer", "prompt_chars"]].isna().all()
    recorder.close()


def test_an_ok_row_and_its_rejected_row_with_the_same_time_are_both_stored() -> None:
    backend = MemoryBackend()
    recorder = UsageRecorder(UsageWriter(backend), clock=lambda: NEXT)
    rejected = call(NEXT, outcome="rejected", cost_usd=None, cost_basis="unknown", stage="answer")
    recorder.submit(call(NEXT))
    recorder.submit(rejected)
    recorder.submit(call(NEXT, user="bea"))  # another user, same instant
    recorder.flush()
    recorder.submit(rejected | {"error": "again"})  # a later batch: same key, the latest wins
    recorder.flush()
    frame = read_llm_calls(StoreReader(backend), date(2026, 10, 3), date(2026, 10, 3))
    assert frame is not None
    assert sorted(zip(frame["user"], frame["outcome"], strict=True)) == [
        ("abhi", "ok"), ("abhi", "rejected"), ("bea", "ok")]  # fmt: skip
    assert frame.set_index("outcome").loc["rejected", "error"] == "again"
    recorder.close()
