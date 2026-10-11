"""The trade ledger has one writer and one reader (ADR 0064 decision 3): ``results/edge_trades``
is named only by ``services/evaluation/cross_section/detail/`` (which frames it), the run reader
``services/read/evaluation/runs.py`` (the one page read, which applies ``oos_hidden`` and the
licence redaction) and the schema that declares it; the purge task reaches it through the
schema's spec and the run reader's keep list, never by name."""

import ast
from pathlib import Path

from tests.conftest import REPO_ROOT

TABLE = "results/edge_trades"
NAME = "edge_trades"
ALLOWED = (
    "src/algotrade/services/evaluation/cross_section/detail/",
    "src/algotrade/services/read/evaluation/runs.py",
    "src/algotrade/storage/tables/edge_schemas.py",
)
SCANNED = ("src/algotrade", "apps/api", "apps/backtest", "apps/ingestion", "libs")


def _names(path: Path) -> set[str]:
    return {
        n.value
        for n in ast.walk(ast.parse(path.read_text()))
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    }


def test_only_the_writer_and_the_run_reader_name_the_ledger() -> None:
    offenders = []
    for root in SCANNED:
        for path in sorted((REPO_ROOT / root).rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if rel.startswith(ALLOWED) or "node_modules" in rel:
                continue
            if {TABLE, NAME} & _names(path):
                offenders.append(rel)
    assert not offenders, f"only detail/ and runs.py may name {TABLE}: {offenders}"


def test_the_scan_sees_the_reader_and_the_schema() -> None:
    assert NAME in _names(REPO_ROOT / "src/algotrade/services/read/evaluation/runs.py")
    assert TABLE in _names(REPO_ROOT / "src/algotrade/storage/tables/edge_schemas.py")


def test_the_ledger_is_registered_as_not_every_session() -> None:
    text = (REPO_ROOT / "architecture/tables.toml").read_text()
    block = text.split(f'name = "{TABLE}"')[1].split("[[table]]")[0]
    assert "per_session = false" in block
