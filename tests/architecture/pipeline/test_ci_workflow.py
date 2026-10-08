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
    assert shards["strategy"]["matrix"]["shard"] == [1, 2]
    steps = shards["steps"]
    assert any("download-artifact" in str(s.get("uses")) for s in steps)
    assert not any("storybook:build" in str(s.get("run", "")) for s in steps)
    visual = next(s["run"] for s in steps if "npm run visual" in str(s.get("run", "")))
    assert "--shard=${{ matrix.shard }}/2" in visual


def test_the_web_gate_waits_for_every_web_job_and_tolerates_skips() -> None:
    gate = _jobs()["web"]
    assert set(gate["needs"]) == WEB_JOBS
    assert gate["if"].strip() == "${{ !cancelled() }}"
    run = gate["steps"][0]["run"]
    assert "failure" in run and "cancelled" in run and "skipped" not in run


def test_python_jobs_skip_web_only_and_docs_only_changes() -> None:
    jobs = _jobs()
    assert jobs["test"]["if"] == "needs.changes.outputs.python == 'true'"
    assert jobs["quality"]["if"] == "needs.changes.outputs.python == 'true'"
    assert jobs["architecture"]["if"] == "needs.changes.outputs.python != 'true'"
    classify = jobs["changes"]["steps"][-1]["run"]
    assert "docs/* | .claude/* | *.md" in classify, "docs-only PRs run the architecture tests only"


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
