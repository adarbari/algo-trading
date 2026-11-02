"""``read_paper``: one user's rows with a signal session in the window, nothing stored is an
empty frame, and ``as_of`` keeps the book an earlier night saw."""

from datetime import UTC, date, datetime

import pandas as pd

from algotrade.data.paper import PAPER_COLUMNS, read_paper, read_stored
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.edge_schemas import EDGE_PAPER
from algotrade.storage.tables.readers import StoreReader
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


def test_one_owners_stored_rows_in_the_window_sorted_by_signal_session() -> None:
    out = read_stored(_store(), "u1", D1, D2)
    assert list(out.columns) == list(PAPER_COLUMNS)
    assert list(zip(out["signal_session"], out["instrument_id"], strict=True)) == [
        (D1, "EQ:A"), (D2, "EQ:A"),
    ]  # fmt: skip


def test_the_window_bounds_the_signal_sessions() -> None:
    assert list(read_stored(_store(), "u1", D2, D2)["signal_session"]) == [D2]


def test_a_later_run_settles_the_row_and_as_of_keeps_the_earlier_book() -> None:
    store = _store()
    assert list(read_stored(store, "u1", D1, D1)["status"]) == ["won"]
    early = datetime(2026, 9, 2, tzinfo=UTC)
    assert list(read_stored(store, "u1", D1, D1, early)["status"]) == ["open"]


def test_nothing_stored_is_an_empty_frame_with_the_columns() -> None:
    out = read_stored(StoreReader(MemoryBackend()), "u1", D1, D2)
    assert out.empty and list(out.columns) == list(PAPER_COLUMNS)
    assert isinstance(out, pd.DataFrame)


def test_read_paper_keeps_only_the_rows_of_each_edges_record_owner() -> None:
    """A follower's old row of a site edge is not part of the shared record."""
    backend = MemoryBackend()
    rows = [_row("site", "EQ:A", D1), _row("u1", "EQ:A", D1), _row("u1", "EQ:Z", D1)]
    rows[2]["edge_id"] = "mine"
    writer = StoreWriter(backend)
    writer.write_table(EDGE_PAPER.name, D1, "r1", stamped(rows, D1, "r1", source="edge-signals"))
    store = StoreReader(backend)
    shared = read_paper(store, {"drift": "site", "mine": "u1"}, D1, D2)
    assert sorted(zip(shared["user_id"], shared["edge_id"], strict=True)) == [
        ("site", "drift"), ("u1", "mine"),
    ]  # fmt: skip
    assert read_paper(store, {}, D1, D2).empty
    assert len(read_stored(store, "u1", D1, D2)) == 2  # the owner's own nightly settles both


def test_a_row_written_before_the_return_and_licence_columns_reads_with_them_null() -> None:
    """The partition of D1 was written by the first run without the columns; a later run that has
    them merges into it, and both rows read back under ``PAPER_COLUMNS`` (null, never missing)."""
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    known = datetime(2026, 9, 1, 22, tzinfo=UTC)
    old = _row("site", "EQ:A", D1)
    new = _row("site", "EQ:B", D1, "won") | {"return": 0.04, "licence": "personal"}
    for run, row in (("r1", old), ("r2", new)):
        writer.write_table(EDGE_PAPER.name, D1, run, stamped([row], D1, run, known, "edge-signals"))
    out = read_stored(StoreReader(backend), "site", D1, D1).set_index("instrument_id")
    assert list(out.columns) == [c for c in PAPER_COLUMNS if c != "instrument_id"]
    assert pd.isna(out.loc["EQ:A", "return"]) and pd.isna(out.loc["EQ:A", "licence"])
    assert out.loc["EQ:B", "return"] == 0.04 and out.loc["EQ:B", "licence"] == "personal"


def test_a_row_written_before_the_trade_contract_columns_reads_with_them_null() -> None:
    """E6a (ADR 0088): the exit kind, return on capital and price source of a settled trade; an
    older row, in the same partition, reads them null, never a default."""
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    known = datetime(2026, 9, 1, 22, tzinfo=UTC)
    old = _row("site", "EQ:A", D1, "won") | {"return": 0.02}
    new = _row("site", "EQ:B", D1, "won") | {
        "return": 0.04, "exit_kind": "HORIZON", "return_on_capital": 0.039, "price_source": "bars",
    }  # fmt: skip
    for run, row in (("r1", old), ("r2", new)):
        writer.write_table(EDGE_PAPER.name, D1, run, stamped([row], D1, run, known, "edge-signals"))
    out = read_stored(StoreReader(backend), "site", D1, D1).set_index("instrument_id")
    for column in ("exit_kind", "return_on_capital", "price_source"):
        assert pd.isna(out.loc["EQ:A", column]), column
    assert (
        out.loc["EQ:B", "exit_kind"] == "HORIZON" and out.loc["EQ:B", "return_on_capital"] == 0.039
    )
    assert out.loc["EQ:A", "return"] == 0.02  # the meaning of return is unchanged
