"""``apply_outcome``: the one place an edge's ``[outcome]`` meets the stored fields. A value that
cannot be computed is excluded with a reason, never a miss; DELISTED rows count; ``oriented`` is
higher-is-better."""

from datetime import date
from typing import Any

import numpy as np
import pandas as pd
import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.calendar import next_session
from algotrade.quant.black_scholes import (
    atm_straddle_price,
    atm_straddle_vega,
    prob_otm,
    strike_from_delta,
)
from algotrade.services.evaluation.cross_section.hit import (
    apply_outcome,
    borrow_cost,
    needs_implied_vol,
    short_view,
)
from algotrade.storage.tables.schemas import RESIDUAL_RETURNS
from tests.helpers.stored_frames import stamped
from tests.unit.services.evaluation.cross_section.conftest import (
    IDS,
    KNOWN,
    World,
    build_world,
    edge,
)
from tests.unit.services.evaluation.cross_section.test_harness import DAYS, run

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


def test_an_unmeasured_row_is_excluded_with_its_reason_never_a_miss() -> None:
    out = apply_outcome(
        edge(),
        rows(fwd_excess_return=[None, 0.1], outcome_status=["UNMEASURED", "COMPLETE"]),
    )
    assert list(out["excluded"]) == ["unmeasured", ""]
    assert list(out["hit"]) == [False, True] and np.isnan(out["value"].iloc[0])


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


# ---- option_model_pnl: the modelled straddle P&L (basis "model") -------------------------

MODEL = {
    "kind": "option_model_pnl", "horizon_sessions": [21], "benchmark": "none",
    "structure": "atm_straddle_long", "iv_field": "rollup.ibkr_iv@v1.iv30_ibkr",
    "start_offset_sessions": 1,
}  # fmt: skip


def model_edge(**changes: object):  # type: ignore[no-untyped-def]
    return edge(outcome={**MODEL, **changes}, schedule="every_session")


def test_a_long_straddle_earns_the_move_less_the_closed_form_price() -> None:
    e = model_edge()
    assert needs_implied_vol(e)
    price = float(atm_straddle_price(SIGMA, YEARS))
    out = apply_outcome(e, otm_rows([0.10, -0.10, 0.0]), ivs(3))
    assert np.allclose(out["value"], [0.10 - price, 0.10 - price, -price])
    assert list(out["hit"]) == [True, True, False]
    assert set(out["excluded"]) == {""} and np.isnan(out["reference"]).all()


def test_a_short_straddle_is_the_exact_negative_of_the_long_one() -> None:
    r = otm_rows([0.10, -0.02, 0.0])
    long = apply_outcome(model_edge(), r, ivs(3))
    short = apply_outcome(model_edge(structure="atm_straddle_short"), r, ivs(3))
    assert np.allclose(short["value"], -long["value"])
    assert list(short["hit"]) == [False, True, True]  # a quiet window pays the seller


def test_a_delta_hedged_straddle_earns_the_vega_form_and_its_sign_follows_realised_vs_implied() -> (
    None
):
    e = model_edge(structure="delta_hedged_atm")
    r = otm_rows([0.0] * 3, fwd_realised_vol=[0.40, 0.30, 0.20])
    out = apply_outcome(e, r, ivs(3))
    vega = float(atm_straddle_vega(SIGMA, YEARS))
    assert np.allclose(out["value"], [vega * 0.07 / 0.6, 0.0, -vega * 0.05 / 0.6])
    assert list(out["hit"]) == [True, False, False]  # equal is a miss


def test_the_short_delta_hedged_straddle_is_the_exact_negative_of_the_long_one() -> None:
    r = otm_rows([0.0] * 3, fwd_realised_vol=[0.40, 0.30, 0.20])
    long = apply_outcome(model_edge(structure="delta_hedged_atm"), r, ivs(3))
    short = apply_outcome(model_edge(structure="delta_hedged_atm_short"), r, ivs(3))
    assert np.allclose(short["value"], -long["value"])
    assert list(short["hit"]) == [False, False, True]  # a calm window pays the seller


def test_the_cost_is_charged_once_in_bps_of_the_entry_price_whatever_the_structure() -> None:
    r = otm_rows([0.10, 0.10])
    gross = apply_outcome(model_edge(structure="atm_straddle_short"), r, ivs(2))["value"]
    net = apply_outcome(model_edge(structure="atm_straddle_short", cost_bps=25), r, ivs(2))
    assert np.allclose(net["value"], gross - 0.0025)
    hedged = otm_rows([0.0], fwd_realised_vol=[0.30])
    cost = apply_outcome(model_edge(structure="delta_hedged_atm", cost_bps=25), hedged, ivs(1))
    assert np.allclose(cost["value"], -0.0025)


