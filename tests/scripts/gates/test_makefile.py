"""Makefile guards: `make install` refuses a linked `.venv`; `make check` gates by scope."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

MAKEFILE = Path(__file__).resolve().parents[3] / "Makefile"


def _install(cwd: Path) -> subprocess.CompletedProcess[str]:
    # UV / PY stubs: the guard runs first; when it passes, the stubs show what would have run.
    (cwd / "bin").mkdir(exist_ok=True)
    (cwd / "bin" / "pre-commit").symlink_to(shutil.which("true") or "/usr/bin/true")
    return subprocess.run(
        ["make", "-f", str(MAKEFILE), "install", "UV=echo uv", f"PY={cwd}/bin/python"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.skipif(shutil.which("make") is None, reason="needs make")
def test_install_refuses_a_linked_venv_and_names_the_worktree_way(tmp_path: Path) -> None:
    main_venv = tmp_path / "main" / ".venv"
    main_venv.mkdir(parents=True)
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / ".venv").symlink_to(main_venv)
    out = _install(wt)
    assert out.returncode != 0
    assert "uv sync" not in out.stdout
    assert "PYTHONPATH" in out.stderr and "worktree.env" in out.stderr


@pytest.mark.skipif(shutil.which("make") is None, reason="needs make")
def test_install_syncs_a_real_venv(tmp_path: Path) -> None:
    (tmp_path / ".venv").mkdir()
    out = _install(tmp_path)
    assert out.returncode == 0, out.stderr
    assert "uv sync --all-packages --locked" in out.stdout


def _dry_check(**vars: str) -> str:
    overrides = [f"{k}={v}" for k, v in vars.items()]
    # check-gates, not check: `check` takes the worktree lock and runs the sub-make, which a
    # dry run must not do; the scope variables are the same for both.
    out = subprocess.run(
        ["make", "-n", "check-gates", "PY=/nonexistent/python", *overrides],
        cwd=MAKEFILE.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    assert out.returncode == 0, out.stderr
    return out.stdout


@pytest.mark.skipif(shutil.which("make") is None, reason="needs make")
def test_check_runs_only_the_gates_of_the_changed_areas() -> None:
    web = _dry_check(CHECK_SCOPE="web")
    assert "npm run e2e" in web and "storybook:build" in web
    assert "pytest" not in web and "lint-imports" not in web
    python = _dry_check(CHECK_SCOPE="python")
    assert "pytest -n" in python and "lint-imports" in python
    assert "storybook:build" not in python and "playwright" not in python
    docs = _dry_check(CHECK_SCOPE="docs")
    assert "tests/architecture" in docs and "pytest -q -n" in docs
    assert "--cov" not in docs and "storybook:build" not in docs


@pytest.mark.skipif(shutil.which("make") is None, reason="needs make")
def test_full_runs_every_gate_without_asking_git() -> None:
    out = _dry_check(FULL="1")
    assert "pytest -n" in out and "--cov" in out and "lint-imports" in out
    assert "storybook:build" in out and "npm run e2e" in out
    assert "regime-scorecard" in out and "playwright.real.config.ts" in out


@pytest.mark.skipif(shutil.which("make") is None, reason="needs make")
def test_the_gates_run_in_parallel_under_one_sub_make() -> None:
    text = MAKEFILE.read_text()
    recipe = re.search(r"^check:.*?(?=^\S)", text, re.S | re.M)
    assert recipe and "-j$(CHECK_JOBS)" in recipe.group(0) and "check_lock.sh" in recipe.group(0)
