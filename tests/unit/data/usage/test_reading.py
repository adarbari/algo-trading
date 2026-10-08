"""``spent_by_day`` / ``read_llm_calls``: a date-range read of the usage log; only the costs that
count against a budget (``price`` / ``reported``, known) are summed, per exchange date; an empty
store is no spend."""

from datetime import UTC, date, datetime

import pandas as pd

from algotrade.data.usage import LLM_CALLS, read_llm_calls, spent_by_day
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped

D1, D2, D3 = date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3)


def row(day: date, second: int, cost: float | None, basis: str, provider: str = "claude") -> dict:
    return {"ts": pd.Timestamp(day, tz="UTC") + pd.Timedelta(seconds=second), "provider": provider,
            "model": "m", "use_case": "screener-draft", "user": "abhi", "input_tokens": 10,
            "output_tokens": 5, "latency_s": 1.0, "cost_usd": cost, "cost_basis": basis,
            "outcome": "ok", "fell_back_from": None}  # fmt: skip


def store() -> StoreReader:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    rows1 = [row(D1, 0, 0.25, "price"), row(D1, 1, 0.5, "reported", "cli"),
             row(D1, 2, 0.0, "free", "gemini"), row(D1, 3, None, "unknown")]  # fmt: skip
    writer.write_table(LLM_CALLS, D1, "r1", stamped(rows1, D1, "r1"))
    writer.write_table(LLM_CALLS, D1, "r2", stamped([row(D1, 9, 0.25, "price")], D1, "r2"))
    writer.write_table(LLM_CALLS, D3, "r3", stamped([row(D3, 0, 1.0, "price")], D3, "r3"))
    return StoreReader(backend)


def test_spend_is_summed_per_day_over_paid_and_reported_known_costs_only() -> None:
    assert spent_by_day(store(), D1, D3) == {D1: 1.0, D3: 1.0}  # free, unknown and gaps add nothing
    assert spent_by_day(store(), D2, D2) == {}
    assert spent_by_day(store(), D1, D1) == {D1: 1.0}  # both runs of the day


def test_nothing_recorded_is_no_spend_and_no_frame() -> None:
    empty = StoreReader(MemoryBackend())
    assert spent_by_day(empty, D1, D3) == {} and read_llm_calls(empty, D1, D3) is None


def test_the_range_read_returns_every_attempt_known_by_as_of() -> None:
    frame = read_llm_calls(store(), D1, D3)
    assert frame is not None and len(frame) == 6
    early = datetime(2026, 9, 1, tzinfo=UTC)  # before any was known (knowledge_ts is T0)
    assert read_llm_calls(store(), D1, D3, as_of=early) is None
