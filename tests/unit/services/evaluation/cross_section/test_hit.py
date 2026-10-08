"""``apply_outcome``: the one place an edge's ``[outcome]`` meets the stored fields. A value that
cannot be computed is excluded with a reason, never a miss; DELISTED rows count; ``oriented`` is
higher-is-better."""

import numpy as np
import pandas as pd
import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.quant.black_scholes import prob_otm, strike_from_delta
from algotrade.services.evaluation.cross_section.hit import apply_outcome, needs_implied_vol
from tests.unit.services.evaluation.cross_section.conftest import edge

NAN = float("nan")
VRP = {
    "kind": "hit_target", "horizon_sessions": [20], "benchmark": "none", "target": 1.0,
    "measure": "realised_to_implied_vol", "direction": "below", "max_drawdown": 0.5,
    "start_offset_sessions": 1,
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
            "start_offset_sessions": 1,
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


# ---- expires_otm: the short option is not assigned at the horizon's close ----------------

SIGMA, YEARS = 0.30, 21 / 252
OTM = {
    "kind": "expires_otm", "horizon_sessions": [21], "benchmark": "none", "structure": "put",
    "strike_delta": 0.30, "iv_field": "rollup.ibkr_iv@v1.iv30_ibkr", "start_offset_sessions": 1,
}  # fmt: skip


def rel(delta: float, right: str, sigma: float = SIGMA) -> float:
    """The strike relative to the entry close, minus 1: the return the strike sits at."""
    return float(strike_from_delta(1.0, sigma, YEARS, delta, right)) - 1.0


def otm_rows(returns: list[float], **columns: list[object]) -> pd.DataFrame:
    n = len(returns)
    return rows(fwd_return=returns, horizon_sessions=[21] * n, fwd_max_return=[0.0] * n, **columns)


def ivs(n: int, level: float = SIGMA) -> dict[str, float | None]:
    return {f"EQ:{i}": level for i in range(n)}


@pytest.mark.parametrize(
    "structure,delta,returns,hits",
    [
        ("put", 0.30, lambda: [rel(0.30, "put") + 0.01, rel(0.30, "put") - 0.01], [True, False]),
        ("call", 0.30, lambda: [rel(0.30, "call") - 0.01, rel(0.30, "call") + 0.01], [True, False]),
        (
            "strangle",
            0.16,
            lambda: [0.0, rel(0.16, "put") - 0.01, rel(0.16, "call") + 0.01],
            [True, False, False],
        ),
    ],
)
def test_the_hit_table_of_each_structure(structure, delta, returns, hits) -> None:  # type: ignore[no-untyped-def]
    e = edge(outcome={**OTM, "structure": structure, "strike_delta": delta})
    r = returns()
    out = apply_outcome(e, otm_rows(r), ivs(len(r)))
    assert list(out["hit"]) == hits and set(out["excluded"]) == {""}
    assert out["value"].iloc[0] > 0  # the cushion to the nearest strike; negative on a miss
    assert (out["value"].iloc[1:] < 0).all()


def test_an_otm_pct_strike_is_a_fixed_fraction_of_the_entry_close() -> None:
    e = edge(outcome={**{k: v for k, v in OTM.items() if k != "strike_delta"}, "otm_pct": 0.05})
    out = apply_outcome(e, otm_rows([-0.049, -0.051, 0.0]), ivs(3))
    assert list(out["hit"]) == [True, False, True]


def test_the_reference_rate_is_the_risk_neutral_chance_and_touch_is_the_intraday_strike() -> None:
    e = edge(outcome=OTM)
    k = rel(0.30, "put")
    out = apply_outcome(
        e,
        otm_rows([0.0, 0.0], fwd_max_drawdown=[-k - 0.001, -k + 0.001]),  # low under / above K
        ivs(2),
    )
    assert list(out["touch"]) == [0.0, 1.0]  # the low reaches K when drawdown >= 1 - K
    expected = float(prob_otm(1.0, 1.0 + k, SIGMA, YEARS, "put"))
    assert out["reference"].iloc[0] == pytest.approx(expected) and 0.5 < expected < 0.8
    two = apply_outcome(edge(outcome={**OTM, "structure": "strangle"}), otm_rows([0.0]), ivs(1))
    assert two["reference"].iloc[0] < expected  # the joint chance is below one leg's


def test_a_null_or_zero_implied_vol_is_excluded_with_a_reason_never_a_hit_or_a_miss() -> None:
    out = apply_outcome(
        edge(outcome=OTM), otm_rows([0.0, 0.0, 0.0]), {"EQ:0": None, "EQ:1": 0.0, "EQ:2": 0.3}
    )
    assert list(out["excluded"]) == ["no_implied_vol", "no_implied_vol", ""]
    assert not out["hit"].iloc[:2].any() and np.isnan(out["reference"].iloc[:2]).all()
    assert needs_implied_vol(edge(outcome=OTM))
    with pytest.raises(ConfigurationError, match="needs the implied vol"):
        apply_outcome(edge(outcome=OTM), otm_rows([0.0]))


@pytest.mark.filterwarnings("error")
@pytest.mark.parametrize("structure", ["put", "call", "strangle"])
def test_an_absurd_or_non_finite_implied_vol_is_excluded_never_a_miss_and_never_warns(
    structure: str,
) -> None:
    """Real IBKR rows hold IV30 up to 31420 (a 5 > range): exp overflowed, the strike went
    inf / 0 and the put "missed". Out of the declared (0, 5] range is excluded as invalid."""
    out = apply_outcome(
        edge(outcome={**OTM, "structure": structure}),
        otm_rows([0.0] * 6),
        {f"EQ:{i}": v for i, v in enumerate((1e3, 31420.0, float("inf"), NAN, 5.01, 5.0))},
    )
    assert list(out["excluded"]) == ["invalid_implied_vol"] * 3 + ["no_implied_vol"] + [
        "invalid_implied_vol",
        "",
    ]
    assert not out["hit"].iloc[:5].any()  # excluded rows never hit; IV = 5.0 still counts
    assert np.isnan(out["value"].iloc[:5]).all() and np.isnan(out["reference"].iloc[:5]).all()


@pytest.mark.filterwarnings("error")
def test_an_absurd_implied_vol_is_excluded_from_the_vol_ratio_too() -> None:
    out = apply_outcome(
        edge(outcome=VRP, schedule="every_session"), rows(fwd_excess_return=[0.0] * 2),
        {"EQ:0": 1e3, "EQ:1": 0.3},
    )  # fmt: skip
    assert list(out["excluded"]) == ["invalid_implied_vol", ""]


def test_a_higher_vol_puts_the_strike_further_out_so_the_same_return_hits() -> None:
    low = apply_outcome(edge(outcome=OTM), otm_rows([-0.05]), ivs(1, 0.2))
    high = apply_outcome(edge(outcome=OTM), otm_rows([-0.05]), ivs(1, 0.6))
    assert [bool(low["hit"].iloc[0]), bool(high["hit"].iloc[0])] == [False, True]
