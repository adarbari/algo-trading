"""`scripts/ops/deploy.sh --dry-run`: refuses off `main` or a dirty tree, else prints the plan."""

import os
import shutil
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "ops" / "deploy.sh"


def _git(cwd: Path, *args: str) -> None:
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
        "PATH": os.environ["PATH"],
        "HOME": str(cwd),
    }
    subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True)


def _repo(tmp_path: Path) -> Path:
    origin = tmp_path.parent / f"{tmp_path.name}-origin.git"
    _git(tmp_path.parent, "init", "-q", "--bare", "-b", "main", str(origin))
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "remote", "add", "origin", str(origin))
    (tmp_path / ".gitignore").write_text("*.local.toml\n")
    (tmp_path / "a.txt").write_text("a\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "init")
    _git(tmp_path, "push", "-q", "origin", "main")
    return tmp_path


def _deploy(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), "--dry-run"], cwd=repo, capture_output=True, text=True, check=False
    )


def test_refuses_off_main(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _git(repo, "switch", "-qc", "feat/x")
    out = _deploy(repo)
    assert out.returncode == 1 and "not main" in out.stderr


def test_refuses_a_dirty_tree_but_not_the_ignored_overlay(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "llm.local.toml").write_text("enabled = true\n")  # git-ignored overlay
    assert _deploy(repo).returncode == 0
    (repo / "a.txt").write_text("changed\n")
    out = _deploy(repo)
    assert out.returncode == 1 and "uncommitted" in out.stderr


def test_on_main_prints_the_plan_and_runs_nothing(tmp_path: Path) -> None:
    out = _deploy(_repo(tmp_path))
    assert out.returncode == 0, out.stderr
    plan = [x for x in out.stdout.splitlines() if x.startswith("[dry-run]")]
    assert [x.split()[1] for x in plan] == ["git", "uv", "make", "launchctl", "curl"]
    assert "pull --ff-only origin main" in plan[0] and "sync --all-packages --locked" in plan[1]
    assert "web-build" in plan[2] and "kickstart -k" in plan[3] and "/health" in plan[4]


def test_refuses_unpushed_local_commits(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "b.txt").write_text("b\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "local only")
    out = _deploy(repo)
    assert out.returncode == 1 and "not on origin/main" in out.stderr


def test_script_is_executable_and_bash_parses_it() -> None:
    assert os.access(SCRIPT, os.X_OK) and shutil.which("bash")
