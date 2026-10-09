"""An edge's live record: judged against the backtest's usual range (a binomial band over the
closed trades), open and skipped counted apart, the sentences the server's, and a trial's forward
test beside the edge it replaces."""

from datetime import date, timedelta
from itertools import pairwise

import pytest

from algotrade.config.edges.document import QUALITY_BAR
from algotrade.quant.edge_statistics import win_rate_band
from algotrade.services.read.edge_desk.live import (
    ABOVE,
    BELOW,
    NO_BACKTEST,
    NO_TRADES,
    ON_TRACK,
    TOO_EARLY,
    load_edge_paper,
)
from algotrade.storage.backends.memory import MemoryBackend
from tests.unit.services.read.edge_desk.conftest import (
    SESSION,
    closed_trades,
    context,
    store,
    trade,
)
from tests.unit.services.read.evaluation.conftest import FROZEN, write_run


def paper(backend: MemoryBackend, **kwargs):  # type: ignore[no-untyped-def]
    found = load_edge_paper(context(backend, **kwargs), "drift")
    assert found is not None
    return found


@pytest.mark.parametrize(
    ("wins", "losses", "state"),
    [(12, 8, ON_TRACK), (4, 16, BELOW), (19, 1, ABOVE)],
)
def test_the_live_rate_is_judged_against_the_backtests_usual_range(
    backend: MemoryBackend, wins: int, losses: int, state: str
) -> None:
    store(backend, closed_trades(wins, losses))
    record = paper(backend).record
    low, high = win_rate_band(0.6, 20) or (0.0, 0.0)
    assert (record.state, record.closed, record.wins) == (state, 20, wins)
    assert (record.low, record.high) == (low, high) and record.backtest_rate == 0.6
    assert record.basis == "out-of-sample win rate"
    assert str(round(low * 100)) + "%" in record.headline


def test_the_boundaries_of_the_range_are_inside_it(backend: MemoryBackend) -> None:
    low, high = win_rate_band(0.6, 20) or (0.0, 0.0)
    for wins in (round(low * 20), round(high * 20)):
        store(backend, closed_trades(wins, 20 - wins))
        assert paper(backend).record.state == ON_TRACK
        backend.__init__()  # type: ignore[misc]
        write_run(backend, "site1", FROZEN, 0.6)


def test_the_picture_is_the_binomial_distribution_and_sums_to_one(backend: MemoryBackend) -> None:
    store(backend, closed_trades(12, 8))
    bins = paper(backend).record.bins
    assert 1 <= len(bins) <= 20 and sum(b.chance for b in bins) == pytest.approx(1.0)
    assert bins[0].start == 0.0 and bins[-1].end == 1.0
    assert all(a.end <= b.start + 1e-12 for a, b in pairwise(bins))


def test_too_few_closed_trades_is_too_early_and_says_when_it_will_be_judged(
    backend: MemoryBackend,
) -> None:
    store(
        backend,
        [
            *closed_trades(5, 3),
            trade("EQ:O", SESSION),
            trade("EQ:K", date(2026, 9, 3), "skipped", sell=date(2026, 10, 2), rank=2),
        ],
    )
    record = paper(backend).record
    assert (record.state, record.closed, record.open, record.skipped) == (TOO_EARLY, 8, 1, 1)
    assert record.bins == () and record.low is None
    assert record.headline.startswith(
        "5 of 8 closed trades won; judged once 10 signal sessions have closed."
    )
    assert "1 open, 1 skipped" in record.headline


def test_no_trades_says_so_and_no_run_means_no_backtest() -> None:
    empty = MemoryBackend()
    write_run(empty, "site1", FROZEN, 0.6)
    store(empty, [trade("EQ:X", date(2026, 7, 1), user="someone else")])
    assert paper(empty).record.state == NO_TRADES
    bare = MemoryBackend()  # no run at all
    store(bare, closed_trades(12, 8))
    record = paper(bare).record
    assert (record.state, record.backtest_rate) == (NO_BACKTEST, None)
    assert "no backtest" in record.headline


def test_a_run_committed_after_the_session_is_not_known_by_it(backend: MemoryBackend) -> None:
    store(backend, closed_trades(12, 8, sell=date(2026, 9, 30)))
    early = context(backend, day=date(2026, 10, 1))  # the run committed on Oct 2
    found = load_edge_paper(early, "drift")
    assert found is not None and found.record.state == NO_BACKTEST


