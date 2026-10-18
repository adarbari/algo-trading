"""The turnover pass of a buy/hold band, by hand: a name held through the band is charged once
(half a round trip in, half out), entries and exits are the only cost, the pass is deterministic
and leaves the gross figures alone, and the net series and the break-even follow it."""

from dataclasses import replace
from datetime import date

import pytest

from algotrade.quant.edges.statistics import break_even_cost
from algotrade.services.evaluation.cross_section.measures import (
    UNCOUNTED_BAND,
    CostGrid,
    Pick,
    SessionStat,
    cost_measures,
    edge_slices,
    slice_measures,
)
from algotrade.services.evaluation.cross_section.reporting.turnover import (
    apply_hold_bands,
    apply_rebalances,
)

COST = 20.0  # bp per round trip; the legs' values are net of one of them (0.002)
D1, D2, D3 = date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3)


def top(*named: tuple[str, float]) -> tuple[tuple[Pick, ...], tuple[float, ...]]:
    """Counted picks (``(id, net value)``, ranks from 1) and their ``pick_values``."""
    picks = tuple(Pick(i, r, "", v) for r, (i, v) in enumerate(named, start=1))
    return picks, tuple(v for _, v in named)


def band(first: int, *named: tuple[str, float | None]) -> tuple[Pick, ...]:
    return tuple(
        Pick(i, r, "" if v is not None else UNCOUNTED_BAND, v)
        for r, (i, v) in enumerate(named, start=first)
    )


def session(
    day: date, picks: tuple[tuple[str, float], ...], below: tuple[Pick, ...]
) -> SessionStat:
    found, values = top(*picks)
    return SessionStat(
        session=day, regime="CALM", pick_values=values, pick_hits=len(values), picks=found,
        band=below,
    )  # fmt: skip


# Net values are gross - 0.002. top_k 2, hold_rank 4.
#   D1  top A (g .05) B (g .02)       band C (g .01)
#   D2  top A (g .03) C (g .00)       band B (g .002), D (g .05)   -> B held through, D never held
#   D3  top D (g .04) E (g .01)       band A (g .02), B (g .002)   -> A, B held; C is out
S1 = session(D1, (("A", 0.048), ("B", 0.018)), band(3, ("C", 0.008)))
S2 = session(D2, (("A", 0.028), ("C", -0.002)), band(3, ("B", 0.0), ("D", 0.048)))
S3 = session(D3, (("D", 0.038), ("E", 0.008)), band(3, ("A", 0.018), ("B", 0.0)))


def test_a_name_held_through_the_band_is_charged_once_not_every_session() -> None:
    one, two, three = apply_hold_bands([S1, S2, S3], COST)
    # D1: A and B enter (half a trip each), both held on: 1 trip, values gain the half not paid
    assert one.round_trips == pytest.approx(1.0)
    assert one.banded_values == pytest.approx((0.048 + 0.001, 0.018 + 0.001))
    # D2: A held through (0), C enters and leaves (1), B held through from the band (0); the band's
    # D is not held (it was not held at D1), so it pays nothing and is not in the book
    assert two.banded_values == pytest.approx((0.028 + 0.002, -0.002, 0.0 + 0.002))
    assert two.round_trips == pytest.approx(1.0)
    # D3 (the last: every name exits): D and E a whole trip, A and B (held in) half
    assert three.banded_values == pytest.approx((0.038, 0.008, 0.018 + 0.001, 0.0 + 0.001))
    assert three.round_trips == pytest.approx(3.0)


def test_the_cost_is_the_entries_and_exits_of_the_book_by_hand() -> None:
    stats = apply_hold_bands([S1, S2, S3], COST)
    positions = ["A", "B", "C", "D", "E"]  # each entered once and left once: 5 round trips
    assert sum(s.round_trips or 0.0 for s in stats) == pytest.approx(len(positions))
    names = sum(len(s.net_values) for s in stats)
    assert names == 2 + 3 + 4
    gross = 0.05 + 0.02 + 0.03 + 0.00 + 0.002 + 0.04 + 0.01 + 0.02 + 0.002
    net = sum(sum(s.net_values) for s in stats)
    assert net == pytest.approx(gross - len(positions) * COST / 1e4)  # 5 trips, not 9 or 12


