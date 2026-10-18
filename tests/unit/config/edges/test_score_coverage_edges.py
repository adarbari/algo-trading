"""EB E6: an edge whose screener's score exists only for some names (a feature with rows for
instruments with an event) gates its universe on that score, so every base name is scored: the
harness calls a session too thin to rank when under 80 percent of the base has a score
(``MIN_SCORE_COVERAGE``), and a short leg is then not measured at all."""

import tomllib

import pytest

from algotrade.config.edges.document import Edge
from algotrade.config.edges.loading import load_edges
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT

STORE = FileConfigStore(REPO_ROOT / "config", local=False)
SPARSE = ("insider_opportunistic_cluster_buys", "short_squeeze_days_to_cover")
EDGES = {e.id: e for e in load_edges(STORE) if e.id in SPARSE}


def _score_field(screener: str) -> str:
    path = REPO_ROOT / f"config/site/presets/screeners/{screener}/v1.toml"
    return str(tomllib.loads(path.read_text())["rank"]["tie_break"])


@pytest.mark.parametrize("edge", EDGES.values(), ids=list(EDGES))
def test_the_universe_requires_the_screeners_score(edge: Edge) -> None:
    assert edge.base == "universe" and len(edge.screeners) == 1
    field = _score_field(edge.screeners[0])
    gated = [r for r in edge.universe.where.rules() if r.field == field]  # type: ignore[union-attr]
    assert gated and gated[0].op == "gte", f"{edge.id}: gate the universe on {field}"
