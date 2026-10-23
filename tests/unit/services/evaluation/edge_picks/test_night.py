"""What a site edge takes at a session (ADR 0081): the harness's pick rule over the harness's own
screen and universe, and why a session has none."""

from algotrade.config.user import UserContext
from algotrade.services.evaluation.cross_section.harness import evaluate_edge
from algotrade.services.evaluation.edge_picks.night import (
    NOT_DECISION_DAY,
    PICKED,
    SKIPPED,
    UNJUDGED,
    Night,
    edge_night,
    fires,
)
from tests.unit.services.evaluation.cross_section.conftest import (
    AS_OF,
    DAYS,
    World,
    build_world,
    edge,
)

USER = UserContext("site")
# The screener ranks N19, N18, N17 ... (price 100 + 10 i); the edge takes common stocks, and N18
# is the ETF of the page's example (SPY): it takes the screener's second place and is not an
# eligible name of the edge.
NO_N18 = {"where": {"all": [{"field": "instrument.symbol", "op": "not_in", "value": ["N18"]}]}}


def night(w: World, day=DAYS[0]) -> Night:  # type: ignore[no-untyped-def]
    return Night(w.reader, w.configs, USER, day)


def ids(*numbers: int) -> tuple[str, ...]:
    return tuple(f"EQ:N{i:02d}" for i in numbers)


def test_the_stored_picks_are_the_harnesss_when_the_edge_universe_is_narrower_than_the_screener(
    world: World,
) -> None:
    narrow = edge(universe=NO_N18, top_k=5)
    (stored,) = edge_night(night(world), narrow)
    assert (stored.status, stored.pick_ids) == (PICKED, ids(19, 17, 16, 15, 14))  # N18 is not one
    harness = evaluate_edge(
        world.reader, world.results, world.configs, USER, narrow, *_range(), AS_OF
    )
    first = harness.results[0].stats[0]
    assert first.session == DAYS[0]
    assert (
        tuple(p.instrument_id for p in first.picks) == stored.pick_ids
    )  # the same names, best first
    assert [p.rank for p in first.picks] == [1, 2, 3, 4, 5]


def _range():  # type: ignore[no-untyped-def]
    return DAYS[0], DAYS[-1]


def test_without_a_narrower_universe_the_screeners_second_name_is_taken(world: World) -> None:
    (stored,) = edge_night(night(world), edge(top_k=3))
    assert stored.pick_ids == ids(19, 18, 17)


def test_no_top_k_takes_every_qualified_name_of_the_universe(world: World) -> None:
    (stored,) = edge_night(night(world), edge(universe=NO_N18, top_k="all"))
    assert len(stored.pick_ids) == 19 and "EQ:N18" not in stored.pick_ids


def test_a_month_end_edge_decides_on_the_last_session_of_the_month_only(world: World) -> None:
    monthly = edge(schedule="month_end", outcome={**_outcome(), "horizon_sessions": [2]})
    (early,) = edge_night(night(world, DAYS[2]), monthly)
    assert (early.status, early.pick_ids) == (NOT_DECISION_DAY, ())
    assert fires(monthly, DAYS[2]) is False


def _outcome() -> dict[str, object]:
    return {"kind": "excess_return", "benchmark": "SPY", "start_offset_sessions": 1}


def test_a_short_edge_is_unjudged_with_its_reason(world: World) -> None:
    short = edge(outcome={**_outcome(), "horizon_sessions": [2], "side": "short",
                          "borrow_bps_annual": 30})  # fmt: skip
    (stored,) = edge_night(night(world), short)
    assert stored.status == UNJUDGED and "short" in stored.reason and stored.pick_ids == ()


def test_a_session_with_no_features_is_skipped_with_the_reason_never_empty_picks() -> None:
    w = build_world(no_features=[DAYS[3]])
    (stored,) = edge_night(night(w, DAYS[3]), edge())
    assert stored.status == SKIPPED and stored.reason and stored.pick_ids == ()


def test_one_screen_serves_every_edge_that_lists_it(world: World) -> None:
    n = night(world)
    edge_night(n, edge(top_k=2))
    edge_night(n, edge(universe=NO_N18))
    assert len(n.runs) == 1
