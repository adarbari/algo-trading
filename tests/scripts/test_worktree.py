"""`scripts/worktree.sh --dry-run`: reports the plan and changes nothing; `--prune-merged`."""

import os
import subprocess
from pathlib import Path

import pytest

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


# --prune-merged, on a temp repo with a stub `gh` (CI never calls the network).


def _git(cwd: Path, *args: str) -> str:
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
        "PATH": os.environ["PATH"],
        "HOME": str(cwd),
    }
    return subprocess.run(
        ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def prune_repo(tmp_path: Path) -> dict[str, Path]:
    """A main checkout plus worktrees: merged, merged-but-dirty, open PR, no PR, extra commit."""
    main = tmp_path / "algo-trading"
    main.mkdir()
    _git(main, "init", "-q", "-b", "main")
    (main / "f.txt").write_text("x")
    _git(main, "add", "f.txt")
    _git(main, "commit", "-q", "-m", "init")
    paths = {"main": main}
    for name, where in {
        "merged": "algo-trading-merged",
        "dirty": "algo-trading-dirty",
        "open": "algo-wt-open",
        "nopr": "algo-trading-nopr",
        "extra": "algo-trading-extra",
        "agent": "algo-trading/.claude/worktrees/agent-1",
        "other": "elsewhere",
    }.items():
        wt = tmp_path / where
        _git(main, "worktree", "add", "-q", "-b", f"feat/{name}", str(wt))
        paths[name] = wt
    (paths["dirty"] / "f.txt").write_text("changed")
    (paths["extra"] / "g.txt").write_text("g")
    _git(paths["extra"], "add", "g.txt")
    _git(paths["extra"], "commit", "-q", "-m", "after the PR")
    merged = {
        n: _git(main, "rev-parse", f"feat/{n}") for n in ("merged", "dirty", "agent", "other")
    }
    merged["extra"] = _git(main, "rev-parse", "main")  # the PR's last commit is before ours
    stub = tmp_path / "bin" / "gh"
    stub.parent.mkdir()
    rows = "".join(f"feat/{n}\t{oid}\n" for n, oid in merged.items())
    stub.write_text(
        f"#!/bin/sh\ncase \"$*\" in\n  *merged*) printf '%s' '{rows}' ;;\n"
        "  *) printf 'feat/open\\n' ;;\nesac\n"
    )
    stub.chmod(0o755)
    return paths


def _prune(repo: dict[str, Path], *flags: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PATH": f"{repo['main'].parent / 'bin'}:{os.environ['PATH']}"}
    return subprocess.run(
        ["bash", str(SCRIPT), *flags, "--prune-merged"],
        cwd=repo["main"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_prune_merged_dry_run_reports_and_removes_nothing(prune_repo: dict[str, Path]) -> None:
    out = _prune(prune_repo, "--dry-run")
    assert out.returncode == 0, out.stderr
    assert f"would remove {prune_repo['merged'].resolve()} (feat/merged)" in out.stdout
    assert f"would remove {prune_repo['agent'].resolve()} (feat/agent)" in out.stdout
    assert "(feat/dirty): uncommitted changes" in out.stdout
    assert "(feat/open): open PR" in out.stdout
    assert "(feat/nopr): no merged PR" in out.stdout
    assert "(feat/extra): commits after the merged PR" in out.stdout
    assert "would remove 2 worktree(s), kept 4" in out.stdout
    assert prune_repo["merged"].exists() and prune_repo["agent"].exists()


def test_prune_merged_removes_clean_merged_worktrees_and_their_branches(
    prune_repo: dict[str, Path],
) -> None:
    out = _prune(prune_repo)
    assert out.returncode == 0, out.stderr
    assert "removed 2 worktree(s), kept 4" in out.stdout
    main = prune_repo["main"]
    assert not prune_repo["merged"].exists() and not prune_repo["agent"].exists()
    for kept in ("dirty", "open", "nopr", "extra", "other"):
        assert prune_repo[kept].exists()
    branches = _git(main, "branch", "--format=%(refname:short)").split()
    assert "feat/merged" not in branches and "feat/agent" not in branches
    assert {"main", "feat/dirty", "feat/open", "feat/nopr", "feat/extra"} <= set(branches)
    assert main.exists()


def test_prune_merged_never_touches_the_current_worktree(prune_repo: dict[str, Path]) -> None:
    env = {**os.environ, "PATH": f"{prune_repo['main'].parent / 'bin'}:{os.environ['PATH']}"}
    out = subprocess.run(
        ["bash", str(SCRIPT), "--dry-run", "--prune-merged"],
        cwd=prune_repo["merged"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert "(feat/merged): the current worktree" in out.stdout


def test_prune_merged_takes_no_branch() -> None:
    assert _run("--prune-merged", "feat/x").returncode == 2
