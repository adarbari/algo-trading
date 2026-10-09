"""The Ideas signals: tonight's buys, tomorrow's sells and each followed edge's record, all from
the stored paper record as ``ctx.session`` knew it."""

from datetime import date

import pytest

from algotrade.data.paper import job_name
from algotrade.services.read.edge_desk.desk import load_edge_desk
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.result_writer import ResultWriter
from tests.unit.services.read.edge_desk.conftest import (
    FOLLOWED,
    KNOWN,
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


def _night(backend: MemoryBackend, day: date, stats: dict, finish: bool = True) -> None:  # type: ignore[type-arg]
    """The run record a nightly ``edge-signals`` job leaves for ``me`` on ``day``."""
    record = RunRecord(f"edge-paper-{day}", job_name("me"), day, KNOWN)
    ResultWriter(backend).save_run(record.finish(KNOWN, complete=finish, stats=stats))


def _tonight(backend: MemoryBackend) -> tuple[str, str]:
    (edge,) = load_edge_desk(context(backend)).followed
    return edge.tonight, edge.tonight_reason


def test_a_due_edge_whose_screen_failed_says_why_instead_of_an_empty_list(
    backend: MemoryBackend,
) -> None:
    reason = "no rollups/instrument/option_liquidity@v1 for 2026-10-05"
    _night(backend, SESSION, {"tonight": {"drift": {"state": "skipped", "reason": reason}}})
    desk = load_edge_desk(context(backend))
    assert desk.buys == () and _tonight(backend) == ("skipped", reason)


@pytest.mark.parametrize("state", ["signalled", "no_picks", "not_due"])
def test_the_nightlys_state_for_an_edge_is_served(backend: MemoryBackend, state: str) -> None:
    _night(backend, SESSION, {"tonight": {"drift": {"state": state, "reason": ""}}})
    assert _tonight(backend) == (state, "")


def test_no_run_for_the_session_is_not_run_never_nothing_due(backend: MemoryBackend) -> None:
    assert _tonight(backend) == ("not_run", "")  # no run record at all
    _night(backend, date(2026, 10, 2), {"tonight": {"drift": {"state": "signalled"}}})
    assert _tonight(backend) == ("not_run", "")  # an earlier session's run is not tonight's
    _night(backend, SESSION, {"tonight": {}}, finish=False)
    assert _tonight(backend) == ("not_run", "")  # an unfinished run says nothing
    _night(backend, SESSION, {"tonight": {"other": {"state": "signalled"}}})
    assert _tonight(backend) == ("not_run", "")  # a run that never looked at this edge


def test_the_sessions_the_nightly_missed_are_served_per_edge(backend: MemoryBackend) -> None:
    missed = [
        {"edge": "drift", "session": "2026-10-01"},
        {"edge": "other", "session": "2026-10-02"},
    ]
    _night(backend, SESSION, {"tonight": {"drift": {"state": "signalled"}}, "missed": missed})
    (edge,) = load_edge_desk(context(backend)).followed
    assert edge.missed == (date(2026, 10, 1),)
