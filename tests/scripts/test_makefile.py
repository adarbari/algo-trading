"""Makefile guards: `make install` refuses to sync through a worktree's `.venv` link."""

import shutil
import subprocess
from pathlib import Path

import pytest

MAKEFILE = Path(__file__).resolve().parents[2] / "Makefile"


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
