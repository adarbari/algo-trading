"""What a site edge takes at a session (ADR 0081): the harness's pick rule over the harness's own
screen and universe, and why a session has none."""

from dataclasses import replace
from datetime import date, timedelta

from algotrade.config.user import UserContext
from algotrade.services.evaluation.cross_section.harness import evaluate_edge
from algotrade.services.evaluation.edge_picks.night import (
    GATE_CLOSED,
    NOT_DECISION_DAY,
    PICKED,
    SKIPPED,
    UNJUDGED,
    Night,
    edge_night,
    fires,
)
from algotrade.services.screening.regime import MARKET
from tests.helpers.stored_frames import stamped
from tests.unit.services.evaluation.cross_section.conftest import (
    AS_OF,
    DAYS,
    IDS,
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


def _liquid_world() -> World:
    """The small world with every name liquid but name 0 (below the short leg's volume floor)."""
    w = build_world()
    for day in (*DAYS, DAYS[-1] + timedelta(days=4)):
        rows = [
            {"instrument_id": i, "adv_usd_20d": 1e6 if k == 0 else 1e7} for k, i in enumerate(IDS)
        ]
        w.writer.write_table(
            "rollups/instrument/price_stats@v2", day, f"p-{day}", stamped(rows, day, f"p-{day}")
        )
    return w


def _sided(side: str):  # type: ignore[no-untyped-def]
    return edge(outcome={**_outcome(), "horizon_sessions": [2], "side": side,
                         "borrow_bps_annual": 30}, top_k=5)  # fmt: skip


def test_a_short_edge_stores_the_harnesss_short_leg_worst_first_with_its_sides() -> None:
    w, short = _liquid_world(), _sided("short")
    (stored,) = edge_night(night(w), short)
    assert stored.status == PICKED and stored.pick_ids == ids(1, 2, 3, 4, 5)  # N00 is illiquid
    assert stored.pick_sides == ("short",) * 5 and stored.pick_weights == ()
    harness = evaluate_edge(w.reader, w.results, w.configs, USER, short, *_range(), AS_OF)
    first = harness.results[0].stats[0]
    assert tuple(p.instrument_id for p in first.picks) == stored.pick_ids  # the one rule


def test_a_long_short_edge_stores_its_long_leg_then_its_short_leg() -> None:
    (stored,) = edge_night(night(_liquid_world()), _sided("long_short"))
    assert stored.status == PICKED
    assert stored.pick_ids == ids(19, 18, 17, 16, 15, 1, 2, 3, 4, 5)
    assert stored.pick_sides == ("long",) * 5 + ("short",) * 5


def test_a_short_edge_with_too_few_scores_is_skipped_as_the_harness_leaves_it_unmeasured(
    world: World,
) -> None:
    scoreless = Night(world.reader, world.configs, USER, DAYS[0])
    digest, run = scoreless.run("momo")
    assert not isinstance(run, str)
    scoreless.runs[digest] = replace(run, scores={})
    (stored,) = edge_night(scoreless, _sided("short"))
    assert stored.status == SKIPPED and "score" in stored.reason and stored.pick_ids == ()


def test_a_short_edge_with_no_stored_dollar_volume_is_skipped_never_an_empty_leg(
    world: World,
) -> None:
    (stored,) = edge_night(night(world), _sided("short"))  # no price_stats table at all
    assert stored.status == SKIPPED and "price_stats" in stored.reason
    assert stored.pick_ids == ()


def test_a_long_edge_stores_every_pick_as_long(world: World) -> None:
    (stored,) = edge_night(night(world), edge(top_k=3))
    assert stored.pick_sides == ("long",) * 3


def test_a_portfolio_edge_is_unjudged_until_its_book_is_replayed(world: World) -> None:
    book = edge(outcome={**_outcome(), "kind": "portfolio_return", "horizon_sessions": [1],
                         "weighting": "equal"}, top_k=5)  # fmt: skip
    (stored,) = edge_night(night(world), book)
    assert stored.status == UNJUDGED and "book" in stored.reason


def test_a_session_with_no_features_is_skipped_with_the_reason_never_empty_picks() -> None:
    w = build_world(no_features=[DAYS[3]])
    (stored,) = edge_night(night(w, DAYS[3]), edge())
    assert stored.status == SKIPPED and stored.reason and stored.pick_ids == ()


def test_one_screen_serves_every_edge_that_lists_it(world: World) -> None:
    n = night(world)
    edge_night(n, edge(top_k=2))
    edge_night(n, edge(universe=NO_N18))
    assert len(n.runs) == 1


def test_a_month_end_is_a_decision_day_whatever_the_horizon_and_the_month_before(
    world: World,
) -> None:
    for horizon in (2, 21, 60):
        monthly = edge(schedule="month_end", outcome={**_outcome(), "horizon_sessions": [horizon]})
        assert fires(monthly, date(2026, 2, 27)) and fires(monthly, date(2026, 1, 30))
        assert not fires(monthly, date(2026, 2, 26))


def test_a_closed_setup_gate_stores_gate_closed_with_the_gates_reason(world: World) -> None:
    row = {"instrument_id": MARKET, "label": "STRESS", "market_stress": 80.0}
    world.writer.write_table(
        "rollups/market/regime@v3", DAYS[0], "m1", stamped([row], DAYS[0], "m1")
    )
    gate = {"all": [{"field": "market.regime@v3.label", "op": "not_in", "value": ["STRESS"]}]}
    (stored,) = edge_night(night(world), edge(top_k=3, gate=gate))
    assert stored.status == GATE_CLOSED and stored.pick_ids == () and stored.reason


def test_a_gated_edge_with_no_market_row_is_skipped_unknown_never_picked(world: World) -> None:
    gate = {"all": [{"field": "market.regime@v3.label", "op": "not_in", "value": ["STRESS"]}]}
    (stored,) = edge_night(night(world), edge(top_k=3, gate=gate))
    assert stored.status == "skipped" and stored.pick_ids == ()
    assert stored.reason == "regime unknown"  # the gate applies with [regime] off, and fails closed
