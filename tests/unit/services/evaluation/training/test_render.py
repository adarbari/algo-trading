"""The TOML expression feature: the coefficients through the expression engine give the fit's
score (the round trip), the file merge keeps other edges' tables, and the field names map."""

import tomllib
from datetime import date

import numpy as np
import pandas as pd
import pytest

from algotrade.config.site.features.definitions import feature_definitions
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.registry import GROUPS, SUPERSEDED
from algotrade.services.evaluation.training.fit import ScorerFit, score
from algotrade.services.evaluation.training.render import (
    FILE_HEADER,
    expression_name,
    feature_name,
    merge_scorers,
    render_scorer,
)
from tests.conftest import REPO_ROOT

SITE_FEATURES = REPO_ROOT / "config" / "site" / "features"
FIELDS = ("rollup.trend_stats@v2.mom_12_1", "rollup.price_stats@v2.adv_usd_20d")
D = date(2026, 3, 2)


def fitted(edge_id: str = "momo") -> ScorerFit:
    return ScorerFit(edge_id, 20, FIELDS, 0.128, (-0.084, 0.146), (0.283, 4.6e8), (1.13, 1.6e9),
                     3758, 3, 2075, date(2026, 3, 3), -100.0)  # fmt: skip


def test_expression_names() -> None:
    assert expression_name("rollup.trend_stats@v2.mom_12_1") == "trend_stats.mom_12_1"
    assert expression_name("feature.vrp_iv30") == "vrp_iv30"


def test_the_expression_feature_scores_what_the_fit_predicts() -> None:
    fit = fitted()
    doc = tomllib.loads(render_scorer(fit))
    site = {p.stem: tomllib.loads(p.read_text()) for p in SITE_FEATURES.glob("*.toml")}
    fs = FeatureSet.build(GROUPS, feature_definitions({**site, "edge_scores": doc}), SUPERSEDED)
    x = np.array([[0.5, 1e9], [-0.2, 2e8], [1.5, 5e9]])
    ids = ["A", "B", "C"]
    frames = {
        "rollups/instrument/trend_stats@v2": pd.DataFrame(
            {"session_date": D, "instrument_id": ids, "mom_12_1": x[:, 0]}
        ),
        "rollups/instrument/price_stats@v2": pd.DataFrame(
            {"session_date": D, "instrument_id": ids, "adv_usd_20d": x[:, 1]}
        ),
    }
    out = fs.evaluate(frames, [feature_name("momo")])
    assert out[feature_name("momo")].to_numpy() == pytest.approx(score(fit, x), abs=1e-12)


def test_merge_replaces_an_edges_table_with_the_next_version_and_keeps_the_others() -> None:
    first = merge_scorers("", "momo", render_scorer(fitted("momo")))
    both = merge_scorers(first, "alpha", render_scorer(fitted("alpha")))
    again = merge_scorers(both, "momo", render_scorer(fitted("momo")))
    assert both.startswith(FILE_HEADER)
    docs = tomllib.loads(again)
    assert list(docs) == ["edge_score_alpha", "edge_score_momo"]  # sorted by name
    assert (docs["edge_score_momo"]["version"], docs["edge_score_alpha"]["version"]) == (2, 1)
    assert "fitted_through=2026-03-03" in docs["edge_score_momo"]["description"]
