"""The bought option history is quarantined (ADR 0084 decision 3): ``algotrade.data.option_history``
is imported only by the ingestion app's import (``tasks/options_history``) and its verification
checks (``tasks/verification``), and only ingestion asks the environment for its store URL. No
evaluation, feature, screener, page read or API reaches a personal-licence history directly."""

import ast
import tomllib
from pathlib import Path

from tests.conftest import REPO_ROOT

PROTECTED = "algotrade.data.option_history"
ALLOWED = (
    "src/algotrade/data/option_history/",
    "apps/ingestion/algotrade_ingestion/tasks/options_history/",
    "apps/ingestion/algotrade_ingestion/tasks/verification/",
)
SCANNED = ("src/algotrade", "apps/api", "apps/backtest", "apps/ingestion", "libs")
CONTRACT = "Option history is quarantined: only ingestion reads it (ADR 0084)"
GETTER = "option_history_url"
GETTER_HOMES = ("src/algotrade/config/env.py", "apps/ingestion/")


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


def _files() -> list[tuple[str, Path]]:
    out = []
    for root in SCANNED:
        for path in sorted((REPO_ROOT / root).rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if "node_modules" not in rel:
                out.append((rel, path))
    return out


def test_only_the_ingestion_import_and_checks_read_the_history() -> None:
    offenders = [
        rel
        for rel, path in _files()
        if not rel.startswith(ALLOWED) and any(_reaches(m) for m in _imports(path))
    ]
    assert not offenders, f"only ingestion's import and checks may import {PROTECTED}: {offenders}"


def test_only_ingestion_asks_the_environment_for_the_history_url() -> None:
    offenders = [
        rel
        for rel, path in _files()
        if not rel.startswith(GETTER_HOMES) and GETTER in path.read_text()
    ]
    assert not offenders, f"only apps/ingestion calls env.{GETTER}: {offenders}"


def test_the_import_contract_protects_the_history() -> None:
    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    contracts = {c["name"]: c for c in config["tool"]["importlinter"]["contracts"]}
    contract = contracts[CONTRACT]
    assert contract["type"] == "protected"
    assert contract["protected_modules"] == [PROTECTED]
    assert set(contract["allowed_importers"]) == {
        "algotrade_ingestion.tasks.options_history",
        "algotrade_ingestion.tasks.verification",
    }


def test_the_scan_sees_an_import() -> None:
    sample = REPO_ROOT / "apps/ingestion/algotrade_ingestion/tasks/options_history/importer.py"
    assert any(_reaches(m) for m in _imports(sample))
