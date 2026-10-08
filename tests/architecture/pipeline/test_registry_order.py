"""The registries are id-ordered inside each section, so two PRs that add an entry no longer
append at the same line: ownership responsibilities by `id`, layout `[[dir]]` / `[[test_dir]]`
and web `[[web_dir]]` by `path`. A section is the block under one `# ----` heading. The loaders
read every entry (no first-match, no precedence), so the order carries no meaning."""

import re
import tomllib
from pathlib import Path

import pytest

ARCH = Path(__file__).resolve().parents[3] / "architecture"
KEYS = {"responsibility": "id", "dir": "path", "test_dir": "path", "web_dir": "path"}
CASES = [
    ("ownership.toml", "responsibility"),
    ("layout.toml", "dir"),
    ("layout.toml", "test_dir"),
    ("web_layout.toml", "web_dir"),
]


def _sections(text: str) -> list[str]:
    """The text of each `# ----` section (and of the header before the first)."""
    return re.split(r"^# -{20,}.*$", text, flags=re.MULTILINE)


def _keys(part: str, table: str) -> list[str]:
    found: list[str] = []
    inside = False
    for line in part.splitlines():
        if (header := re.match(r"\[\[(\w+)\]\]", line)) is not None:
            inside = header.group(1) == table
        elif inside and (m := re.match(rf'{KEYS[table]} = "(.*?)"', line)):
            found.append(m.group(1))
            inside = False
    return found


@pytest.mark.parametrize(("file", "table"), CASES)
def test_entries_are_sorted_within_each_section(file: str, table: str) -> None:
    text = (ARCH / file).read_text()
    total = 0
    for part in _sections(text):
        keys = _keys(part, table)
        total += len(keys)
        wrong = [k for k, s in zip(keys, sorted(keys), strict=True) if k != s]
        assert not wrong, (
            f"{file} [[{table}]]: sort the entries by {KEYS[table]} inside their section "
            f"(first out of place: {wrong[0]!r})"
        )
    assert total == len(tomllib.loads(text)[table]), "every entry has a key line the test reads"
