"""`scripts/worktree.sh --dry-run`: reports the plan and changes nothing."""

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "worktree.sh"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), "--dry-run", *args], capture_output=True, text=True, check=False
    )


def test_create_plan_slugs_the_branch_and_pins_pythonpath() -> None:
    out = _run("feat/my-thing")
    assert out.returncode == 0, out.stderr
    assert "worktree add -b feat/my-thing" in out.stdout
    assert "algo-trading-feat-my-thing" in out.stdout
    assert "origin/main" in out.stdout
    assert "ln -s" in out.stdout and ".venv" in out.stdout
    assert "PYTHONPATH=" in out.stdout and "/src:" in out.stdout
    assert "npm ci" in out.stdout


def test_create_plan_uses_the_given_base() -> None:
    assert "origin/release" in _run("x", "release").stdout


def test_remove_needs_an_existing_worktree() -> None:
    out = _run("--remove", "no-such-branch-xyz")
    assert out.returncode == 1
    assert "no worktree" in out.stderr


def test_usage_error_without_branch() -> None:
    assert _run().returncode == 2


def test_create_plan_installs_node_modules_and_never_links_them() -> None:
    # `make check` runs `npm ci`; through a symlink that empties the main checkout's install.
    out = _run("feat/my-thing").stdout
    assert "npm ci --prefix" in out and "algo-trading-feat-my-thing/apps/web" in out
    assert not any("ln -s" in line and "node_modules" in line for line in out.splitlines())
