"""``fit_scorer`` and ``score``: planted coefficients recovered, the standardisation folded back
into the score, determinism and the refusals."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.quant.black_scholes import norm_cdf
from algotrade.services.evaluation.training.fit import fit_scorer, score
from algotrade.services.evaluation.training.frame import LABEL, TrainingFrame

FEATURES = ("rollup.g@v1.a", "rollup.g@v1.b")


def training(
    n: int = 4000, seed: int = 7, scale_b: float = 1e8, sessions: int = 40
) -> TrainingFrame:
    rng = np.random.default_rng(seed)
    a, b = rng.normal(0.3, 1.1, n), rng.normal(5e8, scale_b, n)
    z = -0.2 + 0.8 * (a - 0.3) / 1.1 - 0.5 * (b - 5e8) / scale_b
    y = (rng.uniform(size=n) < norm_cdf(z)).astype(float)
    frame = pd.DataFrame({"session": date(2026, 1, 1), "instrument_id": "X", FEATURES[0]: a,
                          FEATURES[1]: b, LABEL: y})  # fmt: skip
    return TrainingFrame("e", 20, FEATURES, frame, date(2026, 3, 1), date(2026, 2, 27), sessions)


def test_planted_coefficients_are_recovered() -> None:
    fit = fit_scorer(training())
    assert fit.intercept == pytest.approx(-0.2, abs=0.1)
    assert fit.weights == pytest.approx((0.8, -0.5), abs=0.1)
    assert fit.means[0] == pytest.approx(0.3, abs=0.1) and fit.scales[1] == pytest.approx(
        1e8, rel=0.1
    )
    assert (fit.rows, fit.fitted_through) == (4000, date(2026, 2, 27))


def test_the_score_applies_the_standardised_probit_to_raw_values() -> None:
    fit = fit_scorer(training())
    x = np.array([[0.3, 5e8], [2.0, 3e8]])
    z = fit.intercept + sum(
        w * (x[:, k] - m) / s
        for k, (w, m, s) in enumerate(zip(fit.weights, fit.means, fit.scales, strict=True))
    )
    assert score(fit, x) == pytest.approx(norm_cdf(z), abs=1e-12)
    at_means = score(fit, np.array([fit.means]))
    assert at_means[0] == pytest.approx(norm_cdf(fit.intercept), abs=1e-12)


def test_the_fit_is_deterministic() -> None:
    assert fit_scorer(training()) == fit_scorer(training())


@pytest.mark.parametrize("n", [20, 99])
def test_too_few_rows_is_refused(n: int) -> None:
    with pytest.raises(ConfigurationError, match="too few"):
        fit_scorer(training(n))


def test_too_few_independent_sessions_is_refused_with_the_count() -> None:
    with pytest.raises(ConfigurationError, match=r"3 decision sessions .* 40 independent"):
        fit_scorer(training(sessions=3))


def test_one_class_and_a_constant_feature_are_refused() -> None:
    t = training()
    one = TrainingFrame(**{**t.__dict__, "frame": t.frame.assign(**{LABEL: 1.0})})
    with pytest.raises(ConfigurationError, match="too few"):
        fit_scorer(one)
    flat = TrainingFrame(**{**t.__dict__, "frame": t.frame.assign(**{FEATURES[0]: 1.0})})
    with pytest.raises(ConfigurationError, match="constant"):
        fit_scorer(flat)
