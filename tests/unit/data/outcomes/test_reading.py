"""``read_outcomes``: the rows of one horizon and benchmark for the asked start sessions only;
runs merge per (instrument, horizon, benchmark), a later run's row winning; ``as_of`` drops rows
written after it, row by row; nothing stored is a MissingDataError."""

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from algotrade.core.model.errors import MissingDataError
from algotrade.data.outcomes import (
    OUTCOME_FIELDS,
    outcome_known,
    outcome_seqs,
    outcome_stamps,
    read_outcomes,
)
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


def test_with_as_of_only_the_wanted_partitions_are_read() -> None:
    reader = _store()
    read: list[date] = []
    real = reader.table

    def spy(table: str, day: date, *a: object, **k: object) -> pd.DataFrame | None:
        read.append(day)
        return real(table, day, *a, **k)  # type: ignore[arg-type]

    reader.table = spy  # type: ignore[method-assign]
    as_of = datetime(2026, 10, 6, tzinfo=UTC)
    out = read_outcomes(reader, 20, [S1, S3], as_of=as_of)
    assert read == [S1, S3]  # not S2, between them
    assert list(out["session_date"]) == [S1, S1, S3]
    assert read_outcomes(reader, 20, [S1, S3]).equals(out)  # the range read gives the same rows


def test_with_as_of_the_error_keeps_the_span_semantics() -> None:
    reader, as_of = _store(), datetime(2026, 10, 6, tzinfo=UTC)
    assert read_outcomes(reader, 20, [S1, date(2026, 9, 5), S3], as_of=as_of).shape[0] == 3
    with pytest.raises(MissingDataError):  # nothing stored in the span
        read_outcomes(reader, 20, [date(2026, 9, 20), date(2026, 9, 22)], as_of=as_of)
    none_wanted = [date(2026, 8, 30), date(2026, 9, 4)]  # partitions inside, none wanted
    assert read_outcomes(reader, 20, none_wanted, as_of=as_of).empty


def test_outcome_seqs_are_the_wanted_committed_partitions_commit_sequences() -> None:
    reader = _store()
    seqs = outcome_seqs(reader, [S1, S3])
    assert set(seqs) == {S1, S3} and all(isinstance(v, int) for v in seqs.values())
    assert set(outcome_seqs(reader, [S2])) == {S2}
    assert outcome_seqs(reader, []) == {}
    assert outcome_seqs(reader, [date(2020, 1, 1)]) == {}  # no such partition


def test_outcome_known_is_the_latest_known_row_of_each_closed_window_by_as_of() -> None:
    reader = _store()
    early, late = datetime(2026, 10, 1, 22, tzinfo=UTC), datetime(2026, 10, 5, 22, tzinfo=UTC)
    now = datetime(2026, 10, 9, tzinfo=UTC)
    assert outcome_known(reader, [S1, S2, S3], now) == {  # the benchmark SPY only, QQQ's row aside
        (S1, 20): late, (S1, 6): early, (S2, 20): early, (S3, 20): early,
    }  # fmt: skip
    assert outcome_known(reader, [S1, S2, S3], datetime(2026, 10, 3, tzinfo=UTC))[S1, 20] == early
    assert outcome_known(reader, [S1, S3], datetime(2026, 9, 1, tzinfo=UTC)) == {}
    assert outcome_known(reader, [S2], now) == {(S2, 20): early}


def test_outcome_stamps_name_the_spy_rows_known_by_as_of_beside_their_stamps() -> None:
    reader = _store()
    now = datetime(2026, 10, 9, tzinfo=UTC)
    known, names = outcome_stamps(reader, [S1, S2, S3], now, names_for=[6, 20])
    assert known == outcome_known(reader, [S1, S2, S3], now)
    assert names == {  # the benchmark SPY only (QQQ's row aside); r2's later row is a name too
        (S1, 20): frozenset({"EQ:A", "EQ:B"}), (S1, 6): frozenset({"EQ:A"}),
        (S2, 20): frozenset({"EQ:A"}), (S3, 20): frozenset({"EQ:A"}),
    }  # fmt: skip
    only20 = outcome_stamps(reader, [S1, S2], now, names_for=[20])[1]
    assert set(only20) == {(S1, 20), (S2, 20)}  # horizon 6 asked for no names
    _, early = outcome_stamps(reader, [S1], datetime(2026, 10, 3, tzinfo=UTC), names_for=[20])
    assert early[S1, 20] == {"EQ:A", "EQ:B"}  # r2 (EQ:B again) is not known yet: the same names
    assert outcome_stamps(reader, [S1, S3], datetime(2026, 9, 1, tzinfo=UTC)) == ({}, {})


def test_no_name_set_is_built_unless_a_horizon_asks_for_names() -> None:
    reader = _store()
    now = datetime(2026, 10, 9, tzinfo=UTC)
    known, names = outcome_stamps(reader, [S1, S2, S3], now)
    assert names == {} and known == outcome_known(reader, [S1, S2, S3], now)
