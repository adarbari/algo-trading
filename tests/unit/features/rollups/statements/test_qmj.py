"""qmj@v1: the z-scores of the profitability and safety parts and their combination, the
missing-part rules (a part left out, too few parts or members is null) and the mispricing
measures it reads."""

import numpy as np
import pandas as pd
import pytest

from algotrade.features.rollups.statements import qmj
from algotrade.features.rollups.statements.lines import PRICE_STATS, STATEMENTS
from tests.unit.features.rollups.statements.test_mispricing import SESSION, frames

PARAMS = qmj.QmjParams(min_members=3)


def run(inputs: dict | None = None, p: qmj.QmjParams = PARAMS) -> pd.DataFrame:
    return qmj.compute(inputs or frames(), SESSION, p).set_index("instrument_id")


def test_scores_fall_with_the_fixture_s_quality_and_are_standardised() -> None:
    out = run()  # a higher index has lower profitability and more debt and distress
    assert out["profitability_z"].is_monotonic_decreasing
    assert out["safety_z"].is_monotonic_decreasing
    assert out["qmj_score"].is_monotonic_decreasing
    for column in ("profitability_z", "safety_z", "qmj_score"):
        assert out[column].mean() == pytest.approx(0, abs=1e-9)
        assert out[column].std(ddof=0) == pytest.approx(1)


def test_z_is_of_the_rank_so_one_outlier_does_not_stretch_the_scale() -> None:
    inputs = frames()
    gp = inputs[qmj.INCOME].copy()
    gp.loc[0, "gross_profit_ttm"] = 1e9  # an outlier on one part
    out = run({**inputs, qmj.INCOME: gp})
    assert out["profitability_z"].iloc[0] == out["profitability_z"].max()
    assert out["profitability_z"].iloc[0] < 2  # rank z, not value z


def test_a_part_that_cannot_be_formed_is_left_out_not_zero() -> None:
    inputs = frames()
    cf = inputs[qmj.CASH_FLOW].copy()
    cf["ocf_ttm"] = np.nan  # no operating cash flow: two of six parts (cf over assets, accruals)
    out = run({**inputs, qmj.CASH_FLOW: cf})  # four parts remain: still scored
    assert out["profitability_z"].notna().all()
    out = run(
        {**inputs, qmj.CASH_FLOW: cf}, qmj.QmjParams(min_members=3, min_profitability_inputs=5)
    )
    assert out["profitability_z"].isna().all() and out["qmj_score"].isna().all()
    assert out["safety_z"].notna().all()  # the O-score needs ocf, leverage does not


def test_a_thin_cross_section_gives_no_score() -> None:
    out = run(p=qmj.QmjParams(min_members=100))
    assert out[["profitability_z", "safety_z", "qmj_score"]].isna().all().all()


def test_a_stale_statement_is_not_used() -> None:
    inputs = frames()
    bs = inputs[qmj.BALANCE].copy()
    bs.loc[2, "bs_status"] = "STALE"
    out = run({**inputs, qmj.BALANCE: bs})
    assert out["qmj_score"].isna().iloc[2]  # nothing balance-sheet based, too few parts
    assert out["qmj_score"].notna().sum() == 5


def test_params_are_validated() -> None:
    with pytest.raises(ValueError, match="min_profitability_inputs"):
        qmj.QmjParams(min_profitability_inputs=7)
    with pytest.raises(ValueError, match="min_safety_inputs"):
        qmj.QmjParams(min_safety_inputs=0)
    assert {PRICE_STATS, STATEMENTS} <= {i.table for i in qmj.GROUP.inputs}