def test_a_band_that_holds_nothing_charges_every_pick_a_full_round_trip() -> None:
    plain = [replace(S1, band=()), replace(S2, band=()), replace(S3, band=())]
    # no name repeats at D1..D3 but A (top at D1 and D2): it is held through (half + half)
    one, two, three = apply_hold_bands(plain, COST)
    assert one.banded_values == pytest.approx((0.048 + 0.001, 0.018))
    assert two.banded_values == pytest.approx((0.028 + 0.001, -0.002))
    assert three.round_trips == pytest.approx(2.0)
    own = [session(D1, (("A", 0.01),), ()), session(D2, (("B", 0.02),), ())]
    for stat in apply_hold_bands(own, COST):
        assert stat.banded_values == stat.pick_values and stat.round_trips == 1.0


def test_a_band_name_with_no_counted_value_is_never_held() -> None:
    gap = replace(S2, band=band(3, ("B", None)))  # B had no outcome: it cannot be held through
    _, two, _ = apply_hold_bands([S1, gap, S3], COST)
    assert two.banded_values == pytest.approx((0.028 + 0.002, -0.002))
    one, _, _ = apply_hold_bands([S1, gap, S3], COST)
    assert one.banded_values == pytest.approx((0.048 + 0.001, 0.018))  # B leaves: a whole trip


def test_a_session_the_screen_did_not_measure_breaks_the_chain() -> None:
    hole = SessionStat(session=D2, regime="CALM", excluded_coverage=1)
    one, middle, three = apply_hold_bands([S1, hole, S3], COST)
    assert middle == hole  # not a measured session: nothing to charge
    assert one.round_trips == pytest.approx(2.0)  # A and B leave before the gap: a whole trip each
    assert three.round_trips == pytest.approx(2.0)  # only D and E: A and B were not held in


def test_the_pass_is_deterministic_and_keeps_the_order_it_was_given() -> None:
    forward = apply_hold_bands([S1, S2, S3], COST)
    shuffled = apply_hold_bands([S3, S1, S2], COST)
    assert shuffled == (forward[2], forward[0], forward[1])
    assert apply_hold_bands([S1, S2, S3], COST) == forward
    assert [s.session for s in forward] == [D1, D2, D3]


def test_the_orientation_and_a_missing_cost_leave_values_consistent() -> None:
    free = apply_hold_bands([S1, S2, S3], None)  # no document cost: nothing to charge or save
    assert free[0].banded_values == pytest.approx((0.048, 0.018))
    below = apply_hold_bands([S1, S2], COST, -1.0)  # an oriented value is sign * (gross - cost)
    assert below[0].banded_values == pytest.approx((0.048 - 0.001, 0.018 - 0.001))


def test_gross_figures_are_unchanged_and_the_net_series_and_break_even_follow_the_pass() -> None:
    counted = {"pick_hits_at": (2, 2, 2), "base_hits_at": (2, 2, 2)}  # hits at each grid level
    stats = [replace(s, **counted) for s in (S1, S2, S3)]
    banded = apply_hold_bands(stats, COST)
    flat = [replace(s, band=()) for s in stats]
    slices = [s for s in edge_slices(banded, None, False) if s.kind == "all"]
    (m,) = slice_measures(banded, slices)
    (f,) = slice_measures(flat, slices)
    # gross statistics: hits, rates, deciles are the legs' own
    assert (m.picks, m.hits, m.hit_rate, m.eligible) == (f.picks, f.hits, f.hit_rate, f.eligible)
    # the net series: 9 held name-periods, 5 round trips of cost
    assert m.mean_excess_picks == pytest.approx((0.164) / 9)
    grid = CostGrid(COST, (0.0, 20.0, 50.0))
    rows = {r.slice_value: r for r in cost_measures(banded, slices, [m], grid)}
    gross = 0.174 / 9
    for bp in (0.0, 20.0, 50.0):  # exact: the cost is linear in the mean with 5 / 9 trips of it
        assert rows[f"all:{bp:g}"].mean_excess_picks == pytest.approx(gross - 5 / 9 * bp / 1e4)
    assert break_even_cost(rows["all:0"].mean_excess_picks, 0.0, 1.0, 5 / 9) == pytest.approx(
        gross * 1e4 * 9 / 5
    )
    # without a band every name pays a whole round trip: the older, steeper line
    flat_rows = {r.slice_value: r for r in cost_measures(flat, slices, [f], grid)}
    slope = flat_rows["all:0"].mean_excess_picks - flat_rows["all:50"].mean_excess_picks  # type: ignore[operator]
    assert slope == pytest.approx(50 / 1e4)


