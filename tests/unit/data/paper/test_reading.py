"""``read_paper``: one user's rows with a signal session in the window, nothing stored is an
empty frame, and ``as_of`` keeps the book an earlier night saw."""

from datetime import UTC, date, datetime

import pandas as pd

from algotrade.data.paper import PAPER_COLUMNS, read_paper
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.schemas import EDGE_PAPER
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped

D1, D2 = date(2026, 9, 1), date(2026, 9, 3)


def _row(user: str, iid: str, signal: date, status: str = "open") -> dict[str, object]:
    return {
        "user_id": user, "edge_id": "drift", "signal_session": signal, "instrument_id": iid,
        "status": status, "buy_session": signal, "sell_session": signal, "rank": 1,
        "horizon_sessions": 2, "delisted": False,
    }  # fmt: skip


def _store() -> StoreReader:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    early, late = datetime(2026, 9, 1, 22, tzinfo=UTC), datetime(2026, 9, 5, 22, tzinfo=UTC)
    for day, run, known, rows in (
        (D1, "r1", early, [_row("u1", "EQ:A", D1), _row("u2", "EQ:B", D1)]),
        (D2, "r2", early, [_row("u1", "EQ:A", D2)]),
        (D1, "r3", late, [_row("u1", "EQ:A", D1, "won")]),  # settles u1's trade in its partition
    ):
        writer.write_table(
            EDGE_PAPER.name, day, run, stamped(rows, day, run, known, "edge-signals")
        )
    return StoreReader(backend)


def test_one_users_rows_in_the_window_sorted_by_signal_session() -> None:
    out = read_paper(_store(), "u1", D1, D2)
    assert list(out.columns) == list(PAPER_COLUMNS)
    assert list(zip(out["signal_session"], out["instrument_id"], strict=True)) == [
        (D1, "EQ:A"), (D2, "EQ:A"),
    ]  # fmt: skip


def test_the_window_bounds_the_signal_sessions() -> None:
    assert list(read_paper(_store(), "u1", D2, D2)["signal_session"]) == [D2]


def test_a_later_run_settles_the_row_and_as_of_keeps_the_earlier_book() -> None:
    store = _store()
    assert list(read_paper(store, "u1", D1, D1)["status"]) == ["won"]
    early = datetime(2026, 9, 2, tzinfo=UTC)
    assert list(read_paper(store, "u1", D1, D1, early)["status"]) == ["open"]


def test_nothing_stored_is_an_empty_frame_with_the_columns() -> None:
    out = read_paper(StoreReader(MemoryBackend()), "u1", D1, D2)
    assert out.empty and list(out.columns) == list(PAPER_COLUMNS)
    assert isinstance(out, pd.DataFrame)
