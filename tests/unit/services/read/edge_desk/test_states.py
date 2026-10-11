"""Every recorded edge's live state: the live record's own state (never judged twice), served for
the followed edges and the site's, each with its Guide term, as the session's cutoff knew the
paper rows (ADR 0064 decision 9)."""

from datetime import UTC, date, datetime

import pytest

from algotrade.config.user import SITE_USER, UserContext
from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext, open_stores
from algotrade.services.read.edge_desk.desk import load_edge_desk
from algotrade.services.read.edge_desk.states import LIVE_STATES, TERM, below_range
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.result_writer import ResultWriter
from tests.unit.services.read.edge_desk.conftest import (
    SESSION,
    closed_trades,
    context,
    store,
    trade,
)
from tests.unit.services.read.evaluation.conftest import EDGE

SITE_EVIDENCED = {("site", "edges", "drift"): {**EDGE, "status": "evidenced"}}


def _nightly(backend: MemoryBackend, day: date, finished: datetime) -> None:
    record = RunRecord(f"nightly-{day}", "nightly", day, finished)
    ResultWriter(backend).save_run(record.finish(finished))


@pytest.mark.parametrize(
    ("wins", "losses", "state"),
    [(12, 8, "on_track"), (4, 16, "below"), (19, 1, "above"), (3, 2, "too_early")],
)
def test_a_followed_edges_state_is_its_live_records(
    backend: MemoryBackend, wins: int, losses: int, state: str
) -> None:
    store(backend, closed_trades(wins, losses))
    desk = load_edge_desk(context(backend))
    (live,) = desk.live_states
    assert live.state == state == desk.followed[0].record.state
    assert (live.closed, live.wins, live.followed) == (wins + losses, wins, True)
    assert live.term == TERM and live.state in LIVE_STATES


def test_an_edge_with_no_paper_trades_has_no_live_record(backend: MemoryBackend) -> None:
    (live,) = load_edge_desk(context(backend)).live_states
    assert (live.state, live.closed, live.win_rate) == ("no_trades", 0, None)


def test_a_site_edge_nobody_follows_is_judged_but_a_candidate_is_not_recorded(
    backend: MemoryBackend,
) -> None:
    store(backend, closed_trades(4, 16))
    unfollowed = load_edge_desk(context(backend, follow=None, extra=SITE_EVIDENCED))
    assert unfollowed.followed == ()
    assert [(s.edge_id, s.state, s.followed) for s in unfollowed.live_states] == [
        ("drift", "below", False)
    ]
    assert load_edge_desk(context(backend, follow=None)).live_states == ()  # a candidate


def test_a_settlement_a_later_night_recorded_is_not_in_a_finished_sessions_state(
    backend: MemoryBackend,
) -> None:
    """The rows were rewritten as won on Oct 8, three days after the session completed."""
    opened = [trade(t["instrument_id"], t["signal_session"], "open", sell=SESSION)
              for t in closed_trades(12, 8)]  # fmt: skip
    store(backend, opened, datetime(2026, 10, 3, tzinfo=UTC))
    store(backend, closed_trades(12, 8), datetime(2026, 10, 8, 1, tzinfo=UTC))
    assert load_edge_desk(context(backend)).live_states[0].closed == 20  # no cutoff: all known
    _nightly(backend, SESSION, datetime(2026, 10, 5, 22, tzinfo=UTC))
    (live,) = load_edge_desk(context(backend)).live_states
    assert (live.state, live.closed) == ("too_early", 0)  # as the finished session knew them


def test_a_row_known_by_the_cutoff_is_read(backend: MemoryBackend) -> None:
    store(backend, closed_trades(12, 8), datetime(2026, 10, 5, 21, tzinfo=UTC))
    _nightly(backend, SESSION, datetime(2026, 10, 5, 22, tzinfo=UTC))
    assert load_edge_desk(context(backend)).live_states[0].closed == 20


def _as_site(backend: MemoryBackend) -> ReadContext:
    me = context(backend, extra=SITE_EVIDENCED)
    stores = open_stores(StoreReader(backend), me.configs, UserContext(SITE_USER))
    return ReadContext(
        stores.reader, stores.configs, stores.user, me.session, stores.features, stores.cache
    )


def test_below_range_names_only_the_record_owners_edges(backend: MemoryBackend) -> None:
    store(backend, closed_trades(4, 16))
    assert [s.edge_id for s in below_range(_as_site(backend))] == ["drift"]
    # a follower's night would repeat the site's line: the site's job says it once
    assert below_range(context(backend, extra=SITE_EVIDENCED)) == ()


def test_below_range_is_empty_while_the_edge_is_on_track(backend: MemoryBackend) -> None:
    store(backend, closed_trades(12, 8))
    assert below_range(_as_site(backend)) == ()
