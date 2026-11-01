"""The chain P&L reads (``outcomes/option/structure_pnl@v1``, ADR 0053 amendment, EB H13): the
rows of one horizon for the asked start sessions in the price outcomes' shape (return fields
empty, benchmark ``none``); runs merge per (underlying, structure, tenor, horizon) and a later
run wins; ``as_of`` drops rows known after it, row by row (a row is known when its exit chain
was); stamps and commit sequences per (start session, horizon); nothing stored is a
``MissingDataError``; the schema rejects a COMPLETE row without a P&L and an UNMEASURED one with."""

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from algotrade.core.model.errors import DataValidationError, MissingDataError
from algotrade.data.outcomes import (
    CHAIN_COLUMNS,
    OUTCOME_FIELDS,
    chain_seqs,
    chain_sessions,
    chain_stamps,
    read_chain,
)
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.schemas import OPTION_PNL
from algotrade.storage.tables.writers import StoreWriter

S1, S2 = date(2026, 10, 5), date(2026, 10, 6)
EARLY, LATE = datetime(2026, 10, 12, 23, tzinfo=UTC), datetime(2026, 10, 14, 23, tzinfo=UTC)


def _row(iid: str, h: int = 5, pnl: float | None = 0.02, **changes: object) -> dict[str, object]:
    done = pnl is not None
    row = {
        "instrument_id": iid, "ts": pd.Timestamp("2026-10-05T20:00Z"), "structure": "atm_straddle",
        "tenor_days": 30, "horizon_sessions": h, "window_end": date(2026, 10, 12),
        "call_id": "OPT:C", "put_id": "OPT:P", "expiry": date(2026, 11, 6), "strike": 100.0,
        "entry_spot": 100.0, "entry_mid": 5.0, "entry_ask": 5.2,
        "exit_spot": 101.0 if done else None, "exit_mid": 7.0 if done else None,
        "exit_bid": 6.8 if done else None, "exit_kind": "QUOTE" if done else None,
        "pnl_per_premium": pnl, "pnl_exec_per_premium": pnl, "pnl_per_underlying": pnl,
        "hedged_pnl_per_premium": pnl, "hedged_pnl_per_underlying": pnl,
        "outcome_status": "COMPLETE" if done else "UNMEASURED",
        "outcome_reason": None if done else "STALE_CHAIN:2026-10-08", "hedge_reason": None,
    }  # fmt: skip
    return {**row, **changes}


def _write(writer: StoreWriter, day: date, run: str, known: datetime, rows: list[dict]) -> None:
    frame = pd.DataFrame(rows).assign(
        session_date=day, knowledge_ts=pd.Timestamp(known), source="option_outcomes", run_id=run
    )
    writer.write_table(OPTION_PNL, day, run, frame)


def _store() -> StoreReader:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    _write(writer, S1, "r1", EARLY, [_row("EQ:A"), _row("EQ:B", pnl=None), _row("EQ:A", h=2)])
    _write(writer, S1, "r2", LATE, [_row("EQ:B", pnl=0.05)])  # a re-run: its row wins
    _write(writer, S2, "r3", EARLY, [_row("EQ:A", pnl=0.09)])
    return StoreReader(backend)


def test_the_rows_of_one_horizon_in_the_price_outcomes_shape() -> None:
    out = read_chain(_store(), 5, [S1, S2])
    got = zip(out["session_date"], out["instrument_id"], out["pnl_per_underlying"], strict=True)
    assert list(got) == [(S1, "EQ:A", 0.02), (S1, "EQ:B", 0.05), (S2, "EQ:A", 0.09)]
    assert set(CHAIN_COLUMNS) <= set(out.columns) and set(out["benchmark"]) == {"none"}
    assert out[list(OUTCOME_FIELDS[:5])].isna().all().all()  # the return fields are empty
    assert list(read_chain(_store(), 2, [S1])["instrument_id"]) == ["EQ:A"]