def test_a_missing_vol_or_path_is_excluded_with_a_reason_never_a_zero_or_a_miss() -> None:
    r = otm_rows([NAN, 0.1, 0.1, 0.1, 0.1])
    implied = {"EQ:0": 0.3, "EQ:1": None, "EQ:2": 0.0, "EQ:3": 99.0, "EQ:4": 0.3}
    out = apply_outcome(model_edge(), r, implied)
    assert list(out["excluded"]) == [
        "missing_value", "no_implied_vol", "no_implied_vol", "invalid_implied_vol", "",
    ]  # fmt: skip
    assert out["value"].isna().tolist() == [True, True, True, True, False]
    assert not out["hit"].iloc[:4].any()
    hedged = apply_outcome(
        model_edge(structure="delta_hedged_atm"),
        otm_rows([0.0, 0.0], fwd_realised_vol=[NAN, 0.3]),
        ivs(2),
    )
    assert list(hedged["excluded"]) == ["missing_value", ""]


def test_an_unmeasured_row_is_excluded_as_unmeasured_before_the_model_reason() -> None:
    r = otm_rows([NAN, 0.1], outcome_status=["UNMEASURED", "COMPLETE"])
    out = apply_outcome(model_edge(), r, ivs(2))
    assert list(out["excluded"]) == ["unmeasured", ""]


def test_a_row_with_no_horizon_has_no_time_to_expiry_so_no_value() -> None:
    r = otm_rows([0.1])
    r["horizon_sessions"] = [NAN]
    assert apply_outcome(model_edge(), r, ivs(1))["excluded"].iloc[0] == "missing_value"


def test_the_model_pnl_needs_the_implied_vol() -> None:
    with pytest.raises(ConfigurationError, match="needs the implied vol"):
        apply_outcome(model_edge(), otm_rows([0.1]))


def _sided(side: str, **outcome: object) -> object:
    base = {
        "kind": "excess_return", "horizon_sessions": [20], "benchmark": "SPY",
        "start_offset_sessions": 1, "cost_bps": 50, "side": side, "borrow_bps_annual": 252,
    }  # fmt: skip
    return edge(outcome={**base, **outcome}, top_k=5)


def test_a_short_value_is_minus_the_excess_return_less_cost_and_borrow() -> None:
    """252 bp a year over 20 of 252 sessions is 20 bp; cost is 50 bp: a short pays 70 bp."""
    e = _sided("short")
    frame = rows(fwd_excess_return=[-0.03, -0.005, 0.01, NAN], horizon_sessions=[20] * 4)
    out = apply_outcome(e, frame)
    assert np.allclose(out["short_value"][:3], [0.03 - 0.007, 0.005 - 0.007, -0.01 - 0.007])
    assert list(out["short_hit"]) == [True, False, False, False]  # -0.2%: it fell less than costs
    assert np.isnan(out["short_value"][3]) and out["excluded"][3] == "missing_value"
    # the long columns are untouched: the base and the deciles are over them whatever the side
    assert np.allclose(out["oriented"][:3], [-0.03 - 0.005, -0.005 - 0.005, 0.01 - 0.005])
    assert list(out["hit"]) == [False, False, True, False]
    view = short_view(out.set_index("instrument_id"))
    assert np.allclose(view["oriented"].iloc[:3], out["short_value"][:3])
    assert list(view["hit"]) == list(out["short_hit"])


def test_a_long_outcome_has_no_short_value_and_borrow_scales_with_the_holding_period() -> None:
    out = apply_outcome(edge(), rows(fwd_excess_return=[0.05, -0.05], horizon_sessions=[2, 2]))
    assert np.isnan(out["short_value"]).all() and not out["short_hit"].any()
    assert np.allclose(borrow_cost(252.0, np.array([252.0, 63.0])), [0.0252, 0.0063])
    assert np.allclose(borrow_cost(None, np.array([20.0])), [0.0])


# ---- option_pnl: the P&L of quoted prices from the chain grain (basis "chain") ------------

CHAIN = {
    "kind": "option_pnl", "horizon_sessions": [5], "benchmark": "none", "tenor_days": 30,
    "structure": "atm_straddle_long", "start_offset_sessions": 1,
}  # fmt: skip


