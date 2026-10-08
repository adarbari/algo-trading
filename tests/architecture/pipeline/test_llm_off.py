"""No real model call from a test, a local gate, the real-app smoke or CI (owner rule 2026-10-08,
ADR 0041 amendment): ``ALGOTRADE_LLM=off`` forces the text model off whatever ``llm.local.toml``
or ``.env`` hold, and every place that runs the suite or the real API sets it. This fails when one
is missing, or when a test builds the text model or a Claude CLI without deciding the guard."""

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
SWITCH = "ALGOTRADE_LLM"
# Targets that run no test themselves: `check` fans out to targets that carry the export
# (a target-specific export reaches its prerequisites); the visual ones run Storybook only.
NO_API = {"check", "web-check", "web-visual"}


def test_every_workflow_that_runs_tests_or_the_smoke_sets_the_switch() -> None:
    for name in ("ci.yml", "screenshots.yml"):
        env = yaml.safe_load((REPO / ".github" / "workflows" / name).read_text())["env"]
        assert env.get(SWITCH) == "off", f"{name} must set {SWITCH}: off at the workflow level"


def test_the_real_app_playwright_api_sets_the_switch() -> None:
    config = (REPO / "apps" / "web" / "playwright.real.config.ts").read_text()
    assert re.search(rf"{SWITCH}:\s*'off'", config), "the real-app API must run with the switch off"


def test_every_makefile_target_that_runs_pytest_or_the_real_app_exports_the_switch() -> None:
    lines = (REPO / "Makefile").read_text().splitlines()
    exported: set[str] = set()
    for line in lines:
        m = re.match(rf"([\w\- ]+):\s*export {SWITCH}\s*=\s*off\s*$", line)
        if m:
            exported |= set(m.group(1).split())
    needing: set[str] = set()
    target = ""
    for line in lines:
        head = re.match(r"([\w\-]+):(?!=)", line)
        if head:
            target = head.group(1)
        elif line.startswith("\t") and re.search(r"pytest|playwright test|npm run e2e", line):
            needing.add(target)
    missing = needing - exported - NO_API
    assert not missing, f"targets that run tests without `export {SWITCH} = off`: {missing}"
    assert {"test", "test-shard", "changed", "web-real", "web-e2e"} <= exported


def test_no_test_builds_the_text_model_without_deciding_the_guard() -> None:
    """A test that calls ``open_text_model`` mentions the switch (it sets or clears it on
    purpose); one that builds a ``ClaudeCli`` hands it a fake ``runner``."""
    bad: list[str] = []
    for path in sorted((REPO / "tests").rglob("*.py")):
        if path == Path(__file__):
            continue
        text = path.read_text()
        if "open_text_model(" in text and SWITCH not in text:
            bad.append(f"{path.relative_to(REPO)}: open_text_model without {SWITCH}")
        if re.search(r"\bClaudeCli\(", text) and "runner" not in text:
            bad.append(f"{path.relative_to(REPO)}: ClaudeCli without a fake runner")
    assert not bad, bad
