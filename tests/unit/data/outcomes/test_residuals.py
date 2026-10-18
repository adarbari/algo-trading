"""``read_residuals`` and ``attach_residuals``: the stored residual rows of the asked start
sessions only, ``as_of`` dropping rows written after it; attached to one horizon's forward rows,
a name with no residual row is UNMEASURED ``NO_RESIDUAL_ROW`` (never a zero, never the excess
return), a stored UNMEASURED keeps its reason, and the forward frame is otherwise untouched."""

from datetime import UTC, date, datetime

import pandas as pd

from algotrade.data.outcomes import (
    NO_RESIDUAL_ROW,
    RESIDUAL_FIELDS,
    attach_residuals,
    read_residuals,
)
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.schemas import RESIDUAL_RETURNS
from algotrade.storage.tables.writers import StoreWriter

S1, S2 = date(2026, 9, 1), date(2026, 9, 2)
EARLY, LATE = datetime(2026, 10, 1, 22, tzinfo=UTC), datetime(2026, 10, 5, 22, tzinfo=UTC)


def _row(iid: str, h: int, resid: float | None, reason: str | None = None) -> dict[str, object]:
    return {
        "instrument_id": iid, "ts": pd.Timestamp("2026-09-01T20:00Z"), "horizon_sessions": h,
        "window_end": date(2026, 10, 1), "beta_session": date(2026, 8, 31),
        "fwd_residual_return": resid, "fwd_factor_return": None if resid is None else 0.01,
        "outcome_status": "COMPLETE" if reason is None else "UNMEASURED", "outcome_reason": reason,
    }  # fmt: skip


def _write(writer: StoreWriter, day: date, run: str, known: datetime, rows: list[dict]) -> None:
    frame = pd.DataFrame(rows).assign(
        session_date=day, knowledge_ts=pd.Timestamp(known), source="residual_returns", run_id=run
    )
    writer.write_table(RESIDUAL_RETURNS, day, run, frame)


def _store() -> StoreReader:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    rows = [
        _row("EQ:A", 20, 0.03),
        _row("EQ:B", 20, None, "NO_FACTOR_HISTORY"),
        _row("EQ:A", 6, 0.5),
    ]
    _write(writer, S1, "r1", EARLY, rows)
    _write(writer, S1, "r2", LATE, [_row("EQ:A", 20, 0.04)])  # a re-run: its row wins
    _write(writer, S2, "r3", EARLY, [_row("EQ:A", 20, 0.09)])
    return StoreReader(backend)


def _forward(*ids: str, day: date = S1) -> pd.DataFrame:
    return pd.DataFrame(
        {"instrument_id": list(ids), "session_date": day, "fwd_excess_return": 0.5,
         "outcome_status": "COMPLETE"}
    )  # fmt: skip


def test_only_the_asked_sessions_partitions_are_read() -> None:
    frame = read_residuals(_store(), [S1])
    assert frame is not None and set(frame["session_date"]) == {S1}
    assert read_residuals(_store(), []) is None
    assert read_residuals(_store(), [date(2026, 8, 3)]) is None  # nothing stored there


def test_as_of_drops_rows_written_after_it() -> None:
    old = read_residuals(_store(), [S1], datetime(2026, 10, 2, tzinfo=UTC))
    assert old is not None
    a20 = old[(old["instrument_id"] == "EQ:A") & (old["horizon_sessions"] == 20)]
    assert list(a20["fwd_residual_return"]) == [0.03]
    new = read_residuals(_store(), [S1])
    assert new is not None
    a20 = new[(new["instrument_id"] == "EQ:A") & (new["horizon_sessions"] == 20)]
    assert list(a20["fwd_residual_return"]) == [0.04]


def test_attach_joins_one_horizon_and_marks_a_missing_row_unmeasured() -> None:
    forward = _forward("EQ:A", "EQ:B", "EQ:NEW")
    out = attach_residuals(forward, read_residuals(_store(), [S1]), 20)
    assert set(RESIDUAL_FIELDS) <= set(out.columns) and list(out.index) == list(forward.index)
    by = out.set_index("instrument_id")
    assert (
        by.loc["EQ:A", "fwd_residual_return"] == 0.04
        and by.loc["EQ:A", "residual_status"] == "COMPLETE"
    )
    assert by.loc["EQ:B", "residual_reason"] == "NO_FACTOR_HISTORY"
    assert by.loc["EQ:NEW", "residual_status"] == "UNMEASURED"
    assert by.loc["EQ:NEW", "residual_reason"] == NO_RESIDUAL_ROW
    assert out["fwd_excess_return"].eq(0.5).all()  # the forward fields are untouched


def test_nothing_stored_marks_every_row_unmeasured_never_zero() -> None:
    out = attach_residuals(_forward("EQ:A"), None, 20)
    assert out["residual_reason"].iloc[0] == NO_RESIDUAL_ROW and pd.isna(
        out["fwd_residual_return"].iloc[0]
    )
    assert attach_residuals(_forward("EQ:A").iloc[0:0], None, 20).empty
