"""Outcomes are quarantined (ADR 0053 decision 4): ``algotrade.data.outcomes`` is imported only
by ``algotrade.services.evaluation`` (and itself). This scans every module of the library and
the apps, so a screener, strategy, feature, page read or app that reached the future fails here
as well as in the import-linter contract it backs up."""

import ast
import tomllib
from pathlib import Path

from tests.conftest import REPO_ROOT

PROTECTED = "algotrade.data.outcomes"
ALLOWED = ("src/algotrade/data/outcomes/", "src/algotrade/services/evaluation/")
SCANNED = ("src/algotrade", "apps/api", "apps/backtest", "apps/ingestion", "libs")
CONTRACT = "Outcomes are quarantined: only services.evaluation reads them (ADR 0053)"


def _imports(path: Path) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
            out.update(f"{node.module}.{alias.name}" for alias in node.names)
    return out


def _reaches(module: str) -> bool:
    return module == PROTECTED or module.startswith(f"{PROTECTED}.")


def test_only_the_harness_imports_outcomes() -> None:
    offenders = []
    for root in SCANNED:
        for path in sorted((REPO_ROOT / root).rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if rel.startswith(ALLOWED) or "node_modules" in rel:
                continue
            if any(_reaches(m) for m in _imports(path)):
                offenders.append(rel)
    assert not offenders, f"only services/evaluation may import {PROTECTED}: {offenders}"


def test_the_import_contract_protects_outcomes() -> None:
    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    contracts = {c["name"]: c for c in config["tool"]["importlinter"]["contracts"]}
    contract = contracts[CONTRACT]
    assert contract["type"] == "protected"
    assert contract["protected_modules"] == [PROTECTED]
    assert contract["allowed_importers"] == ["algotrade.services.evaluation"]


def test_the_scan_sees_an_import() -> None:
    sample = REPO_ROOT / "src" / "algotrade" / "data" / "outcomes" / "__init__.py"
    assert any(_reaches(m) for m in _imports(sample))