def test_as_of_drops_rows_known_after_it_row_by_row() -> None:
    out = read_chain(_store(), 5, [S1], as_of=datetime(2026, 10, 13, tzinfo=UTC))
    assert list(zip(out["instrument_id"], out["outcome_status"], strict=True)) == [
        ("EQ:A", "COMPLETE"),
        ("EQ:B", "UNMEASURED"),
    ]  # the re-run of B was not yet known: B is still the unmeasured row


def test_an_unmeasured_row_has_its_reason_and_no_pnl() -> None:
    out = read_chain(_store(), 5, [S1], as_of=datetime(2026, 10, 13, tzinfo=UTC))
    b = out[out["instrument_id"] == "EQ:B"].iloc[0]
    assert b["outcome_reason"] == "STALE_CHAIN:2026-10-08" and pd.isna(b["pnl_per_underlying"])


def test_stamps_per_start_session_and_horizon_and_commit_sequences() -> None:
    reader = _store()
    known, names = chain_stamps(reader, [S1, S2], LATE, names_for=[5])
    assert known[S1, 5] == LATE and known[S1, 2] == EARLY and known[S2, 5] == EARLY
    assert names[S1, 5] == frozenset({"EQ:A", "EQ:B"}) and (S1, 2) not in names
    assert set(chain_seqs(reader, [S1, S2, date(2026, 10, 7)])) == {S1, S2}
    assert chain_sessions(reader) == [S1, S2]


def test_nothing_stored_is_missing_data_and_no_sessions_is_empty() -> None:
    reader = StoreReader(MemoryBackend())
    with pytest.raises(MissingDataError, match="option-outcomes"):
        read_chain(reader, 5, [S1])
    assert chain_sessions(reader) == [] and chain_seqs(reader, []) == {}


@pytest.mark.parametrize(
    ("row", "problem"),
    [
        (_row("EQ:A", pnl=None, outcome_reason=None), "needs an outcome_reason"),
        (_row("EQ:A", pnl=None, pnl_per_underlying=0.0), "must be null when UNMEASURED"),
        (_row("EQ:A", pnl_per_underlying=None), "is null on a COMPLETE outcome"),
        (_row("EQ:A", exit_kind="MID"), "exit_kind must be one of"),
        (_row("EQ:A", outcome_status="PARTIAL"), "outcome_status must be one of"),
        (_row("EQ:A", hedged_pnl_per_premium=None), "is null on a COMPLETE outcome with no hedge"),
        (_row("EQ:A", hedge_reason="NO_DELTA:2026-10-06"), "must be null when hedge_reason is set"),
    ],
)
def test_the_schema_rejects_a_row_that_breaks_the_status_or_hedge_rule(
    row: dict[str, object], problem: str
) -> None:
    writer = StoreWriter(MemoryBackend())
    with pytest.raises(DataValidationError, match=problem):
        _write(writer, S1, "r1", EARLY, [row])


def test_a_complete_row_with_a_hedge_reason_has_its_hedged_columns_null() -> None:
    row = _row(
        "EQ:A", hedged_pnl_per_premium=None, hedged_pnl_per_underlying=None,
        hedge_reason="NO_DELTA:2026-10-06",
    )  # fmt: skip
    writer = StoreWriter(MemoryBackend())
    _write(writer, S1, "r1", EARLY, [row])  # accepted: the unhedged P&L stands


def test_a_table_without_a_licence_column_has_no_licence_frames() -> None:
    """``forward_returns@v2`` and the chain grain declare no ``licence`` column yet (E4 adds it
    to ``structure_pnl@v2``): their rows are open and nothing is read."""
    from datetime import date  # noqa: PLC0415

    from algotrade.data.outcomes import licence_frames  # noqa: PLC0415
    from algotrade.storage.backends.memory import MemoryBackend  # noqa: PLC0415
    from algotrade.storage.tables.readers import StoreReader  # noqa: PLC0415

    reader = StoreReader(MemoryBackend())
    for chain in (False, True):
        assert licence_frames(reader, chain, [date(2026, 1, 5)]) == []
