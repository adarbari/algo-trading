"""The Ideas signals: tonight's buys, tomorrow's sells and each followed edge's record, all from
the stored paper record as ``ctx.session`` knew it."""

from datetime import date

from algotrade.services.read.edge_desk.desk import load_edge_desk
from algotrade.storage.backends.memory import MemoryBackend
from tests.unit.services.read.edge_desk.conftest import (
    FOLLOWED,
    NEXT,
    SESSION,
    closed_trades,
    context,
    store,
    trade,
)


def test_the_desk_lists_tonights_buys_and_tomorrows_sells_best_first(
    backend: MemoryBackend,
) -> None:
    store(
        backend,
        [
            trade("EQ:B", SESSION, rank=2, sell=date(2026, 11, 3)),
            trade("EQ:A", SESSION, rank=1, sell=date(2026, 11, 3)),
            trade("EQ:S", date(2026, 9, 4), sell=NEXT),  # closes tomorrow: a sell
            trade("EQ:L", date(2026, 9, 4), sell=date(2026, 10, 9)),  # later: neither
        ],
    )
    desk = load_edge_desk(context(backend))
    assert (desk.session, desk.sell_session) == (SESSION, NEXT)
    assert [t.instrument_id for t in desk.buys] == ["EQ:A", "EQ:B"]
    assert [t.instrument_id for t in desk.sells] == ["EQ:S"]
    assert desk.buys[0].edge_name == "Drift"


def test_a_user_who_follows_nothing_gets_an_empty_desk(backend: MemoryBackend) -> None:
    store(backend, [trade("EQ:A", SESSION)])
    desk = load_edge_desk(context(backend, follow=None))
    assert desk.buys == desk.sells == desk.followed == ()


def test_a_trade_signalled_after_the_session_is_not_read(backend: MemoryBackend) -> None:
    store(backend, [trade("EQ:A", NEXT), trade("EQ:B", SESSION)])
    desk = load_edge_desk(context(backend))
    assert [t.instrument_id for t in desk.buys] == ["EQ:B"]


def test_a_trade_settled_later_is_open_for_a_session_before_its_sell_session(
    backend: MemoryBackend,
) -> None:
    store(backend, [trade("EQ:A", date(2026, 9, 21), "won", sell=date(2026, 10, 19))])
    earlier = load_edge_desk(context(backend, day=date(2026, 10, 5)))
    record = earlier.followed[0].record
    assert (record.open, record.closed) == (1, 0)
    later = load_edge_desk(context(backend, day=date(2026, 10, 19)))
    assert (later.followed[0].record.open, later.followed[0].record.closed) == (0, 1)


def test_every_followed_edge_carries_its_record_and_since(backend: MemoryBackend) -> None:
    store(backend, closed_trades(12, 8))
    (edge,) = load_edge_desk(context(backend)).followed
    assert (edge.edge_id, edge.state, edge.since) == ("drift", "following", FOLLOWED)
    assert (edge.record.closed, edge.record.wins) == (20, 12)
