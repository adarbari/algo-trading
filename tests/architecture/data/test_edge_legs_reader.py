"""The stored legs are private to the harness's ``legs`` folder (ADR 0063): a leg holds values
derived from outcomes and from what a screen read, so the table ``results/edge_legs`` is named
only by ``services/evaluation/cross_section/legs/`` (and the one schema that declares it), and no
ingestion task, page read or other service reaches it. The ownership gate's ``edge-leg-reuse``
rule is the same check on the string; this scans for the table's name too."""

import ast
from pathlib import Path

from tests.conftest import REPO_ROOT

TABLE = "results/edge_legs"
NAME = "edge_legs"
ALLOWED = (
    "src/algotrade/services/evaluation/cross_section/legs/",
    "src/algotrade/storage/tables/schemas.py",  # declares the one schema
)
SCANNED = ("src/algotrade", "apps/api", "apps/backtest", "apps/ingestion", "libs")


def _names(path: Path) -> set[str]:
    """Every string literal of a module, docstrings included: a name in prose is no use."""
    return {
        n.value
        for n in ast.walk(ast.parse(path.read_text()))
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    }


def test_only_the_legs_folder_names_the_table() -> None:
    offenders = []
    for root in SCANNED:
        for path in sorted((REPO_ROOT / root).rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if rel.startswith(ALLOWED) or "node_modules" in rel:
                continue
            if {TABLE, NAME} & _names(path):
                offenders.append(rel)
    assert not offenders, f"only cross_section/legs may name {TABLE}: {offenders}"


def test_the_scan_sees_the_store_and_the_schema() -> None:
    legs = REPO_ROOT / "src/algotrade/services/evaluation/cross_section/legs/store.py"
    assert NAME in _names(legs)
    assert TABLE in _names(REPO_ROOT / "src/algotrade/storage/tables/schemas.py")


def test_the_table_is_registered_as_not_every_session() -> None:
    text = (REPO_ROOT / "architecture/tables.toml").read_text()
    block = text.split(f'name = "{TABLE}"')[1].split("[[table]]")[0]
    assert "per_session = false" in block  # written for an evaluation's sessions, not nightly