# portfolio_return books (ADR 0074): the weight change is the only cost
def book(day: date, gross: float, **weights: float) -> SessionStat:
    """A session whose leg value is net of one full round trip, as every leg stores it."""
    net = gross - COST / 1e4
    return SessionStat(
        session=day, regime="CALM", pick_values=(net,), pick_hits=int(net > 0),
        weights=tuple(weights.items()),
    )  # fmt: skip


def test_a_book_that_holds_still_pays_only_its_entry_and_its_last_exit() -> None:
    still = [book(d, 0.01, A=0.5, B=0.5) for d in (D1, D2, D3)]
    one, two, three = apply_rebalances(still, COST)
    assert (one.round_trips, two.round_trips, three.round_trips) == pytest.approx((0.5, 0.0, 0.5))
    # gross 1% less the cost paid: the entry's half at D1, nothing at D2, the exit's half at D3
    assert one.net_values == pytest.approx((0.01 - 0.5 * COST / 1e4,))
    assert two.net_values == pytest.approx((0.01,))
    assert three.net_values == pytest.approx((0.01 - 0.5 * COST / 1e4,))
    assert one.pick_values == still[0].pick_values  # the legs' gross figures stay as stored


def test_a_full_replacement_pays_one_round_trip_and_a_partial_one_its_weight_change() -> None:
    legs = [book(D1, 0.01, A=1.0), book(D2, 0.01, B=1.0), book(D3, 0.01, A=0.4, B=0.6)]
    one, two, three = apply_rebalances(legs, COST)
    # D2: A sold (1) and B bought (1): half of 2 trips-worth = 1.0; D3: |0.4-0| + |0.6-1| = 0.8
    assert (one.round_trips, two.round_trips, three.round_trips) == pytest.approx(
        (0.5, 1.0, 0.4 + 0.5)
    )
    total = sum(s.round_trips or 0.0 for s in (one, two, three))
    assert total == pytest.approx(2.4)


def test_cash_is_free_to_hold_and_to_leave() -> None:
    legs = [book(D1, 0.0, CASH=1.0), book(D2, 0.0, A=0.5, CASH=0.5), book(D3, 0.0, CASH=1.0)]
    one, two, three = apply_rebalances(legs, COST)
    assert (one.round_trips, two.round_trips, three.round_trips) == pytest.approx(
        (0.0, 0.25, 0.25)  # A's half is bought at D2 and sold at D3; cash trades nothing
    )
    assert one.net_values == pytest.approx((0.0,))  # a cash book pays nothing, not a full trip


def test_a_session_with_no_value_breaks_the_chain() -> None:
    gap = SessionStat(session=D2, regime="CALM", excluded_coverage=1, portfolio_reason="no_vol")
    one, skipped, three = apply_rebalances(
        [book(D1, 0.01, A=1.0), gap, book(D3, 0.01, A=1.0)], COST
    )
    assert one.round_trips == pytest.approx(1.0)  # bought at D1, sold before the gap
    assert skipped is gap
    assert three.round_trips == pytest.approx(1.0)  # bought afresh, sold at the end


def test_the_rebalance_pass_is_deterministic_whatever_the_order_given() -> None:
    legs = [book(D1, 0.01, A=1.0), book(D2, 0.02, B=1.0), book(D3, 0.03, A=1.0)]
    forward = apply_rebalances(legs, COST)
    shuffled = apply_rebalances([legs[2], legs[0], legs[1]], COST)
    assert [s.session for s in shuffled] == [D3, D1, D2]  # the order given, each its own figures
    assert {s.session: s.net_values for s in shuffled} == {s.session: s.net_values for s in forward}


def test_the_net_slice_follows_the_book_and_the_gross_hit_rate_does_not() -> None:
    legs = [book(d, 0.0025, A=1.0) for d in (D1, D2, D3)]  # 25 bp gross, 20 bp a full round trip
    sessions = apply_rebalances(legs, COST)
    measure = slice_measures(sessions, edge_slices(sessions, None, False))[0]
    assert measure.hit_rate == 1.0  # the legs' own: 5 bp is left after a full round trip each
    # D1 pays its entry's half, D2 nothing, D3 its exit's half: 20 bp over the three sessions
    assert measure.mean_excess_picks == pytest.approx((0.0025 * 3 - COST / 1e4) / 3)
    assert measure.base_rate is None and measure.lift is None  # the benchmark is the base
    assert (measure.sessions, measure.picks) == (3, 3)
