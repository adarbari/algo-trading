"""``paper_book``: one edge's rows for its record owner only, as known at the cut-off."""

from datetime import UTC, date, datetime

from algotrade.services.evaluation.portfolio_level.paper import paper_book
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.edge_schemas import EDGE_PAPER
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped

D1, D2 = date(2026, 9, 1), date(2026, 9, 2)
EARLY, LATE = datetime(2026, 9, 1, 22, tzinfo=UTC), datetime(2026, 9, 5, 22, tzinfo=UTC)


PLANNED = date(2026, 9, 3)


def _row(user: str, edge: str, iid: str, status: str = "open", signal: date = D1):
    """A row as the nightly writes it: ``sell_session`` is the planned sell from the signal on."""
    return {
        "user_id": user, "edge_id": edge, "signal_session": signal, "instrument_id": iid,
        "status": status, "buy_session": signal, "sell_session": PLANNED, "rank": 1,
        "horizon_sessions": 2, "delisted": False, "licence": "open",
    }  # fmt: skip


def _store() -> StoreReader:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    old = date(2026, 3, 2)  # signalled long before the session, still open
    for day, run, known, rows in (
        (
            D1,
            "r1",
            EARLY,
            [
                _row("site", "mine", "EQ:A"),
                _row("site", "other", "EQ:B"),
                _row("u2", "mine", "EQ:C"),
                _row("site", "mine", "EQ:S", "skipped"),
            ],
        ),
        (D1, "r2", LATE, [_row("site", "mine", "EQ:A", "won")]),  # settled after the cut-off
        (old, "r0", EARLY, [_row("site", "mine", "EQ:OLD", signal=old)]),
    ):
        writer.write_table(
            EDGE_PAPER.name, day, run, stamped(rows, day, run, known, "edge-signals")
        )
    return StoreReader(backend)


def _held(as_of: datetime, name: str):
    return next(
        t for t in paper_book(_store(), "mine", "site", D1, as_of) if t.instrument_id == name
    )


def test_only_this_edges_rows_for_its_owner_that_entered() -> None:
    book = paper_book(_store(), "mine", "site", D1, EARLY)
    assert {t.instrument_id for t in book} == {"EQ:A", "EQ:OLD"}  # not another edge, owner, skipped


def test_an_open_row_is_due_at_its_planned_sell_and_its_exit_is_not_known() -> None:
    a = next(
        t for t in paper_book(_store(), "mine", "site", D1, EARLY) if t.instrument_id == "EQ:A"
    )
    assert (a.exit_session, a.planned_exit, a.capital) == (None, PLANNED, None)


def test_a_settlement_written_after_the_cut_off_is_not_leaked() -> None:
    late = next(
        t for t in paper_book(_store(), "mine", "site", D1, LATE) if t.instrument_id == "EQ:A"
    )
    assert late.exit_session == PLANNED


def test_a_trade_still_open_from_an_early_signal_is_in_the_book() -> None:
    old = next(
        t for t in paper_book(_store(), "mine", "site", D1, EARLY) if t.instrument_id == "EQ:OLD"
    )
    assert old.entry_session == date(2026, 3, 2)  # not dropped by a too-recent window
