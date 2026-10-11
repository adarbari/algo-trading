"""``Edge.costs`` and ``Edge.capacity`` serve the read model's figures and states as they are
(ADR 0064 decision 5): the break-even, the cost-invariant decile spread and the state that says
why a figure is missing (never a zero)."""

from algotrade.services.read.edge_evidence import capacity, costs
from algotrade_api.graphql.schema import schema
from algotrade_api.graphql.types.evaluation.edge_costs import EdgeCapacity, EdgeCosts


def test_costs_serve_the_levels_the_break_even_and_the_states() -> None:
    level = costs.CostLevel("all", 15.0, False, 40, 200, 0.55, 0.5, 5.0, 0.011)
    period = costs.CostPeriod("all", costs.MEASURED, 125.0, 0.04)
    hidden = costs.CostPeriod("out_of_sample", costs.OOS_HIDDEN, None, None)
    served = EdgeCosts.of(
        costs.EdgeCosts(costs.MEASURED, "momo", 20, 20.0, (level,), (period, hidden))
    )
    assert (served.state, served.variant, served.horizon, served.assumed_bp) == (
        "measured", "momo", 20, 20.0
    )  # fmt: skip
    assert (served.levels[0].bp, served.levels[0].lift_pts, served.levels[0].mean_excess) == (
        15.0, 5.0, 0.011
    )  # fmt: skip
    assert (served.periods[0].break_even_bp, served.periods[0].decile_spread) == (125.0, 0.04)
    assert served.periods[1].state == "oos_hidden" and served.periods[1].break_even_bp is None


def test_capacity_serves_unknown_as_null_not_zero() -> None:
    measured = capacity.CapacityPeriod("in_sample", capacity.MEASURED, 40, 8e6, 30, 4)
    unknown = capacity.CapacityPeriod("all", capacity.NOT_STORED, None, None, None, None)
    served = EdgeCapacity.of(
        capacity.EdgeCapacity(capacity.MEASURED, "momo", 20, 5e6, (measured, unknown))
    )
    assert served.floor_usd == 5e6 and served.periods[0].adv_low == 4
    assert served.periods[1].adv_median is None and served.periods[1].adv_known is None


def test_the_schema_has_both_sections_on_the_edge_with_an_optional_basis() -> None:
    sdl = schema.as_str()
    block = sdl[sdl.index("type Edge {") :].split("\n}")[0]
    assert "costs(variant: String = null, horizon: Int = null): EdgeCosts!" in block
    assert "capacity(variant: String = null, horizon: Int = null): EdgeCapacity!" in block
