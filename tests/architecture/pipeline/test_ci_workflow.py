"""The CI workflow keeps its parallel shape (docs/ci.md "Pipeline"): the web work runs as
independent jobs gated on the changed areas, Storybook is built once and handed to the
screenshot shards, the protected check names stay, and the Playwright image is one string."""

import json
import re
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[3]
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"
LOCK = REPO / "apps" / "web" / "package-lock.json"

# Branch protection on main requires these contexts by name (the owner's repo settings): a
# renamed job never reports and blocks every merge.
PROTECTED_CHECKS = {
    "Changed areas",
    "Lint, types, boundaries, ownership, duplicates, file length, strategy evaluation",
    "Tests (py${{ matrix.python }})",
    "Web (lint, types, unit, design system, build, Storybook, e2e, screenshots)",
    "Real app smoke (Vite dev + real API, empty and golden stores)",
}
WEB_JOBS = {"web-static", "web-e2e", "web-storybook", "web-screenshots"}


def _jobs() -> dict[str, dict[str, Any]]:
    return yaml.safe_load(WORKFLOW.read_text())["jobs"]


def test_protected_check_names_are_unchanged() -> None:
    names = {job["name"] for job in _jobs().values()}
    missing = PROTECTED_CHECKS - names
    assert not missing, f"renaming a protected check blocks every merge: {missing}"


def test_web_jobs_run_in_parallel_gated_on_the_changed_areas() -> None:
    jobs = _jobs()
    for name in WEB_JOBS:
        job = jobs[name]
        assert job["if"] == "needs.changes.outputs.web == 'true'", f"{name} must skip non-web PRs"
        upstream = set(job["needs"]) - {"changes"}
        expected = {"web-storybook"} if name == "web-screenshots" else set()
        assert upstream == expected, f"{name} may wait only for {expected or 'nothing'}: {upstream}"


def test_storybook_is_built_once_and_handed_to_the_screenshot_shards() -> None:
    jobs = _jobs()
    uploads = [s for s in jobs["web-storybook"]["steps"] if "upload-artifact" in str(s.get("uses"))]
    assert uploads and uploads[0]["with"]["name"] == "storybook-static"
    shards = jobs["web-screenshots"]
    count = len(shards["strategy"]["matrix"]["shard"])
    assert shards["strategy"]["matrix"]["shard"] == list(range(1, count + 1)) and count >= 4
    steps = shards["steps"]
    assert any("download-artifact" in str(s.get("uses")) for s in steps)
    assert not any("storybook:build" in str(s.get("run", "")) for s in steps)
    visual = next(s["run"] for s in steps if "npm run visual" in str(s.get("run", "")))
    assert f"--shard=${{{{ matrix.shard }}}}/{count}" in visual
    assert f"of {count})" in shards["name"]


def test_pytest_shards_cover_every_test_folder_and_combine_under_the_protected_name() -> None:
    makefile = (REPO / "Makefile").read_text()
    shards = re.findall(r"^TEST_SHARD_(\w+) = (.+)$", makefile, flags=re.MULTILINE)
    assert [name for name, _ in shards] == ["unit", "apps", "rest"]
    covered = {folder for _, folders in shards for folder in folders.split()}
    with_tests = {
        f"tests/{d.name}"
        for d in (REPO / "tests").iterdir()
        if d.is_dir() and any(d.rglob("test_*.py"))
    }
    assert covered == with_tests, f"shards vs folders: {covered ^ with_tests}"
    jobs = _jobs()
    assert jobs["test"]["strategy"]["matrix"]["shard"] == [name for name, _ in shards]
    assert "make test-shard SHARD=${{ matrix.shard }}" in str(jobs["test"]["steps"])
    gate = jobs["tests"]
    assert gate["name"] == "Tests (py${{ matrix.python }})"
    assert set(gate["needs"]) == {"changes", "test"}
    assert gate["if"].strip() == "${{ !cancelled() }}"
    assert "make coverage-combine" in str(gate["steps"])
    assert "--cov-fail-under=0" in makefile and "--fail-under=90" in makefile


def test_npm_audit_runs_only_on_a_dependency_change() -> None:
    jobs = _jobs()
    audit = next(s for s in jobs["web-static"]["steps"] if "npm audit" in str(s.get("run", "")))
    assert audit["if"].startswith("needs.changes.outputs.web_deps == 'true'")
    assert "apps/web/package-lock.json" in jobs["changes"]["steps"][-1]["run"]


def test_the_web_gate_waits_for_every_web_job_and_tolerates_skips() -> None:
    gate = _jobs()["web"]
    assert set(gate["needs"]) == WEB_JOBS
    assert gate["if"].strip() == "${{ !cancelled() }}"
    run = gate["steps"][0]["run"]
    assert "failure" in run and "cancelled" in run and "skipped" not in run


def test_python_jobs_skip_web_only_and_docs_only_changes() -> None:
    jobs = _jobs()
    assert jobs["quality"]["if"] == "needs.changes.outputs.python == 'true'"
    steps = {s.get("name"): s for s in jobs["test"]["steps"]}
    full = next(s for n, s in steps.items() if n and n.startswith("Unit + architecture"))
    assert full["if"] == "needs.changes.outputs.python == 'true'"
    arch = next(s for n, s in steps.items() if n and n.startswith("Architecture tests only"))
    assert arch["if"] == "needs.changes.outputs.python != 'true' && matrix.shard == 'rest'"
    assert "tests/architecture" in arch["run"]
    classify = jobs["changes"]["steps"][-1]["run"]
    assert "docs/* | .claude/* | *.md" in classify, "docs-only PRs run the architecture tests only"


def test_a_matrix_job_with_a_protected_name_has_no_job_level_if() -> None:
    """GitHub does not expand the matrix of a skipped job: the check reports under the literal
    name "Tests (py${{ matrix.python }})" and the protected "Tests (py3.12)" never appears."""
    for name, job in _jobs().items():
        if "matrix" in job.get("strategy", {}) and job["name"] in PROTECTED_CHECKS:
            condition = str(job.get("if", "")).strip()
            assert condition in ("", "${{ !cancelled() }}"), f"{name}: condition the steps"


def test_playwright_image_is_one_string_matching_the_lockfile() -> None:
    text = WORKFLOW.read_text()
    env_image = yaml.safe_load(text)["env"]["PLAYWRIGHT_IMAGE"]
    containers = re.findall(r"^\s+image: (\S+)$", text, flags=re.MULTILINE)
    assert containers and set(containers) == {env_image}, "every container uses PLAYWRIGHT_IMAGE"
    locked = json.loads(LOCK.read_text())["packages"]["node_modules/@playwright/test"]["version"]
    assert env_image == f"mcr.microsoft.com/playwright:v{locked}-noble"


def test_retries_exist_only_in_the_playwright_configs() -> None:
    """One retry in CI for Playwright only (docs/ci.md); pytest and vitest never retry."""
    web = REPO / "apps" / "web"
    for cfg in ("playwright.config.ts", "playwright.visual.config.ts"):
        assert "retries: process.env['CI'] ? 1 : 0" in (web / cfg).read_text(), cfg
    assert "retries: 0" in (web / "playwright.real.config.ts").read_text()
    assert "retry" not in (web / "vite.config.ts").read_text()
    assert "reruns" not in (REPO / "pyproject.toml").read_text()