def chain_rows(n: int = 3, **columns: object) -> pd.DataFrame:
    """Rows of the chain grain: entry 5.0 mid / 5.2 ask on a 100 stock, exit 7.0 mid / 6.8 bid
    (half-spreads 0.2 at entry and 0.2 at exit), mid P&L 2.0 (0.02 of the stock), hedged 1.0."""
    base: dict[str, object] = {
        "instrument_id": [f"EQ:{i}" for i in range(n)], "structure": ["atm_straddle"] * n,
        "tenor_days": [30] * n, "entry_spot": [100.0] * n, "entry_mid": [5.0] * n,
        "entry_ask": [5.2] * n, "exit_mid": [7.0] * n, "exit_bid": [6.8] * n,
        "pnl_per_underlying": [0.02] * n, "hedged_pnl_per_underlying": [0.01] * n,
        "outcome_status": ["COMPLETE"] * n, "outcome_reason": [None] * n,
        "hedge_reason": [None] * n,
    }  # fmt: skip
    return pd.DataFrame({**base, **columns})


def chain_edge(**changes: object):  # type: ignore[no-untyped-def]
    return edge(outcome={**CHAIN, **changes}, schedule="every_session")


def test_a_long_straddle_earns_the_quoted_executable_pnl_over_the_entry_spot() -> None:
    e = chain_edge()
    assert not needs_implied_vol(e)  # priced from quotes: no implied-vol field
    out = apply_outcome(e, chain_rows())
    assert np.allclose(out["value"], (6.8 - 5.2) / 100)  # bought at the ask, sold at the bid
    assert list(out["hit"]) == [True] * 3 and set(out["excluded"]) == {""}


def test_a_short_structure_sells_at_the_bid_and_buys_back_at_the_ask() -> None:
    out = apply_outcome(chain_edge(structure="atm_straddle_short"), chain_rows())
    entry_bid, exit_ask = 2 * 5.0 - 5.2, 2 * 7.0 - 6.8  # the quote is symmetric around the mid
    assert np.allclose(out["value"], (entry_bid - exit_ask) / 100)
    assert list(out["hit"]) == [False] * 3  # the straddle gained, the seller lost


def test_a_hedged_structure_reads_the_hedged_pnl_less_the_same_half_spreads() -> None:
    long = apply_outcome(chain_edge(structure="delta_hedged_atm"), chain_rows())
    short = apply_outcome(chain_edge(structure="delta_hedged_atm_short"), chain_rows())
    assert np.allclose(long["value"], 0.01 - (0.2 + 0.2) / 100)
    assert np.allclose(short["value"], -0.01 - (0.2 + 0.2) / 100)  # a seller pays the spread too


def test_cost_bps_is_charged_once_in_bps_of_the_entry_spot() -> None:
    base = apply_outcome(chain_edge(), chain_rows())["value"]
    costed = apply_outcome(chain_edge(cost_bps=25), chain_rows())["value"]
    assert np.allclose(base - costed, 0.0025)


def test_only_the_edges_structure_and_tenor_are_scored_one_row_per_instrument() -> None:
    frame = pd.concat(
        [
            chain_rows(2),
            chain_rows(2, structure=["put_delta_25"] * 2),
            chain_rows(2, tenor_days=[60] * 2),
        ],
        ignore_index=True,
    )
    out = apply_outcome(chain_edge(), frame)
    assert list(out["instrument_id"]) == ["EQ:0", "EQ:1"]
    put = apply_outcome(
        chain_edge(structure="put_short", strike_delta=0.25), frame.assign(pnl_per_underlying=0.0)
    )
    assert list(put["instrument_id"]) == ["EQ:0", "EQ:1"]  # the long put of delta 0.25, sold


def test_an_unmeasured_or_priceless_row_is_excluded_never_a_miss_or_a_zero() -> None:
    frame = chain_rows(
        3, outcome_status=["COMPLETE", "UNMEASURED", "COMPLETE"],
        outcome_reason=[None, "STALE_CHAIN:2026-10-06", None],
        pnl_per_underlying=[0.02, None, NAN],
    )  # fmt: skip
    out = apply_outcome(chain_edge(), frame)
    assert list(out["excluded"]) == ["", "unmeasured", "missing_value"]
    assert np.isnan(out["value"].iloc[1:]).all() and not out["hit"].iloc[1:].any()


def test_a_hedged_row_with_a_hedge_reason_is_unmeasured_but_an_unhedged_one_still_counts() -> None:
    frame = chain_rows(
        2, hedged_pnl_per_underlying=[0.01, None], hedge_reason=[None, "STALE_CHAIN:2026-10-06"]
    )
    hedged = apply_outcome(chain_edge(structure="delta_hedged_atm"), frame)
    assert list(hedged["excluded"]) == ["", "unmeasured"] and not hedged["hit"].iloc[1]
    plain = apply_outcome(chain_edge(), frame)  # the unhedged P&L does not need the hedge
    assert list(plain["excluded"]) == ["", ""] and plain["hit"].all()


def _residual(**outcome: object) -> object:
    base = {
        "kind": "excess_return", "measure": "residual_return", "horizon_sessions": [20],
        "benchmark": "SPY", "start_offset_sessions": 1, "cost_bps": 100,
    }  # fmt: skip
    return edge(outcome={**base, **outcome}, top_k=5)


