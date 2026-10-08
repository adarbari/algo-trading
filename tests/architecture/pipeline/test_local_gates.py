"""The local fast path keeps its shape: the web mapping in `make changed`, `tsc -b` as type gate."""

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


def test_the_one_full_check_rule_is_in_claude_md() -> None:
    text = " ".join((ROOT / "CLAUDE.md").read_text().split())
    assert "once before the push" in text and "never the whole `make check` again" in text
