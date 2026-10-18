"""The Guide's Edges read objects are session-free and show no harness result (ADR 0051;
docs/ui/guide.md, "Edges"): ``services/read/guide/edges`` reads the edge documents and the site
configs only, so it never imports the session, a store, the evaluation read model or the
outcomes, and never touches ``ctx.session`` or ``ctx.reader``. A live number on a Guide page
would make it depend on the day it is read."""

import ast
from pathlib import Path

import pytest

from tests.conftest import REPO_ROOT

FOLDER = REPO_ROOT / "src" / "algotrade" / "services" / "read" / "guide" / "edges"
FORBIDDEN_IMPORTS = (
    "algotrade.services.read.session",
    "algotrade.services.read.evaluation",
    "algotrade.services.read.edge_desk",
    "algotrade.services.read.edge_evidence",
    "algotrade.services.read.edge_ledger",
    "algotrade.services.read.screens",
    "algotrade.services.read.instruments",
    "algotrade.services.read.values",
    "algotrade.services.evaluation",
    "algotrade.data",
    "algotrade.storage.tables",
    "algotrade.storage.backends",
)
FORBIDDEN_ATTRIBUTES = ("session", "reader")  # ctx.session, ctx.reader


def _files() -> list[Path]:
    return sorted(FOLDER.glob("*.py"))


def _imports(tree: ast.AST) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            found += [f"{node.module}.{a.name}" for a in node.names] + [node.module]
    return found


@pytest.mark.parametrize("path", _files(), ids=lambda p: p.name)
def test_the_edges_folder_imports_no_session_store_or_result(path: Path) -> None:
    tree = ast.parse(path.read_text())
    bad = [i for i in _imports(tree) if i.startswith(FORBIDDEN_IMPORTS)]
    assert bad == [], f"{path.name}: the Guide shows no live number; it imports {bad}"


@pytest.mark.parametrize("path", _files(), ids=lambda p: p.name)
def test_the_edges_folder_reads_no_session_or_reader_attribute(path: Path) -> None:
    tree = ast.parse(path.read_text())
    bad = sorted(
        {
            n.attr
            for n in ast.walk(tree)
            if isinstance(n, ast.Attribute)
            and n.attr in FORBIDDEN_ATTRIBUTES
            and isinstance(n.value, ast.Name)
            and n.value.id == "ctx"
        }
    )
    assert bad == [], f"{path.name}: ctx.{bad} makes a Guide page depend on the day it is read"


def test_the_folder_is_not_empty() -> None:
    assert len(_files()) >= 5
