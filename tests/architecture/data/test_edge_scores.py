"""Learned scorers never see the frozen period (ADR 0053 amendment, ED7): every
``edge_score_<edge>`` expression feature in ``config/site/features/edge_scores.toml`` (none is
committed until a fit has the minimum independent sessions) names an edge that declares
``[scorer]`` features and a ``frozen_from``, records ``fitted_through`` before the purge cutoff
of its horizon, and reads exactly the declared features. Every declared ``@v<n>`` is its group's
current registry version. The checks run on a rendered table too, so an empty file is not a pass
of nothing."""

import re
import tomllib
from collections.abc import Mapping
from dataclasses import replace
from datetime import date
from typing import Any

import pytest

from algotrade.config.edges.loading import load_edges
from algotrade.services.evaluation.training.fit import ScorerFit
from algotrade.services.evaluation.training.frame import purge_cutoff
from algotrade.services.evaluation.training.render import (
    PREFIX,
    check_versions,
    expression_name,
    render_scorer,
)
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT

STORE = FileConfigStore(REPO_ROOT / "config", local=False)
EDGES = {e.id: e for e in load_edges(STORE)}
FILE = REPO_ROOT / "config" / "site" / "features" / "edge_scores.toml"
SCORES = tomllib.loads(FILE.read_text()) if FILE.exists() else {}
FITTED = re.compile(r"fitted_through=(\d{4}-\d{2}-\d{2})")
HORIZON = re.compile(r"horizon=(\d+) sessions")


def check_scorer(name: str, table: Mapping[str, Any], edges: Mapping[str, Any]) -> None:
    assert name.startswith(PREFIX), f"{name}: a learned scorer is named {PREFIX}<edge>"
    edge = edges.get(name.removeprefix(PREFIX))
    assert edge is not None, f"{name}: no edge document {name.removeprefix(PREFIX)!r}"
    assert edge.frozen_from is not None, f"{edge.id}: a scorer needs frozen_from"
    assert edge.scorer_features, f"{edge.id}: a scorer needs [scorer] features"
    fitted, horizon = FITTED.search(table["description"]), HORIZON.search(table["description"])
    assert fitted and horizon, f"{name}: the description records fitted_through and horizon"
    cutoff = purge_cutoff(edge.frozen_from, int(horizon.group(1)))
    assert date.fromisoformat(fitted.group(1)) < cutoff, (
        f"{name}: fitted_through {fitted.group(1)} is not before the purge cutoff {cutoff}"
    )
    expected = {expression_name(f) for f in edge.scorer_features}
    used = set(re.findall(r"[a-z_0-9]+\.[a-z_0-9]+", table["expr"]))
    assert used == expected, f"{name} was fitted on other features than {edge.id} declares now"


@pytest.mark.parametrize("name", sorted(SCORES))
def test_every_committed_scorer_respects_the_frozen_period(name: str) -> None:
    check_scorer(name, SCORES[name], EDGES)


@pytest.mark.parametrize(
    "edge", [e for e in EDGES.values() if e.scorer_features], ids=lambda e: e.id
)
def test_a_declared_scorer_field_is_its_groups_current_version(edge) -> None:  # type: ignore[no-untyped-def]
    check_versions(edge.scorer_features)


def _fit(edge_id: str, through: date, horizon: int = 20) -> ScorerFit:
    features = EDGES["momentum_12_1"].scorer_features
    n = len(features)
    return ScorerFit(edge_id, horizon, features, 0.0, (0.1,) * n, (0.0,) * n, (1.0,) * n,
                     500, 40, 250, through, -1.0)  # fmt: skip


def _table(fit: ScorerFit) -> dict[str, Any]:
    return tomllib.loads(render_scorer(fit))[f"{PREFIX}{fit.edge_id}"]


def test_the_check_passes_a_fit_before_the_cutoff_and_fails_one_after() -> None:
    frozen = EDGES["momentum_12_1"].frozen_from
    assert frozen is not None
    cutoff = purge_cutoff(frozen, 20)
    check_scorer(
        "edge_score_momentum_12_1", _table(_fit("momentum_12_1", date(2026, 1, 30))), EDGES
    )
    for through in (cutoff, frozen):  # inside the embargo, or in the frozen period itself
        with pytest.raises(AssertionError, match="purge cutoff"):
            check_scorer("edge_score_momentum_12_1", _table(_fit("momentum_12_1", through)), EDGES)
    unknown = replace(_fit("nope", date(2026, 1, 30)))
    with pytest.raises(AssertionError, match="no edge document"):
        check_scorer("edge_score_nope", _table(unknown), EDGES)


# --- ED7b: every model screener's score is a scorer fitted before its edge's purge cutoff ---------

MODEL_FILES = sorted((REPO_ROOT / "config" / "site" / "presets" / "screeners").glob("*/v*.toml"))
MODELS = {
    f"{p.parent.name}/{p.stem}": doc
    for p in MODEL_FILES
    if (doc := tomllib.loads(p.read_text())).get("impl") == "model"
}


def check_model_screener(
    name: str, doc: Mapping[str, Any], scores: Mapping[str, Any], edges: Mapping[str, Any]
) -> None:
    """``doc``'s ``score`` is a fitted ``edge_score_<edge>`` of ``scores`` (``check_scorer``:
    fitted_through before the purge cutoff), and that edge lists the screener."""
    feature = str(doc["score"]).removeprefix("feature.")
    assert feature in scores, f"{name}: no fitted scorer {feature!r} in edge_scores.toml"
    check_scorer(feature, scores[feature], edges)
    edge = edges[feature.removeprefix(PREFIX)]
    assert doc["id"] in edge.screeners, f"{name}: edge {edge.id} does not list {doc['id']}"


@pytest.mark.parametrize("name", sorted(MODELS))
def test_every_model_screener_scores_with_a_scorer_fitted_before_the_cutoff(name: str) -> None:
    check_model_screener(name, MODELS[name], SCORES, EDGES)


def test_the_model_check_passes_a_fitted_score_and_fails_an_unfitted_or_late_one() -> None:
    edge = EDGES["momentum_12_1"]
    listed = replace(edge, screeners=(*edge.screeners, "mom_model"))
    edges = {**EDGES, edge.id: listed}
    doc = {"id": "mom_model", "impl": "model", "score": "feature.edge_score_momentum_12_1"}
    good = {"edge_score_momentum_12_1": _table(_fit("momentum_12_1", date(2026, 1, 30)))}
    check_model_screener("m", doc, good, edges)
    with pytest.raises(AssertionError, match="no fitted scorer"):
        check_model_screener("m", doc, {}, edges)  # a score nobody fitted
    late = {"edge_score_momentum_12_1": _table(_fit("momentum_12_1", date(2026, 3, 31)))}
    with pytest.raises(AssertionError, match="purge cutoff"):
        check_model_screener("m", doc, late, edges)
    with pytest.raises(AssertionError, match="does not list"):
        check_model_screener("m", doc, good, EDGES)
