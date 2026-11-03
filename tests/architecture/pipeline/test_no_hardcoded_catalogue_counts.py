"""A test never hard-codes how many site presets there are: every new screener PR would break it.

2026-11-02: #1113 failed CI because two tests in the GraphQL ideas suite asserted `== 96` presets
(97 once a screener was added). The count comes from the preset folder, never a literal.
"""

from __future__ import annotations

import re
from pathlib import Path

TESTS = Path(__file__).resolve().parents[2]
# `len(...) == 96` (or `!=`, `>=`) on a line that talks about presets, in code or its comment
LITERAL = re.compile(r"len\([^#]*\)\s*[=!<>]=\s*\d{2,}\b")


def test_no_test_hard_codes_a_count_of_site_presets() -> None:
    offenders = [
        f"{path.relative_to(TESTS.parent)}:{n}: {line.strip()}"
        for path in sorted(TESTS.rglob("*.py"))
        if path != Path(__file__)
        for n, line in enumerate(path.read_text().splitlines(), 1)
        if "preset" in line.lower() and LITERAL.search(line)
    ]
    assert not offenders, (
        "count the presets from config/site/presets/screeners, not a literal:\n"
        + "\n".join(offenders)
    )
