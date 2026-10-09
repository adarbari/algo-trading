"""``edge_signals``: tonight's paper picks are the harness's own, only at the sessions the
schedule fires from the state's ``since``, read at the signal session alone, and an edge or a
screen that cannot be traded says why instead of returning an empty record."""

from datetime import date

from algotrade.config.edges.loading import load_edges
from algotrade.core.time.calendar import next_session
from algotrade.services.evaluation.forward.signals import due, edge_signals, paper_traded
from tests.unit.services.evaluation.cross_section.conftest import DAYS, build_world
from tests.unit.services.evaluation.forward.conftest import USER, Desk, desk


def signals(d: Desk, day: date):  # type: ignore[no-untyped-def]
    (edge,) = load_edges(d.configs, "u1")
    return edge_signals(d.world.reader, d.configs, USER, edge, day)


def test_the_first_session_signals_the_top_names_best_first(following: Desk) -> None:
    found = signals(following, DAYS[0])
    assert found.skipped is None and found.screener == "momo" and found.horizon == 2
    assert [s.instrument_id for s in found.signals] == [
        f"EQ:N{i:02d}" for i in (19, 18, 17, 16, 15)
    ]
    assert [s.rank for s in found.signals] == [1, 2, 3, 4, 5]
    buy = next_session(DAYS[0])
    assert {s.buy_session for s in found.signals} == {buy}
    assert {s.sell_session for s in found.signals} == {next_session(next_session(buy))}


def test_the_schedule_spaces_signals_a_horizon_apart_from_since(following: Desk) -> None:
    (edge,) = load_edges(following.configs, "u1")
    assert [d for d in DAYS if due(edge, d)] == DAYS[0::2]
    assert signals(following, DAYS[1]).signals == ()


def test_a_session_before_the_state_began_does_not_signal() -> None:
    d = desk(follow={"state": "following", "since": DAYS[3].isoformat()})
    assert signals(d, DAYS[2]).signals == ()
    assert len(signals(d, DAYS[3]).signals) == 5


def test_only_following_and_trial_edges_are_paper_traded() -> None:
    for state, expected in (("following", True), ("trial", True), ("retired", False)):
        d = desk(follow={"state": state, "since": DAYS[0].isoformat()})
        (edge,) = load_edges(d.configs, "u1")
        assert paper_traded(edge) is expected


def test_picks_read_nothing_after_the_signal_session(following: Desk) -> None:
    """Prices and outcomes after the session change; the picks do not (point in time)."""
    other = desk(
        build_world(price_of=lambda day, i: 100.0 + 10 * i if day <= DAYS[0] else 500.0 - 10 * i)
    )
    assert signals(following, DAYS[0]).signals == signals(other, DAYS[0]).signals


def test_an_event_schedule_is_skipped_with_the_reason() -> None:
    d = desk(schedule="on_event:ex_dividend")
    found = signals(d, DAYS[0])
    assert found.signals == () and "event schedule" in (found.skipped or "")


def test_an_outcome_that_needs_the_implied_vol_is_skipped_with_the_reason() -> None:
    d = desk(
        outcome={
            "kind": "hit_target", "horizon_sessions": [2], "benchmark": "SPY",
            "start_offset_sessions": 1, "measure": "realised_to_implied_vol",
            "direction": "below", "target": 1.0,
        }
    )  # fmt: skip
    assert "implied vol" in (signals(d, DAYS[0]).skipped or "")


def test_a_screen_with_no_features_for_the_session_is_skipped_not_empty() -> None:
    d = desk(build_world(no_features=[DAYS[0]]))
    found = signals(d, DAYS[0])
    assert found.signals == () and found.skipped is not None
