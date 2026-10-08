"""Learned scorers never see the frozen period (ADR 0053 amendment, ED7): every
``edge_score_<edge>`` expression feature in ``config/site/features/edge_scores.toml`` names an
edge that declares ``[scorer]`` features and a ``frozen_from``, and records ``fitted_through``
strictly before it; the scorer reads exactly the features the document declares."""

import re
import tomllib
from datetime import date

import pytest

from algotrade.config.edges.loading import load_edges
from algotrade.services.evaluation.training.render import PREFIX, expression_name
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT

STORE = FileConfigStore(REPO_ROOT / "config", local=False)
EDGES = {e.id: e for e in load_edges(STORE)}
FILE = REPO_ROOT / "config" / "site" / "features" / "edge_scores.toml"
SCORES = tomllib.loads(FILE.read_text()) if FILE.exists() else {}
FITTED = re.compile(r"fitted_through=(\d{4}-\d{2}-\d{2})")


def test_the_scorer_file_is_not_empty_or_absent() -> None:
    assert SCORES, f"{FILE} is the file `algotrade-backtest fit-edge-scorer` writes"


@pytest.mark.parametrize("name", sorted(SCORES))
def test_a_scorer_was_fitted_before_its_edges_frozen_period(name: str) -> None:
    assert name.startswith(PREFIX), f"{name}: a learned scorer is named {PREFIX}<edge>"
    edge = EDGES.get(name.removeprefix(PREFIX))
    assert edge is not None, f"{name}: no edge document {name.removeprefix(PREFIX)!r}"
    assert edge.frozen_from is not None, f"{edge.id}: a scorer needs frozen_from"
    found = FITTED.search(SCORES[name]["description"])
    assert found, f"{name}: the description must record fitted_through=YYYY-MM-DD"
    assert date.fromisoformat(found.group(1)) < edge.frozen_from, (
        f"{name}: fitted_through {found.group(1)} is not before frozen_from {edge.frozen_from}"
    )


@pytest.mark.parametrize("name", sorted(SCORES))
def test_a_scorer_reads_exactly_the_documents_features(name: str) -> None:
    edge = EDGES[name.removeprefix(PREFIX)]
    assert edge.scorer_features, f"{edge.id}: a scorer needs [scorer] features"
    expected = {expression_name(f) for f in edge.scorer_features}
    used = set(re.findall(r"[a-z_0-9]+\.[a-z_0-9]+", SCORES[name]["expr"]))
    assert used == expected, f"{name} was fitted on other features than {edge.id} declares now"
