"""The local fast path keeps its shape: the web mapping in `make changed`, `tsc -b` as type gate,
`make check` scope-aware and parallel, the release on `FULL=1`."""

import json
import re
from pathlib import Path

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
    assert check and "$(CHECK_TARGETS)" in check.group(0) and "-j$(CHECK_JOBS)" in check.group(0)
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
