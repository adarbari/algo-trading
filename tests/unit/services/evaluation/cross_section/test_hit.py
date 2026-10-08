"""``apply_outcome``: the one place an edge's ``[outcome]`` meets the stored fields. A value that
cannot be computed is excluded with a reason, never a miss; DELISTED rows count; ``oriented`` is
higher-is-better."""

import numpy as np
import pandas as pd
import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.services.evaluation.cross_section.hit import apply_outcome, needs_implied_vol
from tests.unit.services.evaluation.cross_section.conftest import edge

NAN = float("nan")
VRP = {
    "kind": "hit_target", "horizon_sessions": [20], "benchmark": "none", "target": 1.0,
    "measure": "realised_to_implied_vol", "direction": "below", "max_drawdown": 0.5,
}  # fmt: skip


def rows(**columns: list[object]) -> pd.DataFrame:
    n = len(next(iter(columns.values())))
    base = {
        "instrument_id": [f"EQ:{i}" for i in range(n)], "fwd_excess_return": [0.0] * n,
        "fwd_realised_vol": [0.2] * n, "fwd_max_drawdown": [0.0] * n,
        "outcome_status": ["COMPLETE"] * n,
    }  # fmt: skip
    return pd.DataFrame({**base, **columns})


def test_an_excess_return_hit_is_net_of_the_round_trip_cost() -> None:
    e = edge(
        outcome={
            "kind": "excess_return",
            "horizon_sessions": [2],
            "benchmark": "SPY",
            "cost_bps": 100,
        }
    )
    out = apply_outcome(e, rows(fwd_excess_return=[0.02, 0.01, 0.005, -0.01]))
    assert list(out["hit"]) == [True, False, False, False]  # 0.01 - 0.01 is not above zero
    assert np.allclose(out["value"], [0.01, 0.0, -0.005, -0.02])
    assert np.allclose(out["oriented"], out["value"])
    assert set(out["excluded"]) == {""}


def test_a_null_excess_return_is_excluded_never_a_miss_or_a_zero() -> None:
    out = apply_outcome(edge(), rows(fwd_excess_return=[0.05, NAN, -0.05]))
    assert list(out["excluded"]) == ["", "missing_value", ""]
    assert list(out["hit"]) == [True, False, False]
    assert np.isnan(out["value"][1]) and np.isnan(out["oriented"][1])


def test_a_hit_target_divides_realised_by_the_implied_vol_and_orients_below() -> None:
    e = edge(outcome=VRP, schedule="every_session")
    assert needs_implied_vol(e)
    implied = {"EQ:0": 0.4, "EQ:1": 0.1, "EQ:2": 0.2, "EQ:3": None, "EQ:4": 0.0, "EQ:5": 0.4}
    out = apply_outcome(
        e,
        rows(
            fwd_realised_vol=[0.2, 0.2, 0.2, 0.2, 0.2, NAN],
            fwd_max_drawdown=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        ),
        implied,
    )
    assert list(out["excluded"]) == [
        "",
        "",
        "",
        "no_implied_vol",
        "no_implied_vol",
        "missing_value",
    ]
    assert list(out["hit"]) == [True, False, False, False, False, False]  # 0.5 < 1; 2.0; 1.0 equal
    assert np.allclose(out["oriented"][:3], [-0.5, -2.0, -1.0])


def test_the_drawdown_cap_makes_a_hit_need_a_shallow_path() -> None:
    e = edge(outcome=VRP, schedule="every_session")
    out = apply_outcome(
        e, rows(fwd_max_drawdown=[0.4, 0.5, 0.6, NAN]), {f"EQ:{i}": 0.4 for i in range(4)}
    )
    assert list(out["hit"]) == [True, True, False, False]
    assert list(out["excluded"]) == ["", "", "", "missing_drawdown"]


def test_delisted_rows_count_and_are_flagged() -> None:
    out = apply_outcome(
        edge(), rows(fwd_excess_return=[-0.3, 0.1], outcome_status=["DELISTED", "COMPLETE"])
    )
    assert list(out["delisted"]) == [True, False]
    assert list(out["excluded"]) == ["", ""]
    assert list(out["hit"]) == [False, True]


def test_the_implied_vol_is_required_for_a_ratio_measure() -> None:
    with pytest.raises(ConfigurationError, match="implied"):
        apply_outcome(edge(outcome=VRP, schedule="every_session"), rows(fwd_excess_return=[0.0]))
