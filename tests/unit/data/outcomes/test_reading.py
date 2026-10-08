"""``read_outcomes``: the rows of one horizon and benchmark for the asked start sessions only;
runs merge per (instrument, horizon, benchmark), a later run's row winning; ``as_of`` drops rows
written after it, row by row; nothing stored is a MissingDataError."""

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from algotrade.core.model.errors import MissingDataError
from algotrade.data.outcomes import OUTCOME_FIELDS, read_outcomes
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.schemas import FORWARD_RETURNS
from algotrade.storage.tables.writers import StoreWriter

S1, S2, S3 = date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3)


def _row(iid: str, h: int, ret: float, benchmark: str = "SPY") -> dict[str, object]:
    return {
        "instrument_id": iid, "ts": pd.Timestamp("2026-09-01T20:00Z"), "horizon_sessions": h,
        "window_end": date(2026, 10, 1), "benchmark": benchmark, "fwd_return": ret,
        "fwd_excess_return": ret / 2, "fwd_max_return": max(ret, 0.0), "fwd_max_drawdown": 0.0,
        "fwd_realised_vol": 0.2, "outcome_status": "COMPLETE",
    }  # fmt: skip


def _write(writer: StoreWriter, day: date, run: str, known: datetime, rows: list[dict]) -> None:
    frame = pd.DataFrame(rows).assign(
        session_date=day, knowledge_ts=pd.Timestamp(known), source="outcomes", run_id=run
    )
    writer.write_table(FORWARD_RETURNS, day, run, frame)


def _store() -> StoreReader:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    early, late = datetime(2026, 10, 1, 22, tzinfo=UTC), datetime(2026, 10, 5, 22, tzinfo=UTC)
    first = [_row("EQ:A", 20, 0.1), _row("EQ:B", 20, -0.1), _row("EQ:A", 6, 0.3)]
    _write(writer, S1, "r1", early, [*first, _row("EQ:A", 20, 0.4, "QQQ")])
    _write(writer, S1, "r2", late, [_row("EQ:B", 20, -0.2)])  # a re-run: its row wins
    _write(writer, S2, "r3", early, [_row("EQ:A", 20, 0.5)])
    _write(writer, S3, "r4", early, [_row("EQ:A", 20, 0.9)])
    return StoreReader(backend)


def test_one_horizon_and_benchmark_for_the_asked_sessions() -> None:
    out = read_outcomes(_store(), 20, [S1, S3])
    assert list(zip(out["session_date"], out["instrument_id"], out["fwd_return"], strict=True)) == [
        (S1, "EQ:A", 0.1), (S1, "EQ:B", -0.2), (S3, "EQ:A", 0.9),
    ]  # fmt: skip
    assert set(OUTCOME_FIELDS) <= set(out.columns)


def test_another_horizon_or_benchmark() -> None:
    reader = _store()
    assert list(read_outcomes(reader, 6, [S1])["fwd_return"]) == [0.3]
    assert list(read_outcomes(reader, 20, [S1], benchmark="QQQ")["fwd_return"]) == [0.4]


def test_as_of_drops_rows_written_after_it() -> None:
    out = read_outcomes(_store(), 20, [S1], as_of=datetime(2026, 10, 2, tzinfo=UTC))
    assert list(zip(out["instrument_id"], out["fwd_return"], strict=True)) == [
        ("EQ:A", 0.1), ("EQ:B", -0.1),
    ]  # fmt: skip


def test_nothing_stored_is_missing_data_and_no_sessions_is_empty() -> None:
    reader = StoreReader(MemoryBackend())
    with pytest.raises(MissingDataError):
        read_outcomes(reader, 20, [S1])
    assert read_outcomes(reader, 20, []).empty
