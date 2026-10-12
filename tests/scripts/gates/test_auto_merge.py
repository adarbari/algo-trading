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
