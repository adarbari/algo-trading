"""``grain_of`` and ``beside``: the outcome grain a scope is read from (the option trades, the
share paths of a shares position with an exit, the price windows) and the one other grain a
position baseline is valued on, so a run reads both."""

from types import SimpleNamespace
from typing import Any

from algotrade.data.outcomes import CHAIN, SHARE_PATH, STOCK
from algotrade.services.evaluation.cross_section.baselines.variant import (
    Variant,
    _Scope,
    beside,
    grain_of,
)
from tests.unit.services.evaluation.cross_section.conftest import TEMPLATES, edge

SHARE_EXIT = {
    "kind": "excess_return", "horizon_sessions": [5], "benchmark": "SPY",
    "start_offset_sessions": 1, "position": "long_shares", "exit": {"take_profit": 0.1},
}  # fmt: skip
OPTION = {
    "kind": "option_pnl", "horizon_sessions": [5], "benchmark": "none", "tenor_days": 30,
    "position": "short_put", "strike_delta": 0.25, "start_offset_sessions": 1,
}  # fmt: skip


def scope(**outcome: Any) -> _Scope:
    e = edge(outcome=outcome) if outcome else edge()
    return _Scope("main", e, e.universe, "iv", templates=TEMPLATES)  # type: ignore[arg-type]


def baseline(template: str) -> Variant:
    config: Any = SimpleNamespace(hash="h")
    return Variant(f"position:{template}", "baseline", config, position=template)


def test_an_outcome_is_on_the_grain_its_kind_and_exit_say() -> None:
    assert grain_of(scope()) == STOCK
    no_exit = {k: v for k, v in SHARE_EXIT.items() if k != "exit"}
    assert grain_of(scope(**no_exit)) == STOCK  # the exit is what moves a shares setup
    assert grain_of(scope(**SHARE_EXIT)) == SHARE_PATH
    assert grain_of(scope(**OPTION)) == CHAIN


def test_an_option_setups_stock_baseline_is_beside_it_on_the_price_grain() -> None:
    plans = [SimpleNamespace(scope=scope(**OPTION))]
    assert beside(plans, [baseline("long_shares")]) == STOCK
    assert beside(plans, [Variant("momo", "screener", None)]) is None  # type: ignore[arg-type]


def test_a_setup_valued_on_its_own_grain_has_nothing_beside_it() -> None:
    plans = [SimpleNamespace(scope=scope())]
    assert beside(plans, [baseline("long_shares")]) is None  # a stock baseline of a stock setup
    assert beside([], [baseline("long_shares")]) is None


def test_a_share_path_setups_stock_baseline_is_beside_it_on_the_price_grain() -> None:
    """The loader refuses a ``position:<shares>`` baseline beside an exit (it would value the picks
    at the fixed horizon); the run still reads the grain it is asked to, never the share path's."""
    plans = [SimpleNamespace(scope=scope(**SHARE_EXIT))]
    assert beside(plans, [baseline("long_shares")]) == STOCK
