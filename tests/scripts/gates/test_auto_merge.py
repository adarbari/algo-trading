"""``scripts/auto_merge.sh`` never merges a PR carrying ``no-automerge`` or ``needs-owner``: both
are checked before CI is even looked at (a stub ``gh`` answers; any other call fails the test)."""

import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "auto_merge.sh"

STUB = """#!/usr/bin/env bash
# only `gh pr view` is allowed: a label that blocks must stop the script before any other call
if [ "$1 $2" = "pr view" ]; then cat "$PR_JSON"; exit 0; fi
echo "unexpected gh call: $*" >&2; exit 99
"""


def _run(tmp_path: Path, labels: list[str]) -> subprocess.CompletedProcess[str]:
    pr = {
        "state": "OPEN", "isDraft": False, "isCrossRepository": False, "headRefOid": "abc1234",
        "mergeable": "MERGEABLE", "baseRefName": "main",
        "labels": [{"name": name} for name in labels],
    }  # fmt: skip
    (tmp_path / "pr.json").write_text(json.dumps(pr))
    gh = tmp_path / "bin" / "gh"
    gh.parent.mkdir()
    gh.write_text(STUB)
    gh.chmod(0o755)
    env = {**os.environ, "PATH": f"{gh.parent}:{os.environ['PATH']}", "REPO": "o/r",
           "PR_JSON": str(tmp_path / "pr.json"), "DRY_RUN": "1"}  # fmt: skip
    return subprocess.run(
        ["bash", str(SCRIPT), "7"], env=env, capture_output=True, text=True, check=False
    )


@pytest.mark.parametrize("label", ["no-automerge", "needs-owner"])
def test_a_blocking_label_stops_the_merge_before_ci_is_read(tmp_path: Path, label: str) -> None:
    done = _run(tmp_path, ["bug", label])
    assert done.returncode == 0, done.stderr
    assert f"labelled {label}, skipped" in done.stdout


def test_an_unlabelled_pr_goes_on_to_the_ci_check(tmp_path: Path) -> None:
    done = _run(tmp_path, ["bug"])
    assert "skipped" not in done.stdout
    assert "unexpected gh call" in done.stderr  # it reached the CI lookup


# --- which CI run decides: a held pull_request run may be replaced by a dispatched one ---------

SHA = "abc1234"
FULL_STUB = """#!/usr/bin/env bash
case "$*" in
  "pr view"*) cat "$DIR/pr.json" ;;
  *"event=pull_request"*) cat "$DIR/pull_request.json" ;;
  *"event=workflow_dispatch"*) cat "$DIR/dispatch.json" ;;
  *"/check-runs"*) cat "$DIR/check_runs.json" ;;
  *) echo "unexpected gh call: $*" >&2; exit 99 ;;
esac
"""


def _ci(run_id: int, conclusion: str | None, *, suite: int, sha: str = SHA,
        actor: str = "github-actions[bot]", repo: str = "o/r", at: str = "2026-10-17T10:00:00Z",
        status: str = "completed") -> dict:  # fmt: skip
    return {
        "id": run_id, "name": "CI", "conclusion": conclusion, "status": status, "head_sha": sha,
        "check_suite_id": suite, "created_at": at, "head_repository": {"full_name": repo},
        "triggering_actor": {"login": actor},
    }  # fmt: skip


def _decide(
    tmp_path: Path,
    pull_request: list[dict],
    dispatch: list[dict],
    check_runs: list[dict] | None = None,
) -> str:
    pr = {
        "state": "OPEN", "isDraft": False, "isCrossRepository": False, "headRefOid": SHA,
        "mergeable": "MERGEABLE", "baseRefName": "main", "labels": [],
    }  # fmt: skip
    suites = {r["check_suite_id"]: r["conclusion"] for r in pull_request + dispatch}
    checks = [
        {"name": f"job{s}", "status": "completed", "conclusion": c or "failure",
         "check_suite": {"id": s}}
        for s, c in suites.items() if c != "action_required"
    ] + (check_runs or [])  # fmt: skip
    files = {"pr": pr, "pull_request": {"workflow_runs": pull_request},
             "dispatch": {"workflow_runs": dispatch},
             "check_runs": {"check_runs": checks}}  # fmt: skip
    for name, body in files.items():
        (tmp_path / f"{name}.json").write_text(json.dumps(body))
    gh = tmp_path / "bin" / "gh"
    gh.parent.mkdir()
    gh.write_text(FULL_STUB)
    gh.chmod(0o755)
    env = {**os.environ, "PATH": f"{gh.parent}:{os.environ['PATH']}", "REPO": "o/r",
           "DIR": str(tmp_path), "DRY_RUN": "1"}  # fmt: skip
    done = subprocess.run(
        ["bash", str(SCRIPT), "7"], env=env, capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr
    return done.stdout


HELD = _ci(1, "action_required", suite=10)


def test_a_green_pull_request_run_merges(tmp_path: Path) -> None:
    assert "WOULD MERGE" in _decide(tmp_path, [_ci(1, "success", suite=10)], [])


def test_a_held_run_is_replaced_by_a_green_dispatched_run(tmp_path: Path) -> None:
    assert "WOULD MERGE" in _decide(tmp_path, [HELD], [_ci(2, "success", suite=20)])


def test_a_missing_pull_request_run_is_replaced_by_a_green_dispatched_run(tmp_path: Path) -> None:
    assert "WOULD MERGE" in _decide(tmp_path, [], [_ci(2, "success", suite=20)])


def test_a_held_run_with_a_failed_dispatched_run_waits(tmp_path: Path) -> None:
    assert "is 'failure', waiting" in _decide(tmp_path, [HELD], [_ci(2, "failure", suite=20)])


def test_a_held_run_with_a_running_dispatched_run_waits(tmp_path: Path) -> None:
    out = _decide(tmp_path, [HELD], [_ci(2, None, suite=20, status="in_progress")])
    assert "is 'in_progress', waiting" in out


def test_a_held_run_with_no_dispatch_waits(tmp_path: Path) -> None:
    assert "is 'missing', waiting" in _decide(tmp_path, [HELD], [])


def test_a_dispatch_for_another_sha_is_ignored(tmp_path: Path) -> None:
    out = _decide(tmp_path, [HELD], [_ci(2, "success", suite=20, sha="def5678")])
    assert "is 'missing', waiting" in out


def test_a_dispatch_from_a_foreign_repo_or_actor_is_ignored(tmp_path: Path) -> None:
    forged = [_ci(2, "success", suite=20, repo="x/fork"), _ci(3, "success", suite=30, actor="eve")]
    assert "is 'missing', waiting" in _decide(tmp_path, [HELD], forged)


def test_a_failed_check_run_still_blocks_a_green_dispatch(tmp_path: Path) -> None:
    bad = [
        {"name": "lint", "status": "completed", "conclusion": "failure", "check_suite": {"id": 99}}
    ]
    out = _decide(tmp_path, [HELD], [_ci(2, "success", suite=20)], bad)
    assert "checks not passed: lint" in out
