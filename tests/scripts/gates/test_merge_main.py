"""`scripts/merge_main.sh`: generated-file conflicts take main's; anything else aborts the merge."""

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "merge_main.sh"
ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
    "PATH": os.environ["PATH"],
    "MERGE_MAIN_NO_REGEN": "1",
}


def _git(cwd: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env={**ENV, "HOME": str(cwd)},
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout


def _merge(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args], cwd=cwd, env={**ENV, "HOME": str(cwd)},
        capture_output=True, text=True, check=False,
    )  # fmt: skip


def _repo(tmp_path: Path, files: list[str], main_edit: str, branch_edit: str) -> Path:
    """origin (bare) + a clone on `feat`; each file in `files` is edited on both sides."""
    origin, work = tmp_path / "origin.git", tmp_path / "work"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    _git(tmp_path, "clone", "-q", str(origin), str(work))
    for f in files:
        (work / f).parent.mkdir(parents=True, exist_ok=True)
        (work / f).write_text("base\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-qm", "base")
    _git(work, "push", "-q", "origin", "HEAD:main")
    _git(work, "checkout", "-qb", "feat")
    for f in files:
        (work / f).write_text(branch_edit)
    _git(work, "commit", "-qam", "branch")
    _git(work, "checkout", "-q", "main")
    for f in files:
        (work / f).write_text(main_edit)
    _git(work, "commit", "-qam", "main")
    _git(work, "push", "-q", "origin", "main")
    _git(work, "checkout", "-q", "feat")
    return work


def test_generated_file_conflicts_take_mains_version(tmp_path: Path) -> None:
    files = ["apps/api/openapi.json", "docs/data/features.md", "shots/a.png"]
    work = _repo(tmp_path, files, "main side\n", "branch side\n")
    out = _merge(work)
    assert out.returncode == 0, out.stdout + out.stderr
    for f in files:
        assert (work / f).read_text() == "main side\n"
    assert "web-visual" in out.stdout
    assert _git(work, "status", "--porcelain", "--untracked-files=no") == ""
    assert "Merge" in _git(work, "log", "-1", "--format=%s")


def test_other_conflicts_abort_the_merge_and_are_listed(tmp_path: Path) -> None:
    work = _repo(tmp_path, ["apps/api/openapi.json", "src/mod.py"], "main side\n", "branch side\n")
    out = _merge(work)
    assert out.returncode == 1
    assert "src/mod.py" in out.stderr and "openapi.json" not in out.stderr
    assert _git(work, "status", "--porcelain", "--untracked-files=no") == ""
    assert (work / "src/mod.py").read_text() == "branch side\n"


def test_dry_run_prints_the_plan_and_changes_nothing(tmp_path: Path) -> None:
    work = _repo(tmp_path, ["src/mod.py"], "main side\n", "branch side\n")
    head = _git(work, "rev-parse", "HEAD")
    out = _merge(work, "--dry-run")
    assert out.returncode == 0
    assert "export_openapi.py" in out.stdout and "api:generate" in out.stdout
    assert _git(work, "rev-parse", "HEAD") == head
