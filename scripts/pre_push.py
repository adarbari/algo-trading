"""The pre-push fast lane (`make pre-push`): the checks that fail most often, per second they cost.

Owner decision 2026-11-02: the hook runs locally only what failed often in CI or in `make changed`
and is cheap on the shared Mac; everything else is GitHub CI's (the repo is public: hosted minutes
are free, only concurrency is limited). Measured over the last 100 failed CI runs (2026-10-24 to
2026-11-02, `docs/ci.md` "Pre-push fast lane"), on a warm worktree; target 90 s.

Two lanes run side by side:
  - python: `make numbering` (ADR numbers vs origin/main) and `FAST_TESTS`, the file- and
    TOML-only tests that failed most (page-latency view coverage, the ADR index, recorded page
    documents, layout caps, the Guide's coverage and style, the CI workflow shape), at `-n 2`;
  - web, when `apps/web` changed: Prettier and Stylelint over the changed files and `ds:check`;
    when `src/` or `design-system/` changed, the production build, the bundle budgets (with their
    raise reasons) and the DOM / request budgets, the two web CI failures seen most.
A push that only merges main (every commit since the remote head is a clean merge) runs the
python lane alone: a merge brings ADR-number, layout-cap and view-coverage collisions, not new
web code. ESLint, `tsc`, vitest, the mirrored pytest, e2e and screenshots stay CI's; `make
changed` remains the full local check for anyone who wants it.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
import changed_tests
import changed_web

REPO = changed_tests.REPO
WEB = REPO / "apps" / "web"
BUDGET_SECONDS = 90
PY = ".venv/bin/python"
# CI failures in the 100-run sample in brackets; each is seconds on a warm worktree.
FAST_TESTS = (
    # [14] a new web view or operation not measured or listed (`make api-latency-views`)
    "tests/scripts/perf/test_views.py::test_every_web_view_and_operation_is_measured_or_listed",
    # [12] an ADR not indexed, or two PRs taking one number
    "tests/architecture/test_docs.py",
    # [4] the recorded page documents vs the web's generated ones
    "tests/scripts/perf/test_page_docs.py",
    # [3] the committed capture names only catalogue features
    "tests/scripts/perf/test_fast_bench.py::test_the_committed_capture_names_only_features_the_catalogue_has",
    # [2] every web operation in exactly one response-cache group
    "tests/apps/api/graphql/test_response_cache.py::test_every_web_operation_is_in_exactly_one_group",
    # [3] the CI workflow's shape
    "tests/architecture/pipeline/test_ci_workflow.py",
    # [2 + local reports] Guide coverage, wording, `see_also` links
    "tests/architecture/guide",
    "tests/unit/config/site/guide",
    # [2 + local reports] folder caps
    "tests/architecture/test_layout.py",
    "tests/architecture/test_layout_web.py",
)
Step = tuple[str, list[str], dict[str, str]]


def is_merge_only(remote: str | None, local: str, base: str = "origin/main") -> bool:
    """Every commit the push adds over `remote` (not on `base`) is a merge with no resolution."""
    if not remote or set(remote) == {"0"}:  # a new branch: nothing to compare with
        return False
    try:
        commits = changed_tests._git("rev-list", f"{remote}..{local}", "--not", base)
        if not commits:
            return False
        for sha in commits:
            parents = changed_tests._git("rev-list", "--parents", "-n", "1", sha)[0].split()[1:]
            # `--cc` prints a combined diff only where the merge resolved a conflict by hand
            if len(parents) < 2 or changed_tests._git("show", "--cc", "--format=", sha):
                return False
    except subprocess.CalledProcessError:
        return False
    return True


def _tracked() -> str | None:
    """The branch's remote head (`origin/<branch>`), when it has one."""
    try:
        return changed_tests._git("rev-parse", "--verify", "-q", "@{upstream}")[0]
    except (subprocess.CalledProcessError, IndexError):
        return None


def free_port_base() -> str:
    """An `ALGOTRADE_PORT_BASE` whose preview port (+7, vite.config.ts) is free right now."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return str(s.getsockname()[1] - 7)


def python_lane() -> list[Step]:
    return [
        ("numbering", ["make", "--no-print-directory", "numbering"], {}),
        ("fast tests", [PY, "-m", "pytest", "-q", "-x", "-n", "2", *FAST_TESTS], {}),
    ]


def web_lane(files: list[str], root: Path | None = WEB) -> list[Step]:
    """Prettier, Stylelint and `ds:check` from `changed_web`, then the budgets."""
    static: list[Step] = [
        (w, c, {}) for w, c in changed_web._static_steps(_present(files, root)) if w != "eslint"
    ]
    built = any(
        PurePosixPath(f.removeprefix(changed_web.WEB)).parts[0] in ("src", "design-system")
        for f in files
        if f.startswith(changed_web.WEB)
    )
    if not built:
        return static
    budgets: list[Step] = [(w, c, {}) for w, c in changed_web.BUNDLE_STEPS]
    budgets.append(("DOM budgets", ["npm", "run", "perf:e2e"], {"ALGOTRADE_PORT_BASE": ""}))
    return static + budgets


def _present(files: list[str], root: Path | None) -> list[str]:
    rels = [f.removeprefix(changed_web.WEB) for f in files if f.startswith(changed_web.WEB)]
    return [r for r in rels if root is None or (root / r).is_file()]


def plan(files: list[str], merge_only: bool, root: Path | None = WEB) -> dict[str, list[Step]]:
    """The lanes to run: `python` always, `web` unless the push only merges main."""
    lanes = {"python": python_lane()}
    if not merge_only:
        lanes["web"] = web_lane(files, root)
    return lanes


def _run_lane(name: str, steps: list[Step]) -> tuple[str, int, float]:
    started = time.monotonic()
    for what, cmd, extra in steps:
        env = {**os.environ, **extra}
        if extra.get("ALGOTRADE_PORT_BASE") == "":
            env["ALGOTRADE_PORT_BASE"] = free_port_base()
        cwd = REPO if name == "python" else WEB
        print(f"pre-push {name}: {what}", flush=True)
        if subprocess.run(cmd, cwd=cwd, env=env, check=False).returncode:
            return f"{name}: {what}", 1, time.monotonic() - started
    return name, 0, time.monotonic() - started


def main(argv: list[str]) -> int:
    base = next((a for a in argv[1:] if not a.startswith("--")), "origin/main")
    changed_tests.refresh(base)
    files = changed_tests.changed_files(base)
    remote = os.environ.get("PRE_COMMIT_FROM_REF") or _tracked()  # the remote head before the push
    merge_only = is_merge_only(remote, os.environ.get("PRE_COMMIT_TO_REF", "HEAD"), base)
    if merge_only:
        print("pre-push: the push only merges main; the python lane alone", flush=True)
    lanes = plan(files, merge_only)
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=len(lanes)) as pool:
        results = list(pool.map(lambda kv: _run_lane(*kv), lanes.items()))
    elapsed = time.monotonic() - started
    for what, code, seconds in results:
        print(f"pre-push {'FAILED' if code else 'ok'}: {what} ({seconds:.0f} s)")
    if elapsed > BUDGET_SECONDS:
        print(f"pre-push: {elapsed:.0f} s, over the {BUDGET_SECONDS} s budget (docs/ci.md)")
    return max(code for _, code, _ in results)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
