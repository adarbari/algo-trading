"""A reader of ``results/rule_screen_values`` never shows a group row as a criterion (ADR 0071):
a module that filters rows with ``is_display_column``, or names the table or the display-column
mode, also filters with ``is_group_row`` (or uses ``is_criterion_row``, which is both), so the
next reader written cannot forget one. Only the schema and the writing side are exempt."""

from pathlib import Path

from tests.conftest import REPO_ROOT

SCANNED = ("src/algotrade", "apps", "libs")
EXEMPT = (
    "src/algotrade/storage/tables/schemas/results.py",  # defines the predicates
    "src/algotrade/storage/tables/schemas/registry.py",  # registers the spec; reads no rows
    "src/algotrade/services/screening/rule_results.py",  # the writer
    "src/algotrade/services/screening/run.py",  # publishes the writer's frames; reads none
    "apps/ingestion/algotrade_ingestion/tasks/screens/screen_values_recluster.py",  # as stored
    "apps/ingestion/algotrade_ingestion/tasks/framework/registry.py",  # names the task's tables
)
TOUCHES = ("is_display_column", "rule_screen_values", "RULE_SCREEN_VALUES", "DISPLAY_COLUMN_MODE")
SAFE = ("is_group_row", "is_criterion_row")


def _readers() -> list[Path]:
    return [
        path
        for root in SCANNED
        for path in (REPO_ROOT / root).rglob("*.py")
        if "node_modules" not in path.parts
        and path.relative_to(REPO_ROOT).as_posix() not in EXEMPT
        and any(t in path.read_text() for t in TOUCHES)
    ]


def test_a_reader_of_the_values_table_always_filters_group_rows() -> None:
    readers = _readers()
    assert readers, "the scan found no reader: the predicate moved"
    bare = [
        p.relative_to(REPO_ROOT).as_posix()
        for p in readers
        if not any(s in p.read_text() for s in SAFE)
    ]
    assert not bare, f"filter group rows beside display columns (is_criterion_row): {bare}"
