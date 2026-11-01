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
from algotrade.services.read.session import session_cutoff
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.result_writer import ResultWriter
from tests.unit.services.read.edge_desk.conftest import (
    CANDIDATE,
    NEXT,
    NO_CUTOFF,
    SESSION,
    SITE_DRIFT,
    closed_trades,
    context,
    store,
    trade,
)
from tests.unit.services.read.evaluation.conftest import EDGE

SITE_EVIDENCED = {("site", "edges", "drift"): {**EDGE, "status": "evidenced"}}


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


def test_a_site_edge_nobody_follows_is_judged_and_so_is_a_candidate_but_a_draft_is_not_recorded(
    backend: MemoryBackend,
) -> None:
    store(backend, closed_trades(4, 16))
    unfollowed = load_edge_desk(context(backend, follow=None, extra=SITE_EVIDENCED))
    assert unfollowed.followed == ()
    assert [(s.edge_id, s.state, s.followed) for s in unfollowed.live_states] == [
        ("drift", "below", False)
    ]
    (candidate,) = load_edge_desk(context(backend, follow=None, extra=CANDIDATE)).live_states
    assert (candidate.state, candidate.closed, candidate.followed) == ("below", 20, False)
    draft = {SITE_DRIFT: {**EDGE, "status": "researching"}}
    (idle,) = load_edge_desk(context(backend, follow=None, extra=draft)).live_states
    assert (idle.state, idle.closed, idle.followed) == ("not_recording", 0, False)
    assert "not open" in idle.headline and idle.state in LIVE_STATES


def test_a_settlement_a_later_night_recorded_is_not_in_a_finished_sessions_state(
    backend: MemoryBackend,
) -> None:
    """The rows were rewritten as won on Oct 8, three days after the session completed."""
    opened = [trade(t["instrument_id"], t["signal_session"], "open", sell=SESSION)
              for t in closed_trades(12, 8)]  # fmt: skip
    store(backend, opened, datetime(2026, 10, 3, tzinfo=UTC))
    store(backend, closed_trades(12, 8), datetime(2026, 10, 8, 1, tzinfo=UTC))
    (live,) = load_edge_desk(context(backend)).live_states
    assert (live.state, live.closed) == ("too_early", 0)  # as the finished session knew them
    later = datetime(2026, 10, 9, tzinfo=UTC)
    assert load_edge_desk(context(backend, cutoff=later)).live_states[0].closed == 20


def test_a_row_known_by_the_cutoff_is_read(backend: MemoryBackend) -> None:
    store(backend, closed_trades(12, 8), datetime(2026, 10, 5, 21, tzinfo=UTC))
    assert load_edge_desk(context(backend)).live_states[0].closed == 20


def test_the_cutoff_also_bounds_the_desks_buys(backend: MemoryBackend) -> None:
    store(
        backend, [trade("EQ:A", SESSION, sell=date(2026, 11, 3))], datetime(2026, 10, 6, tzinfo=UTC)
    )
    assert load_edge_desk(context(backend)).buys == ()  # recorded after the session completed
    assert len(load_edge_desk(context(backend, cutoff=datetime(2026, 10, 7, tzinfo=UTC))).buys) == 1


def test_a_session_whose_nightly_has_not_completed_is_not_judged(backend: MemoryBackend) -> None:
    store(backend, closed_trades(4, 16))
    desk = load_edge_desk(context(backend, cutoff=NO_CUTOFF))
    (live,) = desk.live_states
    assert (live.state, live.closed, live.win_rate, live.low) == ("not_settled", 0, None, None)
    assert live.term == TERM and live.state in LIVE_STATES
    assert below_range(context(backend, cutoff=NO_CUTOFF)) == ()


def test_the_session_cutoff_is_the_first_completed_nightlys_finish(backend: MemoryBackend) -> None:
    started = datetime(2026, 10, 5, 1, tzinfo=UTC)
    writer = ResultWriter(backend)
    writer.save_run(RunRecord("nightly-run", "nightly", SESSION, started))  # still running
    for run, hour in (("b", 23), ("c", 21)):
        done = RunRecord(f"nightly-{run}", "nightly", SESSION, started)
        writer.save_run(done.finish(datetime(2026, 10, 5, hour, tzinfo=UTC)))
    other = RunRecord("nightly-d", "nightly", NEXT, datetime(2026, 10, 6, tzinfo=UTC))
    writer.save_run(other.finish(datetime(2026, 10, 6, 5, tzinfo=UTC)))
    records = StoreReader(backend).runs("nightly")
    assert session_cutoff(records, SESSION) == datetime(2026, 10, 5, 21, tzinfo=UTC)
    assert session_cutoff(records, date(2026, 10, 1)) is None


def _as_site(backend: MemoryBackend, extra: dict | None = None) -> ReadContext:  # type: ignore[type-arg]
    me = context(backend, extra=extra or SITE_EVIDENCED)
    stores = open_stores(StoreReader(backend), me.configs, UserContext(SITE_USER))
    return ReadContext(
        stores.reader, stores.configs, stores.user, me.session, stores.features, stores.cache
    )


def test_below_range_names_only_the_record_owners_edges(backend: MemoryBackend) -> None:
    store(backend, closed_trades(4, 16))
    assert [s.edge_id for s in below_range(_as_site(backend))] == ["drift"]
    # a follower's night would repeat the site's line: the site's job says it once
    assert below_range(context(backend, extra=SITE_EVIDENCED)) == ()


def test_below_range_names_no_candidate_whose_record_is_unproven(backend: MemoryBackend) -> None:
    store(backend, closed_trades(4, 16))
    assert below_range(_as_site(backend, extra=CANDIDATE)) == ()


def test_below_range_is_empty_while_the_edge_is_on_track(backend: MemoryBackend) -> None:
    store(backend, closed_trades(12, 8))
    assert below_range(_as_site(backend)) == ()


def test_a_followed_draft_reads_not_recording_a_follow_records_nothing(
    backend: MemoryBackend,
) -> None:
    store(backend, closed_trades(12, 8))
    draft = {SITE_DRIFT: {**EDGE, "status": "researching"}}
    desk = load_edge_desk(context(backend, extra=draft))  # followed, but a draft
    (live,) = desk.live_states
    assert (live.state, live.closed) == ("not_recording", 0)


def test_a_name_picked_from_data_the_viewer_has_no_licence_for_is_not_read_nor_counted(
    backend: MemoryBackend,
) -> None:
    """The licence recorded at the signal decides (ADR 0064 decision 10): a candidate's record
    over personal-licence data reads as no trades to a viewer who holds none, whole."""
    rows = [t | {"licence": "personal"} for t in closed_trades(12, 8)]
    store(backend, rows)
    (live,) = load_edge_desk(context(backend, extra=CANDIDATE)).live_states
    assert (live.state, live.closed) == ("no_trades", 0)


def test_a_name_picked_from_open_data_is_read_whole(backend: MemoryBackend) -> None:
    store(backend, [t | {"licence": "open"} for t in closed_trades(12, 8)])
    (live,) = load_edge_desk(context(backend, extra=CANDIDATE)).live_states
    assert live.closed == 20


def test_below_range_judges_a_record_whose_names_a_viewer_could_not_read(
    backend: MemoryBackend,
) -> None:
    """The nightly's line names an edge, never a name: the site user holds no licence, and a
    setup read from personal data is still named when its record is below the range."""
    store(backend, [t | {"licence": "personal"} for t in closed_trades(4, 16)])
    assert [s.edge_id for s in below_range(_as_site(backend))] == ["drift"]
