"""`scripts/check_numbering.py`: ADR numbers vs origin/main, web rule table 1..n, cited rules."""

import importlib.util
import os
import subprocess
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "check_numbering", Path(__file__).resolve().parents[3] / "scripts" / "check_numbering.py"
)
numbering = importlib.util.module_from_spec(SPEC)  # type: ignore[arg-type]
SPEC.loader.exec_module(numbering)  # type: ignore[union-attr]

ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
}  # fmt: skip


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=cwd, env={**os.environ, **ENV, "HOME": str(cwd)}, check=True,
        capture_output=True,
    )  # fmt: skip


def _adr(root: Path, name: str) -> None:
    (root / "docs/adr").mkdir(parents=True, exist_ok=True)
    (root / "docs/adr" / name).write_text("# adr\n")


def _repo(tmp_path: Path) -> Path:
    """A clone whose origin/main has ADR 0001 and 0002, checked out on a branch."""
    origin, work = tmp_path / "origin.git", tmp_path / "work"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    _git(tmp_path, "clone", "-q", str(origin), str(work))
    _adr(work, "0001-a.md")
    _adr(work, "0002-b.md")
    _git(work, "add", "-A")
    _git(work, "commit", "-qm", "base")
    _git(work, "push", "-q", "origin", "HEAD:main")
    _git(work, "checkout", "-qb", "feat")
    return work


def _commit(work: Path) -> None:
    _git(work, "add", "-A")
    _git(work, "commit", "-qm", "x")


def test_a_new_adr_reusing_a_taken_number_fails(tmp_path: Path) -> None:
    work = _repo(tmp_path)
    _adr(work, "0002-mine.md")
    _commit(work)
    problems, note = numbering.adr_collisions(work, fetch=False)
    assert note is None
    assert len(problems) == 1 and "0002-mine.md" in problems[0] and "0002-b.md" in problems[0]


def test_a_new_adr_with_a_free_number_and_existing_ones_pass(tmp_path: Path) -> None:
    work = _repo(tmp_path)
    _adr(work, "0003-mine.md")
    _commit(work)
    assert numbering.adr_collisions(work, fetch=False) == ([], None)


def test_offline_skips_the_adr_check_with_a_note(tmp_path: Path) -> None:
    work = _repo(tmp_path)
    _git(work, "remote", "set-url", "origin", str(tmp_path / "missing.git"))
    problems, note = numbering.adr_collisions(work)
    assert problems == [] and "skipped" in note


def _rules(root: Path, numbers: list[int], cited: str) -> None:
    (root / "docs/ui").mkdir(parents=True)
    rows = "\n".join(f"| {n} | rule | by |" for n in numbers)
    (root / "docs/ui/architecture.md").write_text(
        "## Rules and how they are enforced\n\n| # | Rule | Enforced by |\n|---|---|---|\n"
        f"{rows}\n\n## Next\n"
    )
    (root / "apps/web/lint-rules").mkdir(parents=True)
    (root / "apps/web/lint-rules/r.js").write_text(cited)


def test_rule_table_must_run_one_to_n_in_order(tmp_path: Path) -> None:
    _rules(tmp_path, [1, 2, 4], "message(1, 'x')")
    assert any("expected 1..3" in p for p in numbering.rule_problems(tmp_path))


def test_a_cited_rule_must_be_in_the_table(tmp_path: Path) -> None:
    _rules(tmp_path, [1, 2], "message(1, 'x'); message(\n  3, 'y'); '[ADR 0025 rule 2] z'")
    problems = numbering.rule_problems(tmp_path)
    assert len(problems) == 1 and "cites rule 3" in problems[0]


def test_the_repository_itself_is_consistent() -> None:
    assert numbering.rule_problems(Path(__file__).resolve().parents[3]) == []
