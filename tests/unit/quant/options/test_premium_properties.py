"""Property-based tests of the sold option's figures (``quant.options.premium``)."""

import numpy as np
from hypothesis import given
from hypothesis import strategies as st

from algotrade.quant.black_scholes import prob_otm
from algotrade.quant.options import premium

spots = st.floats(1.0, 1_000.0)
moneyness = st.floats(0.3, 3.0)
years = st.floats(1 / 365, 3.0)
vols = st.floats(0.01, 3.0)
mids = st.floats(0.01, 100.0)
rights = st.sampled_from(["put", "call"])


@given(spots, moneyness, vols, years, rights)
def test_p_below_is_a_probability(s: float, m: float, v: float, t: float, right: str) -> None:
    p = float(premium.p_below(s, s * m, v, t, right))
    assert 0.0 <= p <= 1.0


@given(spots, moneyness, vols, years)
def test_a_put_p_below_and_prob_otm_sum_to_one(s: float, m: float, v: float, t: float) -> None:
    below = float(premium.p_below(s, s * m, v, t, "put"))
    assert abs(below + float(prob_otm(s, s * m, v, t, "put")) - 1.0) < 1e-12


@given(spots, moneyness, vols, years)
def test_a_call_p_below_is_its_prob_otm(s: float, m: float, v: float, t: float) -> None:
    assert float(premium.p_below(s, s * m, v, t, "call")) == float(prob_otm(s, s * m, v, t, "call"))


@given(spots, moneyness, st.floats(0.01, 0.5), vols, years, rights)
def test_p_below_rises_with_the_strike(
    s: float, m: float, gap: float, v: float, t: float, right: str
) -> None:
    low = float(premium.p_below(s, s * m, v, t, right))
    high = float(premium.p_below(s, s * (m + gap), v, t, right))
    assert high >= low - 1e-12


@given(spots, moneyness, mids, st.floats(1.0, 365.0), rights)
def test_roc_yield_and_breakeven_identities(
    s: float, m: float, mid: float, dte: float, right: str
) -> None:
    k = s * m
    roc = float(premium.return_on_collateral(mid, k, s, right))
    collateral = s if right == "call" else k
    assert roc == mid / collateral
    assert float(premium.yield_annualised(roc, dte)) == roc * 365.0 / dte
    assert float(premium.breakeven(mid, k, s, right)) == collateral - mid


@given(st.lists(st.tuples(spots, moneyness, vols, years), min_size=1, max_size=20), rights)
def test_vectorised_equals_scalar_and_is_deterministic(
    rows: list[tuple[float, float, float, float]], right: str
) -> None:
    s, m, v, t = (np.array(c) for c in zip(*rows, strict=True))
    batch = premium.p_below(s, s * m, v, t, right)
    again = premium.p_below(s, s * m, v, t, right)
    assert np.array_equal(batch, again)
    for i, (si, mi, vi, ti) in enumerate(rows):
        assert float(batch[i]) == float(premium.p_below(si, si * mi, vi, ti, right))
