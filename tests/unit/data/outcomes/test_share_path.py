"""The share path reads (``outcomes/instrument/share_path@v1``, ADR 0088, E3c-2): the rows of one
hold for the asked start sessions in the price outcomes' shape with the return fields mapped
(``fwd_return`` the underlying's, long-oriented, even for a short whose own return is its
negative); every read holds the run's (``position_key``, benchmark) so another setup's row never
makes a session look closed; ``as_of`` drops rows known after it, row by row; stamps, commit
sequences and licences per the run's keys; nothing stored for the keys is a ``MissingDataError``."""

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from algotrade.core.model.errors import MissingDataError
from algotrade.data.outcomes import (
    OUTCOME_FIELDS,
    SHARE_COLUMNS,
    SHARE_FIELDS,
    read_share_path,
    read_share_path_stored,
    share_path_seqs,
    share_path_sessions,
    share_path_stamps,
)
from algotrade.data.outcomes.share_path import share_path_licences
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.schemas import SHARE_PATH
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import share_path_row, stamped

S1, S2 = date(2026, 10, 5), date(2026, 10, 6)
EARLY, LATE = datetime(2026, 10, 12, 23, tzinfo=UTC), datetime(2026, 10, 14, 23, tzinfo=UTC)
MINE = ("mine", "SPY")
KEYS = [MINE]


def _write(
    writer: StoreWriter, day: date, run: str, known: datetime, rows: list[dict[str, object]]
) -> None:
    writer.write_table(SHARE_PATH, day, run, stamped(rows, day, run, known, "share_outcomes"))


def _store() -> StoreReader:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    rows = [
        share_path_row("EQ:A", "mine", S1),
        share_path_row("EQ:B", "mine", S1, hold=5),  # another hold of the same key
        share_path_row("EQ:A", "theirs", S1, gross_return=0.5, underlying_return=0.5),
        share_path_row("EQ:A", "mine", S1, benchmark="none", benchmark_return=None),
    ]
    _write(writer, S1, "r1", EARLY, rows)
    _write(writer, S2, "r2", EARLY, [share_path_row("EQ:A", "theirs", S2)])  # no row of mine
    return StoreReader(backend)


def test_a_read_keeps_the_runs_keys_only_and_maps_the_returns_as_the_price_grain() -> None:
    out = read_share_path(_store(), 3, [S1, S2], KEYS)
    assert list(out["instrument_id"]) == ["EQ:A"]  # not "theirs", not the other benchmark
    assert {*OUTCOME_FIELDS, *SHARE_FIELDS} <= set(out.columns)
    row = out.iloc[0]
    assert row["fwd_return"] == pytest.approx(0.06)  # the underlying's
    assert row["fwd_excess_return"] == pytest.approx(0.05)  # less the benchmark's
    assert row["fwd_max_drawdown"] == 0.0 and row["gross_return"] == pytest.approx(0.06)
    assert pd.isna(row["fwd_max_return"]) and pd.isna(row["fwd_realised_vol"])
    assert (row["exit_kind"], row["exit_index"], row["horizon_sessions"]) == ("TAKE_PROFIT", 2, 3)
    assert set(SHARE_COLUMNS) <= set(out.columns)


def test_a_short_rows_return_stays_the_underlyings_and_its_dip_is_null() -> None:
    backend = MemoryBackend()
    short = share_path_row(
        "EQ:A", "mine", S1, gross_return=-0.06, underlying_return=0.06, max_adverse=None
    )
    _write(StoreWriter(backend), S1, "r1", EARLY, [short])
    out = read_share_path(StoreReader(backend), 3, [S1], KEYS)
    assert out.iloc[0]["fwd_return"] == pytest.approx(
        0.06
    )  # long-oriented: the sign is the caller's
    assert out.iloc[0]["gross_return"] == pytest.approx(-0.06)
    assert pd.isna(out.iloc[0]["fwd_max_drawdown"])


