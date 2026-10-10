"""``edge_signals``: tonight's paper picks are the harness's own, only at the sessions the
schedule fires from the state's ``since``, read at the signal session alone, and an edge or a
screen that cannot be traded says why instead of returning an empty record."""

from datetime import date

from algotrade.config.edges.loading import load_edges
from algotrade.core.time.calendar import next_session
from algotrade.services.evaluation.cross_section.sessions import leg_blocks
from algotrade.services.evaluation.forward.signals import edge_signals, legs_between, paper_traded
from tests.unit.services.evaluation.cross_section.conftest import DAYS, build_world
from tests.unit.services.evaluation.cross_section.test_harness import (
    EVENTS,
    OTM_OUTCOME,
    otm_world,
)
from tests.unit.services.evaluation.forward.conftest import (
    USER,
    Desk,
    desk,
    event_changes,
    event_world,
)


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
    legs, _ = legs_between(following.world.reader, following.configs, USER, edge, DAYS[0], DAYS[-1])
    assert [leg.decision for leg in legs] == DAYS[0::2]
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


def test_an_event_schedule_signals_the_event_names_at_the_session_they_fire() -> None:
    w = event_world({DAYS[0]: [10, 11], DAYS[1]: [12, 10], DAYS[4]: [13]})
    d = desk(w, **event_changes(2))
    found = signals(d, DAYS[0])
    assert found.skipped is None
    assert [s.instrument_id for s in found.signals] == ["EQ:N11", "EQ:N10"]  # best first
    assert {s.buy_session for s in found.signals} == {next_session(DAYS[0])}  # S = D + 1
    assert {s.sell_session for s in found.signals} == {DAYS[3]}
    # N10 is counted once per name and quarter (the harness's dedupe): only N12 on the next day.
    assert [s.instrument_id for s in signals(d, DAYS[1]).signals] == ["EQ:N12"]
    quiet = signals(d, DAYS[2])
    assert quiet.signals == () and quiet.skipped is None and quiet.screener is None  # not due


def test_an_event_schedule_does_not_signal_before_the_state_began() -> None:
    w = event_world({DAYS[0]: [10], DAYS[1]: [12]})
    d = desk(w, follow={"state": "following", "since": DAYS[1].isoformat()}, **event_changes(2))
    assert signals(d, DAYS[0]).signals == ()
    assert [s.instrument_id for s in signals(d, DAYS[1]).signals] == ["EQ:N12"]


def test_the_legs_of_the_paper_record_are_the_harnesss_own() -> None:
    w = event_world(EVENTS)
    d = desk(w, **event_changes(2))
    (edge,) = load_edges(d.configs, "u1")
    legs, events = legs_between(w.reader, d.configs, USER, edge, DAYS[0], DAYS[-1])
    harness_legs = [leg for block in leg_blocks(edge, events, DAYS, 2) for leg in block]
    assert legs == harness_legs and [leg.decision for leg in legs] == [DAYS[1], DAYS[2], DAYS[5]]
    assert [leg.entry for leg in legs] == [next_session(leg.decision) for leg in legs]


def test_an_outcome_that_reads_the_implied_vol_is_traded_not_skipped() -> None:
    d = desk(otm_world(), outcome=OTM_OUTCOME)
    found = signals(d, DAYS[0])
    assert found.skipped is None and len(found.signals) == 5


def test_a_mixed_source_implied_vol_field_is_skipped_with_the_reason() -> None:
    d = desk(outcome={**OTM_OUTCOME, "iv_field": "feature.vrp_iv30"})
    assert "mixes sources" in (signals(d, DAYS[0]).skipped or "")


def test_a_screen_with_no_features_for_the_session_is_skipped_not_empty() -> None:
    d = desk(build_world(no_features=[DAYS[0]]))
    found = signals(d, DAYS[0])
    assert found.signals == () and found.skipped is not None
