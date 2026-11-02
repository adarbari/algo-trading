"""The option trade reads (``outcomes/option/structure_pnl@v2``, ADR 0088, design 2.5): the rows of
one hold for the asked start sessions in the price outcomes' shape (return fields empty, benchmark
``none``, ``hold_sessions`` read as ``horizon_sessions``); runs merge per (underlying,
``position_key``) and a later run wins; ``as_of`` drops rows known after it, row by row (a row is
known when its exit chain was); stamps and commit sequences per (start session, hold); nothing
stored is a ``MissingDataError``; the cutover keeps one source per session (H6)."""

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from algotrade.core.model.errors import MissingDataError
from algotrade.data.outcomes import (
    CHAIN_COLUMNS,
    OUTCOME_FIELDS,
    chain_seqs,
    chain_sessions,
    chain_stamps,
    licence_frames,
    read_chain,
)
from algotrade.data.outcomes.chain import FIRST_CBOE_CHAIN_SESSION, select_chain
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.schemas import STRUCTURE_PNL
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped, structure_pnl_row

S1, S2 = date(2026, 10, 5), date(2026, 10, 6)
EARLY, LATE = datetime(2026, 10, 12, 23, tzinfo=UTC), datetime(2026, 10, 14, 23, tzinfo=UTC)


def _row(iid: str, h: int = 5, pnl: float | None = 0.5, **changes: object) -> dict[str, object]:
    done = pnl is not None
    row = structure_pnl_row(iid, f"k{h}", hold=h, pnl_mid=pnl)
    if not done:
        row |= {"outcome_status": "UNMEASURED", "outcome_reason": "STALE_CHAIN:2026-10-08"}
        for column in (
            "exit_session",
            "exit_kind",
            "exit_basis",
            "exit_net_mid",
            "option_pnl",
            "stock_pnl",
        ):
            row[column] = None
    return {**row, **changes}


def _write(
    writer: StoreWriter, day: date, run: str, known: datetime, rows: list[dict[str, object]]
) -> None:
    writer.write_table(STRUCTURE_PNL, day, run, stamped(rows, day, run, known, "option_outcomes"))


def _store() -> StoreReader:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    _write(writer, S1, "r1", EARLY, [_row("EQ:A"), _row("EQ:B", pnl=None), _row("EQ:A", h=2)])
    _write(writer, S1, "r2", LATE, [_row("EQ:B", pnl=0.7)])  # a re-run: its row wins
    _write(writer, S2, "r3", EARLY, [_row("EQ:A", pnl=0.9)])
    return StoreReader(backend)


def test_the_rows_of_one_hold_in_the_price_outcomes_shape() -> None:
    out = read_chain(_store(), 5, [S1, S2])
    got = zip(out["session_date"], out["instrument_id"], out["pnl_mid"], strict=True)
    assert list(got) == [(S1, "EQ:A", 0.5), (S1, "EQ:B", 0.7), (S2, "EQ:A", 0.9)]
    assert set(CHAIN_COLUMNS) <= set(out.columns) and set(out["benchmark"]) == {"none"}
    assert set(out["horizon_sessions"]) == {5}  # the stored hold_sessions
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
    assert b["outcome_reason"] == "STALE_CHAIN:2026-10-08" and pd.isna(b["pnl_mid"])


def test_stamps_per_start_session_and_hold_and_commit_sequences() -> None:
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


def test_a_table_without_a_licence_column_has_no_licence_frames() -> None:
    """``forward_returns@v2`` declares no ``licence`` column: its rows are open, nothing is read."""
    assert licence_frames(StoreReader(MemoryBackend()), False, [date(2026, 1, 5)]) == []


def test_the_cutover_reads_one_source_per_session_on_every_path() -> None:
    """Cboe rows are read only from the first stored chain session, bought-history rows only
    before it: both sources written on both sides of the date, every read path drops the other."""
    before, on = date(2026, 10, 1), FIRST_CBOE_CHAIN_SESSION
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    for day in (before, on):
        rows = [
            _row("EQ:CBOE", licence="open", price_source="cboe"),
            _row("EQ:HIST", licence="personal", price_source="option_history"),
        ]
        _write(writer, day, f"r-{day}", EARLY, rows)
    reader = StoreReader(backend)
    out = read_chain(reader, 5, [before, on])
    assert sorted(zip(out["session_date"], out["instrument_id"], strict=True)) == [
        (before, "EQ:HIST"),
        (on, "EQ:CBOE"),
    ]
    _, names = chain_stamps(reader, [before, on], LATE, names_for=[5])
    assert names[before, 5] == frozenset({"EQ:HIST"}) and names[on, 5] == frozenset({"EQ:CBOE"})
    (licences,) = licence_frames(reader, True, [before, on])
    assert sorted(zip(licences["session_date"], licences["licence"], strict=True)) == [
        (before, "personal"),
        (on, "open"),
    ]


def test_the_option_trade_fields_of_the_contract_are_read_with_the_rows() -> None:
    out = read_chain(_store(), 5, [S1], as_of=datetime(2026, 10, 13, tzinfo=UTC))
    a = out[out["instrument_id"] == "EQ:A"].iloc[0]
    assert (a["exit_kind"], a["collateral"], a["price_source"], a["licence"]) == (
        "HORIZON", 95.0, "cboe", "open",
    )  # fmt: skip
    assert a["exit_session"] == date(2026, 10, 12) and pd.isna(
        a["max_adverse"]
    )  # the fixture row stores none


def test_a_set_of_rows_with_no_exit_still_has_the_exit_columns_as_null() -> None:
    """A partition set holding only UNMEASURED trades may carry no exit, collateral or adverse
    column at all: they read as null, never a KeyError (E6a)."""
    frame = stamped([_row("EQ:B", pnl=None)], S1, "r", EARLY, "option_outcomes")
    bare = frame.drop(columns=["exit_session", "exit_kind", "collateral"])
    out = select_chain(bare, 5, [S1])
    assert set(CHAIN_COLUMNS) <= set(out.columns)
    assert out[["exit_session", "exit_kind", "collateral", "max_adverse"]].isna().all().all()
