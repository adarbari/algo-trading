"""A learned screener is promoted only on frozen-period evidence (ADR 0053 amendment, ED7c).
An edge's ``[implementation] promoted`` names a model screener it lists; the edge is evidenced
or live and cites its canonical run (``[evidence]``, split = frozen_from); the edge commits the
frozen-slice numbers it rests on (``[[implementation.compared]]``: the model and every rule
screener, at every horizon); and ``promotion_problems`` (lift and decile spread strictly higher
at every horizon, the quality bar's sessions on every row) is empty over those numbers. The
read model checks the same function against the cited run's stored rows before it honours
``promoted`` (``load_promotion``), so a committed number that the run does not show is
reported NOT promoted. No site edge is promoted today."""

from dataclasses import replace

import pytest

from algotrade.config.edges.document import Compared, Edge, Evidence
from algotrade.config.edges.loading import load_edges
from algotrade.config.strategy.schema import MODEL_IMPL
from algotrade.config.user import SITE_USER, UserContext
from algotrade.services.configs import resolve_config
from algotrade.services.read.evaluation.promotion import (
    committed_rows,
    promotion_problems,
    rule_screeners,
)
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT

STORE = FileConfigStore(REPO_ROOT / "config", local=False)
EDGES = load_edges(STORE)
CITING = ("evidenced", "live")


def check_promotion(edge: Edge, impl: "dict[str, str]", rules: "list[str]") -> None:
    """Raises ``AssertionError`` naming what the promotion lacks."""
    assert edge.promoted is not None
    assert impl[edge.promoted] == MODEL_IMPL, f"{edge.id}: {edge.promoted} is not a model screener"
    assert edge.status in CITING, f"{edge.id}: a promoted edge is evidenced or live"
    assert edge.evidence is not None, f"{edge.id}: a promotion cites the run that beat the rules"
    assert edge.evidence.split_from == edge.frozen_from, f"{edge.id}: the run is not the frozen one"
    problems = promotion_problems(edge, committed_rows(edge), rules)
    assert not problems, f"{edge.id}: the committed numbers do not show it: {problems}"


@pytest.mark.parametrize("edge", [e for e in EDGES if e.promoted], ids=lambda e: e.id)
def test_a_promoted_edge_commits_frozen_numbers_that_beat_its_rule_screeners(edge: Edge) -> None:
    impl = {s: resolve_config(STORE, s, UserContext(SITE_USER)).config.impl for s in edge.screeners}
    check_promotion(edge, impl, rule_screeners(edge, STORE))


def _promoted() -> Edge:
    base = next(e for e in EDGES if e.id == "momentum_12_1")
    assert base.frozen_from is not None
    h = base.outcome.horizon_sessions
    numbers = tuple(
        Compared(x, s, lift, spread, 45, 45)
        for x in h
        for s, lift, spread in (("momentum_12_1", 1.2, 0.01), ("mom_model", 1.3, 0.02))
    )
    return replace(
        base,
        screeners=("momentum_12_1", "mom_model"),
        promoted="mom_model",
        status="evidenced",
        evidence=Evidence("run-1", base.frozen_from),
        compared=numbers,
    )


def test_the_check_refuses_a_promotion_without_the_evidence() -> None:
    ok = _promoted()
    impl = {"momentum_12_1": "rules", "mom_model": "model"}
    rules = ["momentum_12_1"]
    check_promotion(ok, impl, rules)
    weak = tuple(replace(c, lift=1.1) if c.screener == "mom_model" else c for c in ok.compared)
    thin = tuple(replace(c, sessions=39) if c.screener == "mom_model" else c for c in ok.compared)
    cases = {
        "not a model screener": replace(ok, promoted="momentum_12_1"),
        "evidenced or live": replace(ok, status="candidate"),
        "cites the run": replace(ok, evidence=None),
        "not the frozen one": replace(
            ok,
            evidence=replace(ok.evidence, split_from=ok.frozen_from.replace(year=2025)),  # type: ignore[union-attr, arg-type]
        ),
        "do not show it": replace(ok, compared=()),  # nothing committed
    }
    for message, edge in cases.items():
        with pytest.raises(AssertionError, match=message):
            check_promotion(edge, impl, rules)
    for edge in (replace(ok, compared=weak), replace(ok, compared=thin)):
        with pytest.raises(AssertionError, match="do not show it"):
            check_promotion(edge, impl, rules)
    with pytest.raises(AssertionError, match="do not show it"):
        check_promotion(ok, impl, [])  # no rule screener to have beaten
