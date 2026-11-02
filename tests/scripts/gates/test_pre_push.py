"""`scripts/pre_push.py`: the hook's fast lane plans only the checks that fail most per second,
skips the web lane on a merge-only push and stays under its time budget (owner 2026-11-02)."""

import importlib.util
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
_spec = importlib.util.spec_from_file_location("pre_push", SCRIPTS / "pre_push.py")
assert _spec and _spec.loader
pre_push = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pre_push)


BUDGET_PAGES = " ".join(pre_push.BUDGET_PAGES[1])


def cmds(files: list[str], merge_only: bool = False) -> dict[str, list[str]]:
    lanes = pre_push.plan(files, merge_only, root=None)
    return {lane: [" ".join(c) for _, c, _ in steps] for lane, steps in lanes.items()}


def test_a_web_source_change_runs_the_static_gates_and_the_budgets() -> None:
    web = cmds(["apps/web/src/pages/trader-ideas/IdeasPage.tsx"])["web"]
    assert web[0].startswith("npx prettier --check") and "npm run ds:check" in web
    assert web[-4:] == [
        "env VITE_SUPABASE_URL=http://127.0.0.1:54321 VITE_SUPABASE_ANON_KEY=e2e-anon-key"
        " npx vite build",
        "npm run perf:bundle",
        "npm run perf:e2e",
        BUDGET_PAGES,
    ]


def test_the_slow_rarely_failing_checks_stay_in_ci() -> None:
    # measured 2026-11-02: ESLint 4 failures in 100 red runs for 25-55 s, tsc 0, vitest 1
    every = [
        c
        for lane in cmds(["apps/web/src/a/b/C.tsx", "src/algotrade/x.py"]).values()
        for c in lane
        if c != BUDGET_PAGES  # one vitest file, seconds: the one vitest the hook runs
    ]
    for slow in (
        "eslint",
        "typecheck",
        "vitest",
        "playwright test",
        "generated:check",
    ):
        assert not any(slow in c for c in every), slow
    # the python lane is the fixed fast list plus the scoped ownership check: no mirrored or
    # whole-folder runs
    assert cmds(["src/algotrade/x.py"])["python"][:-1] == cmds([])["python"]
    assert not any(c.endswith(" tests/architecture") for c in every)


def test_a_config_only_web_change_gets_no_build() -> None:
    web = cmds(["apps/web/package.json"])["web"]
    assert not any("vite build" in c or "perf:" in c for c in web)


def test_changed_python_files_get_the_scoped_ownership_check() -> None:
    # 2026-11-02 #1064 / #1065: a new ownership violation reached CI only
    changed = ["src/algotrade/b.py", "apps/api/a.py", "docs/x.md", "tests/unit/t.py"]
    assert cmds(changed)["python"][-1] == (
        ".venv/bin/python scripts/check_ownership.py --files apps/api/a.py src/algotrade/b.py"
    )
    assert not any("check_ownership" in c for c in cmds(["docs/x.md"])["python"])
    assert "check_ownership" in cmds(["src/algotrade/b.py"], merge_only=True)["python"][-1]


def test_a_merge_only_push_skips_the_web_lane() -> None:
    lanes = cmds(["apps/web/design-system/a/B.tsx"], merge_only=True)
    assert set(lanes) == {"python"}
    assert lanes["python"][0] == "make --no-print-directory numbering"


def test_a_merge_only_push_still_checks_a_budget_for_every_lazy_page() -> None:
    # 2026-11-02 #1035: the budgets merge driver kept main's raised budget for two pages the
    # branch had removed; only CI's vitest caught it
    for touched in ("apps/web/src/pages/a/index.ts", "apps/web/perf-budgets.json"):
        assert cmds([touched], merge_only=True)["web"] == [BUDGET_PAGES]
    assert BUDGET_PAGES in cmds(["apps/web/perf-budgets.json"])["web"]
    assert "web" not in cmds(["src/algotrade/x.py"], merge_only=True)


def test_every_fast_test_exists() -> None:
    for node in pre_push.FAST_TESTS:
        path, _, name = node.partition("::")
        assert (REPO / path).exists(), node
        if name:
            assert re.search(rf"^def {name}\(", (REPO / path).read_text(), re.M), node


def _fake_git(monkeypatch: pytest.MonkeyPatch, commits: dict[str, tuple[int, str]]) -> None:
    """`commits`: sha -> (parent count, `show --cc` output) over the push's new commits."""

    def git(*args: str) -> list[str]:
        if args[0] == "rev-list" and args[1] == "--parents":
            n = commits[args[-1]][0]
            return [" ".join([args[-1], *(f"p{i}" for i in range(n))])]
        if args[0] == "rev-list":
            return list(commits)
        if args[0] == "show":
            return [commits[args[-1]][1]] if commits[args[-1]][1] else []
        raise AssertionError(args)

    monkeypatch.setattr(pre_push.changed_tests, "_git", git)


def test_clean_merges_of_main_are_merge_only(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_git(monkeypatch, {"m1": (2, ""), "m2": (2, "")})
    assert pre_push.is_merge_only("remote", "HEAD")


def test_a_new_commit_or_a_resolved_conflict_is_not(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_git(monkeypatch, {"m1": (2, ""), "c1": (1, "")})
    assert not pre_push.is_merge_only("remote", "HEAD")
    _fake_git(monkeypatch, {"m1": (2, "diff --cc a.py")})
    assert not pre_push.is_merge_only("remote", "HEAD")


def test_a_new_branch_is_not_merge_only() -> None:
    assert not pre_push.is_merge_only(None, "HEAD")
    assert not pre_push.is_merge_only("0" * 40, "HEAD")


@pytest.mark.perf
def test_the_python_lane_stays_under_the_budget() -> None:
    # `make perf` on an idle machine: the fast list must not creep past the hook's budget
    started = time.monotonic()
    for _, cmd, _ in pre_push.python_lane():
        assert subprocess.run(cmd, cwd=REPO, check=False).returncode == 0, cmd
    assert time.monotonic() - started < pre_push.BUDGET_SECONDS


def test_a_signal_kills_every_running_step_and_exits_128_plus_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # make passes only SIGTERM on: without this, pytest and `vite preview` outlived the queue slot
    child = subprocess.Popen(["sleep", "30"], start_new_session=True)
    pre_push.RUNNING.add(child)

    def exit_(code: int) -> None:
        raise SystemExit(code)

    monkeypatch.setattr(pre_push.os, "_exit", exit_)
    with pytest.raises(SystemExit) as stopped:
        pre_push.stop_all(15)
    pre_push.RUNNING.discard(child)
    assert stopped.value.code == 143 and child.wait(timeout=5) != 0