def test_the_trades_are_newest_signal_first_and_an_unknown_edge_is_none(
    backend: MemoryBackend,
) -> None:
    store(backend, closed_trades(3, 0))
    assert [t.signal_session for t in paper(backend).trades] == sorted(
        (t.signal_session for t in paper(backend).trades), reverse=True
    )
    assert load_edge_paper(context(backend), "nope") is None


TRIAL = {("me", "edges", "drift2"): {
    "id": "drift2", "name": "Drift v2", "thesis": "Names keep rising.", "mechanism": "m",
    "persistence": "p",
    "schedule": "every_session", "universe": "active", "top_k": 5, "screeners": ["momo"],
    "status": "candidate", "sources": [{"title": "A"}],
    "outcome": {"kind": "excess_return", "horizon_sessions": [20], "benchmark": "SPY",
                "start_offset_sessions": 1},
    "quality_bar": dict.fromkeys(QUALITY_BAR, "An answer."),
    "follow": {"state": "trial", "since": date(2026, 9, 1), "replaces": "drift"},
}}  # fmt: skip


def two_edges(backend: MemoryBackend, v2_wins: int, v1_wins: int, day: date = SESSION):  # type: ignore[no-untyped-def]
    v2 = [t | {"edge_id": "drift2"} for t in closed_trades(v2_wins, 10 - v2_wins)]
    v1 = closed_trades(v1_wins, 10 - v1_wins)
    store(backend, v1 + v2)
    found = load_edge_paper(context(backend, day=day, extra=TRIAL), "drift2")
    assert found is not None
    return found


def test_a_trial_carries_its_forward_test_against_the_edge_it_replaces(
    backend: MemoryBackend,
) -> None:
    forward = two_edges(backend, v2_wins=7, v1_wins=5).forward
    assert forward is not None and forward.replaces == "drift" and forward.replaces_name == "Drift"
    assert (forward.this.wins, forward.replaced.wins) == (7, 5)
    assert forward.needed == 20 and forward.sessions >= 20 and forward.can_replace
    assert forward.headline == "It can replace the edge."


def test_a_trial_behind_the_edge_or_too_young_cannot_replace_it(backend: MemoryBackend) -> None:
    behind = two_edges(backend, v2_wins=4, v1_wins=7).forward
    assert behind is not None and not behind.can_replace
    assert behind.headline == "Its win rate is behind the edge it would replace."
    young = MemoryBackend()
    write_run(young, "site1", FROZEN, 0.6)
    too_young = two_edges(young, 7, 5, day=date(2026, 9, 15)).forward
    assert too_young is not None and not too_young.can_replace
    assert too_young.headline.endswith("sessions of the forward test have passed.")


def test_an_edge_that_is_not_a_trial_has_no_forward_test(backend: MemoryBackend) -> None:
    store(backend, closed_trades(12, 8))
    assert paper(backend).forward is None


def test_the_picks_of_one_night_count_once_the_sessions_are_the_independent_units(
    backend: MemoryBackend,
) -> None:
    # 36 closed trades but only 4 signal sessions: too few independent sessions to judge
    few = [
        trade(
            f"EQ:{d}-{i}",
            date(2026, 9, 2 + d),
            "won" if i < 3 else "lost",
            sell=date(2026, 10, 2),
            rank=i + 1,
        )
        for d in range(4)
        for i in range(5)
    ]
    store(backend, few)
    record = paper(backend).record
    assert (record.state, record.closed) == (TOO_EARLY, 20)
    assert "10 signal sessions" in record.headline


def test_the_band_is_taken_over_signal_sessions_not_trades() -> None:
    backend = MemoryBackend()
    write_run(backend, "site1", FROZEN, 0.6)
    days = [
        date(2026, 9, 1) + timedelta(days=n)
        for n in range(0, 14)
        if (date(2026, 9, 1) + timedelta(days=n)).weekday() < 5
    ]
    rows = [
        trade(f"EQ:{d}-{i}", d, "won" if i < 3 else "lost", sell=date(2026, 10, 2), rank=i + 1)
        for d in days
        for i in range(5)
    ]
    store(backend, rows)
    record = paper(backend).record
    sessions = len(days)
    assert record.closed == 5 * sessions and (record.low, record.high) == win_rate_band(
        0.6, sessions
    )
