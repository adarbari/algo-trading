"""The local fast path keeps its shape: the web mapping in `make changed`, `tsc -b` as type gate,
`make check` scope-aware and parallel, the release on `FULL=1`."""

import json
import re
import shlex
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


def test_make_changed_runs_the_web_mapping() -> None:
    makefile = (ROOT / "Makefile").read_text()
    target = re.search(r"^changed:.*?(?=^\S)", makefile, re.S | re.M)
    assert target and "scripts/changed_web.py" in target.group(0)


def test_the_type_gate_is_tsc_build_mode() -> None:
    scripts = json.loads((ROOT / "apps/web/package.json").read_text())["scripts"]
    assert scripts["typecheck"] == "tsc -b"


def test_the_vitest_pool_is_the_decided_one() -> None:
    # vmThreads keeps per-file isolation but creates jsdom once per worker (142 s -> 35 s,
    # 2026-10-07); change it deliberately, with a new measure in docs/ci.md.
    assert "pool: 'vmThreads'" in (ROOT / "apps/web/vite.config.ts").read_text()


def test_ci_is_the_gate_and_the_machine_never_runs_the_full_check() -> None:
    # Owner decision 2026-10-08: local = `make changed` for what changed, then push; CI gates.
    text = " ".join((ROOT / "CLAUDE.md").read_text().split())
    assert "then push; CI is the gate" in text and "never the full `make check`" in text
    assert "When `make changed` passes, push" in text


def test_make_check_is_scope_aware_and_the_release_runs_every_gate() -> None:
    # docs/ci.md "Scope-aware make check": 30-40 min serial runs, 4.5 per PR in the week to
    # 2026-10-07; a change back to one serial list needs a new measure there.
    makefile = (ROOT / "Makefile").read_text()
    assert "scripts/changed_tests.py --areas" in makefile
    check = re.search(r"^check:.*?(?=^\S)", makefile, re.S | re.M)
    assert check and "-j$(CHECK_JOBS)" in check.group(0) and "check-gates" in check.group(0)
    assert re.search(r"^check-gates: \$\(strip \$\(CHECK_TARGETS\)\)", makefile, re.M)
    release = (ROOT / ".github/workflows/release.yml").read_text()
    assert "make check FULL=1" in release


def test_the_web_gates_are_make_targets_that_build_once() -> None:
    makefile = (ROOT / "Makefile").read_text()
    for target in (
        "web-generated",
        "web-lint",
        "web-typecheck",
        "web-unit",
        "web-storybook",
        "web-e2e",
    ):
        assert re.search(rf"^{target}:", makefile, re.M), target
    assert "npm run build" not in makefile.replace("$(NPM) run build --", "")
    web_check = re.search(r"^web-check:.*?(?=^\S)", makefile, re.S | re.M)
    assert web_check and "$(NPM) run check" not in web_check.group(0)


def test_a_bare_make_check_refuses_with_rule_9() -> None:
    out = subprocess.run(
        ["make", "-n", "check", "PY=/nonexistent/python"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    # Under -n the guard still runs (a shell `if` with the refusal); the sub-make is never reached.
    assert "rule 9" in out.stdout + out.stderr and "check_lock.sh" in out.stdout


def _pre_push_entry() -> str:
    config = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text())
    hooks = [h for repo in config["repos"] for h in repo["hooks"] if h["id"] == "make-changed"]
    assert len(hooks) == 1 and hooks[0]["stages"] == ["pre-push"]
    return str(hooks[0]["entry"])


def test_the_pre_push_hook_runs_make_changed_without_the_git_environment() -> None:
    """Git exports GIT_DIR to a hook; the tests under `make changed` then ran `git init --bare`
    against the real repository and left core.bare=true in the shared config (2026-11-02)."""
    words = shlex.split(_pre_push_entry())
    # the queue wrapper runs `make changed` once it has a slot (scripts/ops/push_queue.py)
    assert words[-2:] == [".venv/bin/python", "scripts/ops/push_queue.py"] and words[0] == "env"
    assert '["make", "changed"' in (ROOT / "scripts" / "ops" / "push_queue.py").read_text()
    unset = {words[i + 1] for i, w in enumerate(words) if w == "-u"}
    assert {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"} <= unset
    probe = [*words[:-2], "sh", "-c", 'printf "%s" "${GIT_DIR-unset}"']
    leaked = {"GIT_DIR": "/a/real/repo/.git", "PATH": "/usr/bin:/bin"}
    out = subprocess.run(probe, env=leaked, capture_output=True, text=True, check=True)
    assert out.stdout == "unset"


def test_the_suite_drops_the_git_repository_from_every_tests_environment() -> None:
    source = (ROOT / "tests" / "conftest.py").read_text()
    fixture = source.split("def no_inherited_git_repository", 1)[1].split("@pytest.fixture", 1)[0]
    assert "GIT_REPOSITORY_ENV" in fixture and "delenv" in fixture
    assert '"GIT_DIR"' in source.split("GIT_REPOSITORY_ENV = (", 1)[1].split(")", 1)[0]
