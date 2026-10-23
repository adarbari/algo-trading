"""The edge harness's detail tables have one writer and one reader each:

- ``results/edge_trades`` (ADR 0064 decision 3) is named only by
  ``services/evaluation/cross_section/detail/`` (which frames it), the run reader
  ``services/read/evaluation/runs.py`` (the one page read, which applies ``oos_hidden`` and the
  licence redaction) and the schema that declares it; the purge task reaches it through the
  schema's spec and the run reader's keep list, never by name.
- ``results/edge_verdict`` (ADR 0053 amendment 2026-10-22) is named only by that same ``detail/``
  (the one framer: the edge-eval publish and the edge-verdicts task reach it through it, and ML
  never does, ADR 0053 decision 8), its one reader ``services/read/evaluation/verdict/stored.py``
  (a row only on a matching fingerprint, else the live judge) and the schema that declares it."""

import ast
from pathlib import Path

import pytest

from tests.conftest import REPO_ROOT

DETAIL = "src/algotrade/services/evaluation/cross_section/detail/"
SCHEMA = "src/algotrade/storage/tables/edge_schemas.py"
RUNS = "src/algotrade/services/read/evaluation/runs.py"
STORED = "src/algotrade/services/read/evaluation/verdict/stored.py"
# table -> (the name of its run reader file, the modules allowed to name it)
TABLES = {
    "edge_trades": (RUNS, (DETAIL, RUNS, SCHEMA)),
    "edge_verdict": (STORED, (DETAIL, STORED, SCHEMA)),
}
SCANNED = ("src/algotrade", "apps/api", "apps/backtest", "apps/ingestion", "libs")


def _names(path: Path) -> set[str]:
    return {
        n.value
        for n in ast.walk(ast.parse(path.read_text()))
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    }


@pytest.mark.parametrize("name", TABLES)
def test_only_its_writer_and_reader_name_the_table(name: str) -> None:
    _, allowed = TABLES[name]
    offenders = []
    for root in SCANNED:
        for path in sorted((REPO_ROOT / root).rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if rel.startswith(allowed) or "node_modules" in rel:
                continue
            if {f"results/{name}", name} & _names(path):
                offenders.append(rel)
    assert not offenders, f"only {allowed} may name results/{name}: {offenders}"


@pytest.mark.parametrize("name", TABLES)
def test_the_scan_sees_the_reader_and_the_schema(name: str) -> None:
    reader, _ = TABLES[name]
    assert name in _names(REPO_ROOT / reader) or f"results/{name}" in _names(REPO_ROOT / reader)
    assert f"results/{name}" in _names(REPO_ROOT / SCHEMA)


@pytest.mark.parametrize("name", TABLES)
def test_the_table_is_registered_as_not_every_session(name: str) -> None:
    text = (REPO_ROOT / "architecture/tables.toml").read_text()
    block = text.split(f'name = "results/{name}"')[1].split("[[table]]")[0]
    assert "per_session = false" in block
