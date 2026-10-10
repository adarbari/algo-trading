"""Fitness: production code publishes table writes pending (ADR 0022, ADR 0063).

A write that is not ``pending=True`` is visible at once and carries no commit sequence, so
``partition_seq`` stamps its partition 0 and a reader can never tell it was rewritten. Every
call of a table write outside ``storage/backends/`` therefore passes ``pending=True`` (or, in the
two write facades that forward their caller's choice, ``pending=pending``)."""

import ast
from pathlib import Path

ROOT = Path(__file__).parents[3]
SOURCES = ("src", "apps", "libs")
WRITES = {"write_table", "write_result"}
FORWARDERS = {  # facades whose own parameter carries the caller's choice
    "src/algotrade/storage/tables/writers.py",
    "src/algotrade/storage/tables/result_writer.py",
}


def _is_table_write(call: ast.Call) -> bool:
    func = call.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr in WRITES:
        return True
    # ``<backend>.tables.write(...)``
    return (
        func.attr == "write"
        and isinstance(func.value, ast.Attribute)
        and func.value.attr == "tables"
    )


def _pending(call: ast.Call, forwarding: bool) -> bool:
    for keyword in call.keywords:
        if keyword.arg == "pending":
            value = keyword.value
            if isinstance(value, ast.Constant):
                return value.value is True
            return forwarding and isinstance(value, ast.Name) and value.id == "pending"
    return False


def test_production_table_writes_are_pending() -> None:
    offenders = []
    for top in SOURCES:
        for path in sorted((ROOT / top).rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            if "/storage/backends/" in rel or "/node_modules/" in rel or "/.venv/" in rel:
                continue
            for node in ast.walk(ast.parse(path.read_text())):
                is_write = isinstance(node, ast.Call) and _is_table_write(node)
                if is_write and not _pending(node, rel in FORWARDERS):  # type: ignore[arg-type]
                    offenders.append(f"{rel}:{node.lineno}")  # type: ignore[attr-defined]
    assert not offenders, f"table writes without pending=True (ADR 0063): {offenders}"
