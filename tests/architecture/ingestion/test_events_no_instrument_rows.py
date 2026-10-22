"""Every events table whose writer stores ``instrument_id`` NULL is in
``data.events.NO_INSTRUMENT_ROWS`` (the tables a per-instrument events read never opens), and
nothing else is: a new CIK-keyed table cannot be silently decoded per instrument (47 s of
``events/filing_text`` read for 0 rows). A writer module is one under ``tasks/events/`` that
names its ``TABLE`` and builds rows with a literal ``instrument_id=None`` / ``"instrument_id":
None``; a table that stores the id on a later version (``events/ipo_lockup``) passes it through
a parameter and is not a literal."""

import ast

from algotrade.data.events import NO_INSTRUMENT_ROWS
from tests.conftest import REPO_ROOT

WRITERS = REPO_ROOT / "apps" / "ingestion" / "algotrade_ingestion" / "tasks" / "events"


def _is_none(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _stores_null_id(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "instrument_id" and _is_none(node.value):
            return True
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                named = isinstance(key, ast.Constant) and key.value == "instrument_id"
                if named and _is_none(value):
                    return True
    return False


def _table_of(tree: ast.Module) -> str | None:
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "TABLE" for t in node.targets)
            and isinstance(node.value, ast.Constant)
        ):
            return str(node.value.value)
    return None


def _null_id_tables() -> set[str]:
    found: set[str] = set()
    for path in sorted(WRITERS.glob("*.py")):
        tree = ast.parse(path.read_text())
        table = _table_of(tree)
        if table is not None and _stores_null_id(tree):
            found.add(table)
    return found


def test_the_tables_whose_writer_stores_no_instrument_id_are_declared() -> None:
    assert _null_id_tables() == set(NO_INSTRUMENT_ROWS)


def test_the_declared_tables_are_events_tables() -> None:
    assert all(t.startswith("events/") for t in NO_INSTRUMENT_ROWS)
