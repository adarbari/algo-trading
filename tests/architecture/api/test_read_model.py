"""READ 2 (docs/api/read-model.md "Enforcement"): only the read model's session plumbing picks
or reads a session partition. Loaders read a session-grain table through
``context.partition(ctx, table)`` for ``ctx.session.date`` (ADR 0036 decision 6): no
``StoreReader.table`` / ``require`` / ``table_range`` (a range read goes through ``data``'s
range functions with explicit dates), no ``dates`` / ``latest_date``, no ``snapshot``, no
``partition_for`` / ``latest_session`` / ``rollup_row`` / ``rollup_on`` of their own.

Scoped to ``services/read`` callers until read-model PR 10 widens it to all of ``src/`` and
``apps/`` (explore and the routes still read partitions until their area moves)."""

import ast

from tests.conftest import REPO_ROOT

READ_MODEL = REPO_ROOT / "src" / "algotrade" / "services" / "read"
# The session plumbing: session.py resolves (and lists present / missing), context.py reads.
PLUMBING = {"session.py", "context.py"}
PARTITION_READS = {
    "table", "require", "table_range", "dates", "latest_date", "snapshot", "read_snapshot",
    "partition_for", "latest_session", "rollup_row", "rollup_on",
}  # fmt: skip


def partition_reads(source: str) -> list[tuple[int, str]]:
    """``(line, callee)`` of every call in ``source`` that picks or reads a partition."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name in PARTITION_READS:
                found.append((node.lineno, name))
    return sorted(found)


def test_only_loaders_read_partitions() -> None:
    hits = [
        f"{path.relative_to(REPO_ROOT)}:{line} {name}()"
        for path in sorted(READ_MODEL.rglob("*.py"))
        if path.parent != READ_MODEL or path.name not in PLUMBING
        for line, name in partition_reads(path.read_text())
    ]
    assert not hits, (
        f"[READ 2 / ADR 0036] a loader picks or reads a partition itself: {hits}. Read a "
        "session-grain table with services.read.context.partition(ctx, table) (UNKNOWN when "
        "absent); other grains by their one rule (.claude/skills/add-domain-object step 2)"
    )


def test_the_plumbing_exists() -> None:
    assert {p.name for p in READ_MODEL.glob("*.py")} >= PLUMBING


def test_the_check_catches_a_loader_reading_a_partition() -> None:
    loader = (
        "def load(ctx):\n"
        "    day = ctx.reader.latest_date('rollups/instrument/x@v1')\n"
        "    return ctx.reader.table('rollups/instrument/x@v1', day), snapshot(ctx.reader, 'x')\n"
    )
    assert partition_reads(loader) == [(2, "latest_date"), (3, "snapshot"), (3, "table")]
    assert partition_reads("def load(ctx):\n    return partition(ctx, 't')\n") == []
