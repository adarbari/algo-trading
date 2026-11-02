"""Where a rule reading a fitted score is judged (E14): the scores a field depends on (directly
or inside another expression), the first judged session after ``fitted_through`` plus the fit's
horizon on the trading calendar, the identity a refit changes, and the fail-closed cases."""

import tomllib
from dataclasses import replace
from datetime import date

import pytest

from algotrade.config.site.features.definitions import FeatureDefinition, feature_definitions
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.calendar import next_session
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.registry import GROUPS, SUPERSEDED
from algotrade.services.evaluation.training.bound import (
    first_judged_session,
    fit_record,
    scored,
    scored_identity,
)
from algotrade.services.evaluation.training.render import render_scorer
from tests.conftest import REPO_ROOT
from tests.unit.services.evaluation.training.test_render import fitted

SITE_FEATURES = REPO_ROOT / "config" / "site" / "features"
THROUGH = date(2026, 3, 3)  # a Tuesday


def _set(version_from: int = 1) -> FeatureSet:
    doc = tomllib.loads(render_scorer(fitted(), version=version_from))
    site = {p.stem: tomllib.loads(p.read_text()) for p in SITE_FEATURES.glob("*/*.toml")}
    derived = FeatureDefinition(
        "momo_half", "test", "edge_score_momo / 2", "float", "decimal", "half the score", "never"
    )
    defs = [*feature_definitions({**site, "edge_scores": doc}), derived]
    return FeatureSet.build(GROUPS, defs, SUPERSEDED)


def test_a_score_is_found_by_name_and_inside_another_expression() -> None:
    fs = _set()
    assert [f.name for f in scored(fs, ["feature.edge_score_momo"])] == ["edge_score_momo"]
    assert [f.name for f in scored(fs, ["feature.momo_half"])] == ["edge_score_momo"]  # indirect
    assert scored(fs, ["feature.near_52w", "rollup.price_stats@v2.hv30", "instrument.status"]) == ()


def test_the_first_judged_session_is_after_fitted_through_plus_the_fit_horizon() -> None:
    scores = scored(_set(), ["feature.edge_score_momo"])
    assert fit_record(scores[0].description) == (THROUGH, 20)
    day = THROUGH
    for _ in range(21):  # the fit's horizon (20) sessions on, and one more
        day = next_session(day)
    assert first_judged_session(scores) == day
    assert first_judged_session(()) is None


def test_a_score_that_records_no_fit_fails_closed() -> None:
    (score,) = scored(_set(), ["feature.edge_score_momo"])
    with pytest.raises(ConfigurationError, match="records no fitted_through"):
        first_judged_session([replace(score, description="a probit")])


def test_a_refit_changes_the_trial_identity() -> None:
    first = scored_identity(scored(_set(1), ["feature.edge_score_momo"]))
    refit = scored_identity(scored(_set(2), ["feature.edge_score_momo"]))
    assert first != refit and first == scored_identity(scored(_set(1), ["feature.momo_half"]))
