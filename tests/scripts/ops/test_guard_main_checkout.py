"""`scripts/ops/guard_main_checkout.py`: the PreToolUse hook keeps the main checkout on main.
Fed sample hook JSON against a temp main repo and a linked worktree of it."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "ops" / "guard_main_checkout.py"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


@pytest.fixture
def repos(tmp_path: Path) -> tuple[Path, Path]:
    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init", "-b", "main")
    (main / "f.txt").write_text("x")
    _git(main, "add", ".")
    _git(main, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "i")
    wt = tmp_path / "wt"
    _git(main, "worktree", "add", "-b", "feat", str(wt))
    return main, wt


def _hook(command: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    payload = json.dumps({"tool_name": "Bash", "cwd": str(cwd), "tool_input": {"command": command}})
    return subprocess.run(
        [sys.executable, str(SCRIPT)], input=payload, capture_output=True, text=True, check=False
    )


@pytest.mark.parametrize(
    "command",
    [
        "git checkout -b perf/x",
        "git checkout -B perf/x origin/main",
        "git switch -c perf/x",
        "git switch --create perf/x",
        "git checkout feat",
        "git switch feat",
        "git -c core.x=1 checkout -b a",
        "FOO=1 git checkout -b a",
        "git status && git checkout -b a",
        "git branch a && git checkout a",
    ],
)
def test_blocks_branch_changes_in_the_main_checkout(repos: tuple[Path, Path], command: str) -> None:
    main, wt = repos
    r = _hook(command, main)
    assert r.returncode == 2 and "scripts/worktree.sh" in r.stderr
    # the same command is fine from a linked worktree
    assert _hook(command, wt).returncode == 0 if "git branch a" not in command else True


def test_blocks_through_cd_prefix_and_git_dash_c(repos: tuple[Path, Path]) -> None:
    main, wt = repos
    assert _hook(f"cd {main} && git checkout -b a", wt).returncode == 2
    assert _hook(f"git -C {main} switch -c a", wt).returncode == 2
    assert _hook(f"cd {wt} && git checkout -b a", main).returncode == 0
    assert _hook(f"git -C {wt} checkout -b a", main).returncode == 0


@pytest.mark.parametrize(
    "command",
    [
        "git checkout main",
        "git switch main",
        "git pull --ff-only origin main",
        "git checkout -- f.txt",
        "git checkout HEAD -- f.txt",
        "git checkout f.txt",
        "git status",
        "ls",
        "git checkout 'unterminated",
    ],
)
def test_allows_main_pull_and_file_checkouts(repos: tuple[Path, Path], command: str) -> None:
    assert _hook(command, repos[0]).returncode == 0


def test_ignores_malformed_input() -> None:
    r = subprocess.run(
        [sys.executable, str(SCRIPT)], input="not json", capture_output=True, text=True, check=False
    )
    assert r.returncode == 0