def _with_residual(**columns: list[object]) -> pd.DataFrame:
    n = len(next(iter(columns.values())))
    base = {"residual_status": ["COMPLETE"] * n, "residual_reason": [None] * n}
    return rows(fwd_excess_return=[0.5] * n, **{**base, **columns})  # excess is far from it


def test_a_residual_outcome_reads_the_residual_never_the_excess_return() -> None:
    out = apply_outcome(_residual(), _with_residual(fwd_residual_return=[0.02, 0.01, -0.01]))
    assert np.allclose(out["value"], [0.01, 0.0, -0.02])  # net of 100 bp, not of 0.5
    assert list(out["hit"]) == [True, False, False] and set(out["excluded"]) == {""}


def test_an_unmeasured_residual_is_excluded_unmeasured_never_a_miss_or_the_excess() -> None:
    frame = _with_residual(
        fwd_residual_return=[0.05, NAN, 0.05],
        residual_status=["COMPLETE", "UNMEASURED", "COMPLETE"],
        residual_reason=[None, "NO_FACTOR_HISTORY", None],
    )
    frame.loc[2, "outcome_status"] = "UNMEASURED"  # a flagged bar in the forward window too
    out = apply_outcome(_residual(), frame)
    assert list(out["excluded"]) == ["", "unmeasured", "unmeasured"]
    assert list(out["hit"]) == [True, False, False] and np.isnan(out["value"][1])


def test_a_residual_outcome_without_the_attached_residuals_fails_loudly() -> None:
    with pytest.raises(ConfigurationError, match="residual-returns rows"):
        apply_outcome(_residual(), rows(fwd_excess_return=[0.05]))


def test_a_short_residual_is_minus_the_residual_less_cost_and_borrow() -> None:
    e = _residual(side="short", borrow_bps_annual=0)
    out = apply_outcome(
        e, _with_residual(fwd_residual_return=[-0.03, 0.01], horizon_sessions=[20] * 2)
    )
    assert np.allclose(out["short_value"], [0.03 - 0.01, -0.01 - 0.01])
    assert list(out["short_hit"]) == [True, False]


ENTRIES = [*DAYS, next_session(DAYS[-1])]  # the world stores outcomes for these start sessions
HARNESS_RESIDUAL = {
    "kind": "excess_return", "measure": "residual_return", "horizon_sessions": [2],
    "benchmark": "SPY", "start_offset_sessions": 1,
}  # fmt: skip


def _write_residuals(w: World, day: date, scale: float = 2.0) -> None:
    rows: list[dict[str, Any]] = [
        {
            "instrument_id": iid, "ts": pd.Timestamp(f"{day}T20:00Z"), "horizon_sessions": 2,
            "window_end": day, "beta_session": day, "outcome_status": "COMPLETE",
            "fwd_residual_return": scale * (i - 9.5) / 100, "fwd_factor_return": 0.0,
        }
        for i, iid in enumerate(IDS)
    ]  # fmt: skip
    frame = stamped(rows, day, f"r-{day}", KNOWN, "residual_returns")
    w.writer.write_table(RESIDUAL_RETURNS, day, f"r-{day}", frame)


def test_the_statistics_read_the_residual_not_the_excess_return() -> None:
    w = build_world()
    for day in ENTRIES:
        _write_residuals(w, day)
    (r,) = run(w, edge(outcome=HARNESS_RESIDUAL)).results
    m = r.measures[0]
    # the excess return of name i is (i - 9.5)%, its residual twice that: picks 15..19 earn 15%
    assert m.mean_excess_picks == pytest.approx(0.15)
    assert (m.sessions, m.picks, m.hits) == (4, 20, 20)
    assert m.decile_spread == pytest.approx(0.36)  # twice the excess run's 0.18


def test_a_start_session_without_residuals_is_unmeasured_never_a_miss_or_a_zero() -> None:
    w = build_world()
    for day in ENTRIES[:-1]:  # the residuals of the last start session were not written
        _write_residuals(w, day)
    plain = run(build_world(), edge()).results[0].measures[0]
    m = run(w, edge(outcome=HARNESS_RESIDUAL)).results[0].measures[0]
    assert m.sessions < plain.sessions  # the unstored session is not measured at all
    assert m.hits == m.picks  # and what is measured is not diluted by zeros


def test_an_excess_return_edge_never_reads_the_residual_rows() -> None:
    w = build_world()
    for day in ENTRIES:
        _write_residuals(w, day, scale=-5.0)  # would flip every figure if they were read
    m = run(w, edge()).results[0].measures[0]
    assert m.mean_excess_picks == pytest.approx(0.075)
