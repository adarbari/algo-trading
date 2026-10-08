"""`apps/web/quarantine.json` (docs/ci.md "Flaky specs") stays honest: every entry names a test
that still exists, the date and the reason, skipped entries stay few, and the Playwright and
Vitest configs read the list (a quarantined spec is skipped by configuration, never by editing
the spec)."""

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[3]
WEB = REPO / "apps" / "web"
QUARANTINE = json.loads((WEB / "quarantine.json").read_text())
MAX_SKIPPED = 8
ENTRIES = [(group, e) for group in ("skipped", "watched") for e in QUARANTINE[group]]


@pytest.mark.parametrize(("group", "entry"), ENTRIES, ids=[e["file"] for _, e in ENTRIES])
def test_entry_names_an_existing_test_with_its_date_and_reason(
    group: str, entry: dict[str, Any]
) -> None:
    path = WEB / entry["file"]
    assert path.is_file(), f"{entry['file']} is gone: drop the entry"
    assert entry["kind"] in ("e2e", "unit")
    date.fromisoformat(entry["since"])
    assert len(entry["reason"]) > 40, "say what flakes and the fix it waits for"
    if entry["kind"] == "e2e":
        pattern = re.escape(entry["title"]).replace(r"\ ", r"\s+")
        # a title built from a template literal keeps its theme / width placeholder
        pattern = re.sub(r"\\\((light|dark)\\\)$", r"\\(\\$\\{theme\\}\\)", pattern)
        assert re.search(pattern, path.read_text()), f"{entry['title']!r} is not in {entry['file']}"
    else:
        assert path.name.endswith((".test.ts", ".test.tsx"))


def test_skipped_stays_a_short_list() -> None:
    assert len(QUARANTINE["skipped"]) <= MAX_SKIPPED, "fix the oldest entries before adding more"


def test_configs_read_the_list() -> None:
    for cfg in ("playwright.config.ts", "vite.config.ts"):
        assert "quarantine.json" in (WEB / cfg).read_text(), f"{cfg} must read quarantine.json"


def test_no_spec_is_skipped_by_editing_it() -> None:
    """A flake goes in the list, so it stays visible and runs under QUARANTINE=only."""
    offenders = [
        str(p.relative_to(WEB))
        for folder in ("e2e", "src", "design-system", "scripts")
        for p in (WEB / folder).rglob("*.spec.ts")
        if re.search(r"\btest\.(skip|fixme)\(\s*['\"`]", p.read_text())
    ]
    assert not offenders, f"quarantine these in apps/web/quarantine.json instead: {offenders}"
