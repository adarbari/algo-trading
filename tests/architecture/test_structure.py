"""Structural rules the codebase must keep. These complement import-linter contracts."""

import ast
import re
import subprocess
import sys
from pathlib import Path

from tests.conftest import REPO_ROOT

SRC = REPO_ROOT / "src" / "algotrade"
LAYERS = sorted(p.name for p in SRC.iterdir() if p.is_dir() and not p.name.startswith("_"))


def test_file_length_limit() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/check_file_length.py"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert proc.returncode == 0, proc.stdout


def test_every_layer_has_unit_tests() -> None:
    missing = [
        layer for layer in LAYERS
        if layer != "cli" and not any((REPO_ROOT / "tests" / "unit" / layer).glob("test_*.py"))
    ]  # fmt: skip
    assert not missing, f"layers without unit tests: {missing}"


def test_every_layer_is_documented() -> None:
    architecture = (REPO_ROOT / "docs" / "architecture.md").read_text()
    undocumented = [layer for layer in LAYERS if f"`{layer}/`" not in architecture]
    assert not undocumented, f"add these layers to docs/architecture.md: {undocumented}"


def test_every_module_has_a_docstring() -> None:
    missing = []
    for path in SRC.rglob("*.py"):
        if path.name == "__main__.py":
            continue
        if ast.get_docstring(ast.parse(path.read_text())) is None:
            missing.append(str(path.relative_to(REPO_ROOT)))
    assert not missing, f"modules need a docstring explaining their responsibility: {missing}"


# ADR 0018: equity ids come from the id rule (core) or the symbol resolver, never ad hoc.
_ADHOC_ID = re.compile(r"""f?["']EQ:|AssetClass\.EQUITY\s*,|\bequity_id\(""")
_ID_OWNERS = {
    "src/algotrade/core/instruments.py",
    "src/algotrade/storage/resolver.py",
    "apps/ingestion/algotrade_ingestion/jobs/instrument_ids.py",
}


def test_equity_ids_are_built_only_by_the_id_rule_and_resolver() -> None:
    offenders = []
    for root in (REPO_ROOT / "src", REPO_ROOT / "apps"):
        for path in root.rglob("*.py"):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if rel in _ID_OWNERS or ".venv" in rel:
                continue
            code = [
                line for line in path.read_text().splitlines() if not line.lstrip().startswith("#")
            ]
            offenders += [f"{rel}: {line.strip()}" for line in code if _ADHOC_ID.search(line)]
    assert not offenders, f"resolve symbols with SymbolResolver (ADR 0018): {offenders}"


def test_scripts_flag_long_files(tmp_path: Path) -> None:
    long_file = tmp_path / "big.py"
    long_file.write_text("x = 1\n" * 1001)
    proc = subprocess.run(
        [sys.executable, "scripts/check_file_length.py", str(long_file)],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert proc.returncode == 1
    assert "1001 lines" in proc.stdout
