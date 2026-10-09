"""The opt-in historical read (ADR 0053 amendment 2026-10-09) is used by the whole edge
evaluation and nowhere else, and every edge universe can take it: reads default to one session
(ADR 0036), so a read under ``services/evaluation`` that forgets ``historical=True`` leaves its
edges survivor-only, and a universe that reads ``optionable`` without a close and a dollar-volume
floor has no proxy for a delisted name."""

import ast
from dataclasses import replace

from algotrade.config.edges.loading import load_edges
from algotrade.config.user import UserContext
from algotrade.services.evaluation.cross_section.harness import edge_universe
from algotrade.services.evaluation.cross_section.historical import require_liquidity_rule
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT

READS = {"fields_view", "select", "screen_session"}
EVALUATION = REPO_ROOT / "src/algotrade/services/evaluation"


def test_every_read_in_the_evaluation_is_historical() -> None:
    offenders = []
    for path in sorted(EVALUATION.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name not in READS:
                continue
            flag = [k for k in node.keywords if k.arg == "historical"]
            if not (flag and ast.unparse(flag[0].value) == "True"):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno} {name}")
    assert not offenders, f"pass historical=True (edges would stay survivor-only): {offenders}"


def test_every_edge_universe_and_variant_carries_the_liquidity_floors() -> None:
    configs = FileConfigStore(REPO_ROOT / "config")
    user = UserContext("site")
    edges = load_edges(configs)
    assert len(edges) >= 5  # the site's edges were found
    for edge in edges:
        require_liquidity_rule(edge_universe(configs, user, edge))
        for variant in edge.variants:
            require_liquidity_rule(
                edge_universe(configs, user, replace(edge, universe=variant.universe))
            )
