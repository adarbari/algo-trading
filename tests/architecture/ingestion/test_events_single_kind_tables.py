"""Every table in ``data.events.CLOSED_END_FUND_ROWS`` (the tables a per-instrument events read
leaves out for an instrument that is not a closed-end fund) has a writer that selects its
instruments with ``data.reference.is_closed_end``, the same test the read side applies, and
nothing else writes a table of this kind unlisted: the writer module names its ``TABLE`` and
filters the reference with ``is_closed_end``. The kind is data-dependent (the reference's
``security_type`` and name), so the fitness is that the writer and the reader share the one
predicate."""

import ast

from algotrade.data.events import CLOSED_END_FUND_ROWS
from tests.architecture.ingestion.test_events_no_instrument_rows import WRITERS, _table_of


def _imports_and_calls_predicate(tree: ast.Module) -> bool:
    imported = any(
        isinstance(n, ast.ImportFrom)
        and n.module == "algotrade.data.reference"
        and any(a.name == "is_closed_end" for a in n.names)
        for n in ast.walk(tree)
    )
    called = any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "is_closed_end"
        for n in ast.walk(tree)
    )
    return imported and called


def _writers_of_declared_tables() -> dict[str, bool]:
    found: dict[str, bool] = {}
    for path in sorted(WRITERS.rglob("*.py")):
        tree = ast.parse(path.read_text())
        table = _table_of(tree)
        if table in CLOSED_END_FUND_ROWS:
            found[table] = found.get(table, False) or _imports_and_calls_predicate(tree)
    return found


def test_each_declared_single_kind_table_has_a_writer_selecting_by_the_shared_predicate() -> None:
    found = _writers_of_declared_tables()
    assert set(found) == set(CLOSED_END_FUND_ROWS)
    assert all(found.values()), found


def test_the_declared_tables_are_events_tables() -> None:
    assert all(t.startswith("events/") for t in CLOSED_END_FUND_ROWS)
