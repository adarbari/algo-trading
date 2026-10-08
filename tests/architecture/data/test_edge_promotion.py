"""A learned screener is promoted only on frozen-period evidence (ADR 0053 amendment, ED7c):
an edge's ``[implementation] promoted`` names a model screener it lists, the edge is evidenced
or live and cites its canonical run (``[evidence]``, split = frozen_from), and the edge lists a
rule screener for the model to have beaten. That the cited run's frozen slice shows it
(lift and decile spread above every rule screener's, at every horizon) is
``services.read.evaluation.promotion.promotion_problems``, tested on stored rows. No site edge
is promoted today."""

from dataclasses import replace

import pytest

from algotrade.config.edges.document import Edge, Evidence
from algotrade.config.edges.loading import load_edges
from algotrade.config.strategy.schema import MODEL_IMPL
from algotrade.config.user import SITE_USER, UserContext
from algotrade.services.configs import resolve_config
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT

STORE = FileConfigStore(REPO_ROOT / "config", local=False)
EDGES = load_edges(STORE)
CITING = ("evidenced", "live")


def impl_of(screener: str) -> str:
    return resolve_config(STORE, screener, UserContext(SITE_USER)).config.impl


def check_promotion(edge: Edge, impl: "dict[str, str]") -> None:
    """Raises ``AssertionError`` naming what the promotion lacks."""
    assert edge.promoted is not None
    assert impl[edge.promoted] == MODEL_IMPL, f"{edge.id}: {edge.promoted} is not a model screener"
    assert edge.status in CITING, f"{edge.id}: a promoted edge is evidenced or live"
    assert edge.evidence is not None, f"{edge.id}: a promotion cites the run that beat the rules"
    assert edge.evidence.split_from == edge.frozen_from, f"{edge.id}: the run is not the frozen one"
    rules = [s for s in edge.screeners if s != edge.promoted and impl[s] != MODEL_IMPL]
    assert rules, f"{edge.id}: no rule screener to have beaten"


@pytest.mark.parametrize("edge", [e for e in EDGES if e.promoted], ids=lambda e: e.id)
def test_a_promoted_edge_cites_frozen_evidence_over_a_rule_screener(edge: Edge) -> None:
    check_promotion(edge, {s: impl_of(s) for s in edge.screeners})


def test_the_check_refuses_a_promotion_without_the_evidence() -> None:
    base = next(e for e in EDGES if e.id == "momentum_12_1")
    impl = {"momentum_12_1": "rules", "mom_model": "model"}
    ok = replace(
        base,
        screeners=("momentum_12_1", "mom_model"),
        promoted="mom_model",
        status="evidenced",
        evidence=Evidence("run-1", base.frozen_from),  # type: ignore[arg-type]
    )
    check_promotion(ok, impl)
    cases = {
        "not a model screener": replace(ok, promoted="momentum_12_1"),
        "evidenced or live": replace(ok, status="candidate"),
        "cites the run": replace(ok, evidence=None),
        "not the frozen one": replace(
            ok,
            evidence=replace(ok.evidence, split_from=ok.frozen_from.replace(year=2025)),  # type: ignore[union-attr, arg-type]
        ),
        "no rule screener": replace(ok, screeners=("mom_model",)),
    }
    for message, edge in cases.items():
        with pytest.raises(AssertionError, match=message):
            check_promotion(edge, impl)
