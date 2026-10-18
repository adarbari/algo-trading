"""A reader of ``results/rule_screen_values`` never shows a group row as a criterion (ADR 0071):
a module that filters rows with ``is_display_column`` also filters with ``is_group_row`` (or
uses ``is_criterion_row``, which is both), so the next reader written cannot forget one."""

from pathlib import Path

from tests.conftest import REPO_ROOT

SCANNED = ("src/algotrade", "apps", "libs")
DECLARES = "src/algotrade/storage/tables/schemas.py"  # defines the three predicates


def _readers() -> list[Path]:
    return [
        path
        for root in SCANNED
        for path in (REPO_ROOT / root).rglob("*.py")
        if "node_modules" not in path.parts
        and path.relative_to(REPO_ROOT).as_posix() != DECLARES
        and "is_display_column" in path.read_text()
    ]


def test_a_display_column_filter_is_always_a_group_row_filter_too() -> None:
    readers = _readers()
    assert readers, "the scan found no reader: the predicate moved"
    bare = [
        p.relative_to(REPO_ROOT).as_posix()
        for p in readers
        if "is_group_row" not in p.read_text() and "is_criterion_row" not in p.read_text()
    ]
    assert not bare, f"filter group rows beside display columns (is_criterion_row): {bare}"