def test_a_session_holding_only_another_setups_rows_is_not_closed_for_this_one() -> None:
    reader = _store()
    stored = read_share_path_stored(reader, [S1, S2], KEYS)
    assert stored is not None and set(stored["session_date"]) == {S1}  # S2 has none of mine
    with pytest.raises(MissingDataError, match="share-outcomes"):
        read_share_path(reader, 3, [S2], KEYS)
    assert read_share_path_stored(reader, [S2], KEYS) is None
    assert share_path_stamps(reader, [S2], LATE, KEYS) == ({}, {})


def test_as_of_drops_a_row_known_after_it_row_by_row() -> None:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    _write(writer, S1, "r1", EARLY, [share_path_row("EQ:A", "mine", S1)])
    _write(writer, S1, "r2", LATE, [share_path_row("EQ:B", "mine", S1)])
    reader = StoreReader(backend)
    assert list(read_share_path(reader, 3, [S1], KEYS, as_of=EARLY)["instrument_id"]) == ["EQ:A"]
    both = read_share_path(reader, 3, [S1], KEYS, as_of=LATE)
    assert list(both["instrument_id"]) == ["EQ:A", "EQ:B"]
    known, names = share_path_stamps(reader, [S1], EARLY, KEYS, names_for=[3])
    assert known == {(S1, 3): EARLY} and names == {(S1, 3): frozenset({"EQ:A"})}


def test_stamps_name_the_horizons_asked_for_and_ignore_other_keys() -> None:
    reader = _store()
    known, names = share_path_stamps(reader, [S1], LATE, KEYS, names_for=[5])
    assert set(known) == {(S1, 3), (S1, 5)}  # the other key's row adds no stamp of its own
    assert names == {(S1, 5): frozenset({"EQ:B"})}
    other, _ = share_path_stamps(reader, [S1], LATE, [("theirs", "SPY")])
    assert set(other) == {(S1, 3)}


def test_sessions_seqs_and_licences_follow_the_partitions_and_the_keys() -> None:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    _write(writer, S1, "r1", EARLY, [share_path_row("EQ:A", "mine", S1, licence="personal")])
    _write(writer, S2, "r2", EARLY, [share_path_row("EQ:A", "theirs", S2, licence="personal")])
    reader = StoreReader(backend)
    assert share_path_sessions(reader) == [S1, S2]
    seqs = share_path_seqs(reader, [S1, S2, date(2026, 10, 9)])
    assert set(seqs) == {S1, S2} and share_path_seqs(reader, []) == {}
    (mine,) = share_path_licences(reader, [S1, S2], KEYS)
    assert set(mine["licence"]) == {"personal"}  # S1's row, the span read
    assert share_path_licences(reader, [S2], [("nobody", "SPY")]) == []
    assert share_path_licences(reader, [], KEYS) == []


def test_a_past_as_of_sees_only_windows_that_had_closed_not_just_the_early_exits() -> None:
    """A replay at ``as_of`` must not keep a row whose exit came early (known by ``as_of``) while
    its hold cap's window was still open: only early exits would show, an upward-biased sample."""
    backend = MemoryBackend()
    known = datetime(2026, 10, 5, 22, tzinfo=UTC)  # the row says it was known at S's own close
    _write(StoreWriter(backend), S1, "r1", known, [share_path_row("EQ:A", "mine", S1)])
    reader = StoreReader(backend)  # window_end 2026-10-08
    before, after = datetime(2026, 10, 7, 23, tzinfo=UTC), datetime(2026, 10, 8, 21, tzinfo=UTC)
    assert read_share_path(reader, 3, [S1], KEYS, as_of=before).empty
    assert share_path_stamps(reader, [S1], before, KEYS) == ({}, {})
    assert len(read_share_path(reader, 3, [S1], KEYS, as_of=after)) == 1
    assert (S1, 3) in share_path_stamps(reader, [S1], after, KEYS)[0]
