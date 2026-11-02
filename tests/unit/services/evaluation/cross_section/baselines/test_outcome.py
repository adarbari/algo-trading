"""``position_outcome``: the outcome a ``position:<template>`` baseline is valued with."""

import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.services.evaluation.cross_section.baselines.outcome import position_outcome
from tests.unit.services.evaluation.cross_section.conftest import TEMPLATES, edge

CHAIN = {
    "kind": "option_pnl", "horizon_sessions": [5], "benchmark": "none", "tenor_days": 30,
    "position": "covered_call", "strike_delta": 0.25, "start_offset_sessions": 1,
    "exit": {"take_profit": 0.5},
}  # fmt: skip


def test_shares_are_the_stock_alone_over_the_same_window_without_the_benchmark() -> None:
    o = position_outcome(edge(outcome=CHAIN).outcome, "long_shares", TEMPLATES)
    assert (o.kind, o.side, o.benchmark, o.position, o.tenor_days) == (
        "excess_return",
        "long",
        "none",
        None,
        None,
    )
    assert (o.horizon_sessions, o.start_offset_sessions) == ((5,), 1)


def test_shares_of_a_setup_with_a_benchmark_keep_it() -> None:
    assert position_outcome(edge().outcome, "long_shares", TEMPLATES).benchmark == "SPY"


def test_the_picks_are_the_setups_own_so_they_are_held_as_its_own_sides_shares() -> None:
    with pytest.raises(ConfigurationError, match="that side's shares only"):
        position_outcome(edge().outcome, "short_shares", TEMPLATES)


def test_an_option_template_keeps_the_setups_entry_and_drops_its_exits() -> None:
    o = position_outcome(edge(outcome=CHAIN).outcome, "short_put", TEMPLATES)
    assert o.kind == "option_pnl" and o.position is not None
    assert (o.position.template, o.position.exit, o.tenor_days) == ("short_put", None, 30)
    assert o.position.collateral == TEMPLATES["short_put"].collateral and o.position.legs


def test_an_option_template_needs_an_option_setup() -> None:
    with pytest.raises(ConfigurationError, match="option_pnl setup only"):
        position_outcome(edge().outcome, "short_put", TEMPLATES)
