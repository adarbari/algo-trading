"""The option cost levels (ADR 0088, E6b-2) by hand: a one-leg put with half-spreads 0.10 / 0.05,
collateral 100 and a mid P&L of 1.00 pays nothing at ``mid``, 0.75 of the spreads and the
commission at ``effective`` and all of them at ``full``; at expiry there is no closing fee."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from algotrade.config.edges.verdict import OPTION_LEVELS, OptionCosts
from algotrade.services.evaluation.cross_section.hit import (
    apply_outcome,
    level_outcomes,
    level_values,
)
from algotrade.services.evaluation.evidence import values
from algotrade.services.evaluation.evidence.shapes import roc_moments, trade_frame
from tests.unit.services.evaluation.cross_section.conftest import edge
from tests.unit.services.evaluation.evidence.test_shapes import CHAIN, DAY, EXIT, _option_rows

COSTS = OptionCosts()  # commission 0.65 per contract and side; shares 1: 0.75, 2: 0.65, 4: 0.53


def _put(**changes: object) -> pd.DataFrame:
    """Three one-leg put trades: spreads 0.10 / 0.05, collateral 100, pnl_mid 1.00, spot 100."""
    one = {
        "leg_kinds": [["option"]], "leg_qty": [[1.0]], "entry_half_spread": 0.10,
        "exit_half_spread": 0.05, "collateral": 100.0, "pnl_mid": 1.0, "exit_basis": "QUOTE",
        **changes,
    }  # fmt: skip
    rows = _option_rows(**{k: v for k, v in one.items() if not isinstance(v, list)})
    for name in ("leg_kinds", "leg_qty"):
        rows[name] = pd.Series([one[name][0]] * len(rows), dtype=object)
    return rows


def _roc(frame: pd.DataFrame) -> np.ndarray:
    e = edge(outcome=CHAIN)
    return trade_frame(
        e, frame, apply_outcome(e, frame, option_costs=COSTS), entry=DAY, bars_exit=EXIT,
        side="long", option_costs=COSTS,
    )["return_on_capital"].to_numpy(dtype=float)  # fmt: skip


def test_the_return_on_capital_at_each_level_by_hand() -> None:
    rows = _put()
    mid, effective, full = (_roc(values.at_level(rows, n, COSTS))[0] for n in OPTION_LEVELS)
    assert mid == pytest.approx(0.0100)
    assert effective == pytest.approx((1.00 - 0.75 * 0.15 - 0.0065 * 2) / 100)
    assert full == pytest.approx((1.00 - 0.15 - 0.013) / 100)
    assert mid > effective > full


def test_the_main_level_is_full_with_the_commission_and_without_costs_there_is_none() -> None:
    rows = _put()
    assert _roc(rows)[0] == pytest.approx((1.00 - 0.15 - 0.013) / 100)  # option_costs: full
    e = edge(outcome=CHAIN)
    bare = trade_frame(e, rows, apply_outcome(e, rows), entry=DAY, bars_exit=EXIT, side="long")
    assert bare["return_on_capital"].iloc[0] == pytest.approx((1.00 - 0.15) / 100)


def test_the_value_pays_the_commission_over_the_entry_spot() -> None:
    e = edge(outcome=CHAIN)
    frame = apply_outcome(e, _put(), option_costs=COSTS)
    assert frame["value"].iloc[0] == pytest.approx((1.00 - 0.15 - 0.013) / 100)  # spot 100
    plain = apply_outcome(e, _put())
    assert plain["value"].iloc[0] == pytest.approx((1.00 - 0.15) / 100)


def test_the_value_at_a_level_equals_the_return_on_capital_scaled_by_the_spot() -> None:
    e, rows = edge(outcome=CHAIN), _put(collateral=100.0)
    levels = level_outcomes(e, rows, OPTION_LEVELS, COSTS)
    got = [float(f["value"].iloc[0]) for f in levels]  # spot 100: the P&L over the spot
    want = [1.00, 1.00 - 0.75 * 0.15 - 0.013, 1.00 - 0.15 - 0.013]
    assert got == pytest.approx([w / 100 for w in want])


def test_an_expired_trade_pays_no_closing_commission() -> None:
    rows = _put(exit_basis="INTRINSIC", exit_half_spread=0.0)
    assert _roc(values.at_level(rows, "full", COSTS))[0] == pytest.approx(
        (1.00 - 0.10 - 0.0065) / 100
    )
    fee = values.commission_per_unit(rows, COSTS)
    assert fee[0] == pytest.approx(0.0065)


def test_the_commission_is_per_option_leg_contract_and_ignores_a_share_leg() -> None:
    rows = _put(leg_kinds=[["option", "option", "shares"]], leg_qty=[[1.0, -2.0, 0.5]])
    assert values.commission_per_unit(rows, COSTS)[0] == pytest.approx(0.65 * 3 / 100 * 2)
    assert values.commission_per_unit(rows, replace(COSTS, commission_usd=0.0))[0] == 0.0


def test_the_effective_share_follows_the_leg_count() -> None:
    assert [values.share_by_legs(COSTS, n) for n in (1, 2, 3, 4, 6)] == [
        0.75,
        0.65,
        0.65,
        0.53,
        0.53,
    ]
    rows = _put(leg_kinds=[["option"] * 2], leg_qty=[[1.0, -1.0]])
    at = values.at_level(rows, "effective", COSTS)
    assert at["entry_half_spread"].iloc[0] == pytest.approx(0.10 * 0.65)
    assert at["exit_half_spread"].iloc[0] == pytest.approx(0.05 * 0.65)
    assert at is not rows and rows["entry_half_spread"].iloc[0] == 0.10  # a copy


def test_unknown_legs_are_unknown_at_every_level_never_zero() -> None:
    rows = _put().drop(columns=["leg_kinds", "leg_qty"])
    for name in OPTION_LEVELS:
        assert np.isnan(values.at_level(rows, name, COSTS)[values.COMMISSION]).all()
    e = edge(outcome=CHAIN)
    assert apply_outcome(e, rows, option_costs=COSTS)["excluded"].iloc[0] == "missing_value"


def test_a_level_counts_the_same_names_and_orders_the_values() -> None:
    e, rows = edge(outcome=CHAIN), _put()
    rows.loc[1, "pnl_mid"] = np.nan
    frames = [f.set_index("instrument_id") for f in level_outcomes(e, rows, OPTION_LEVELS, COSTS)]
    assert len({tuple(f["excluded"]) for f in frames}) == 1
    name = frames[0].index[0]
    mid, eff, full = level_values(frames, name) or (0, 0, 0)
    assert mid > eff > full
    assert level_values(frames, frames[0].index[1]) is None  # no value: never 0
    assert level_values([], name) is None


def test_an_unknown_level_is_refused() -> None:
    with pytest.raises(ValueError, match="option cost level"):
        values.at_level(_put(), "half", COSTS)


def test_the_base_return_on_capital_is_the_mean_over_the_counted_names() -> None:
    e, rows = edge(outcome=CHAIN), _put()
    rows["pnl_mid"] = [1.0, 2.0, 3.0]
    counted = apply_outcome(e, rows, option_costs=COSTS).set_index("instrument_id")
    n, mean, m2 = roc_moments(e, rows, counted, DAY, COSTS) or (0, 0.0, 0.0)
    rocs = [(p - 0.15 - 0.013) / 100 for p in (1.0, 2.0, 3.0)]
    assert n == 3 and mean == pytest.approx(np.mean(rocs))
    assert m2 == pytest.approx(float(np.sum((np.array(rocs) - np.mean(rocs)) ** 2)))
    assert roc_moments(edge(), rows, counted, DAY, COSTS) is None  # a share edge has none
