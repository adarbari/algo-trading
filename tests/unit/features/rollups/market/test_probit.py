"""``market_bear_probit@v1``: the probability by hand from the session's macro row, the source
label from ``fitted``, null (never a guess) when an input is null, and bad coefficients refused."""

import math
from datetime import date

import pandas as pd
import pytest

from algotrade.features.rollups.market import macro, probit
from algotrade.features.rollups.market.probit import Params, compute
from algotrade.quant.black_scholes import norm_cdf

DAY = date(2007, 6, 29)


def inputs(**values: object) -> dict[str, pd.DataFrame | None]:
    row = {"instrument_id": "MKT:US", "session_date": DAY, **values}
    return {macro.GROUP.table: pd.DataFrame([row])}


def test_the_probability_by_hand_with_the_literature_defaults() -> None:
    got = compute(inputs(curve_10y3m=-0.005, cpi_yoy=0.04, hy_oas=0.05), DAY, Params())
    z = -1.0 - 40 * -0.005 + 15 * 0.04 + 10 * 0.05
    assert list(got["instrument_id"]) == ["MKT:US"]
    assert got.iloc[0]["bear_prob_6m"] == pytest.approx(float(norm_cdf(z)))
    assert got.iloc[0]["bear_prob_source"] == "literature"
    fitted = Params(b0=0.2, b_curve=0.0, b_cpi=0.0, b_hy=0.0, fitted=True)
    row = compute(inputs(curve_10y3m=0.01, cpi_yoy=0.02, hy_oas=0.04), DAY, fitted).iloc[0]
    assert (row["bear_prob_6m"], row["bear_prob_source"]) == (
        pytest.approx(float(norm_cdf(0.2))),
        "fitted",
    )


def test_a_null_input_or_no_row_is_unknown() -> None:
    before_1997 = compute(inputs(curve_10y3m=0.01, cpi_yoy=0.03, hy_oas=None), DAY, Params())
    assert math.isnan(before_1997.iloc[0]["bear_prob_6m"])
    assert before_1997.iloc[0]["bear_prob_source"] is None
    empty = compute({macro.GROUP.table: None}, DAY, Params())
    assert math.isnan(empty.iloc[0]["bear_prob_6m"])


def test_the_group_reads_the_macro_columns_and_refuses_bad_coefficients() -> None:
    assert probit.GROUP.entity == "market" and probit.GROUP.key == "market_bear_probit@v1"
    reads = probit.GROUP.feature("bear_prob_6m").inputs
    assert reads == tuple(macro.GROUP.feature(c).key for c in probit.REGRESSORS)
    assert probit.GROUP.feature("bear_prob_6m").licence == "personal"  # from hy_oas
    with pytest.raises(ValueError, match="finite"):
        Params(b_hy=math.inf)
