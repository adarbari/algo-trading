"""`apps/web/audit-allowlist.json` (docs/ci.md "Dependency audit") stays a reviewed, dated list:
every entry names a GHSA advisory, its package, the reason and an expiry at most 90 days after
it was added, and CI runs the gate that honours it over every dependency."""

import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
WEB = REPO / "apps" / "web"
ALLOWED = json.loads((WEB / "audit-allowlist.json").read_text())["allowed"]
MAX_DAYS = 90


@pytest.mark.parametrize("entry", ALLOWED, ids=[e["advisory"] for e in ALLOWED])
def test_entry_is_reviewed_and_dated(entry: dict[str, Any]) -> None:
    assert set(entry) == {"advisory", "package", "reason", "added", "expires"}
    assert re.fullmatch(r"GHSA(-[23456789cfghjmpqrvwx]{4}){3}", entry["advisory"])
    assert len(entry["reason"]) > 80, "say why the risk is accepted and what the fix waits for"
    added, expires = date.fromisoformat(entry["added"]), date.fromisoformat(entry["expires"])
    assert added < expires <= added + timedelta(days=MAX_DAYS), "expire within 90 days"


def test_ci_gates_every_dependency_through_the_allow_list() -> None:
    steps = yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text())["jobs"][
        "web-static"
    ]["steps"]
    runs = [s.get("run", "") for s in steps]
    assert any(r.startswith("npm run audit:check") for r in runs)
    assert "npm audit --omit=dev --audit-level=high" in runs
    assert "npm audit signatures" in runs
    scripts = json.loads((WEB / "package.json").read_text())["scripts"]
    assert scripts["audit:check"] == "tsx scripts/check-audit.ts"
