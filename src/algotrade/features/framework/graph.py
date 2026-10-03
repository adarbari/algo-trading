"""The dependency graph between rollups: a rollup may read another rollup's output.

An input named ``rollups/instrument/<name>@v<N>`` is a dependency on that rollup.
``dependency_order`` sorts rollups so every rollup comes after the rollups it reads
(topological, stable: otherwise in the given order) and refuses an unknown dependency or a
cycle, so a bad graph fails when the registry is built, not halfway through a nightly run.
"""

from collections.abc import Iterable, Sequence

from algotrade.core.model.fields import ROLLUP_TABLE_PREFIX
from algotrade.features.framework.declaration import Rollup


def is_rollup_table(table: str) -> bool:
    return table.startswith(ROLLUP_TABLE_PREFIX)


def dependencies(rollup: Rollup) -> tuple[str, ...]:
    """The keys (``<name>@v<N>``) of the rollups ``rollup`` reads, in declared order."""
    return tuple(
        i.table.removeprefix(ROLLUP_TABLE_PREFIX) for i in rollup.inputs if is_rollup_table(i.table)
    )


def _cycle(pending: dict[str, Rollup]) -> list[str]:
    """One cycle among ``pending`` (each still has a pending dependency), as a key path."""
    key = next(iter(pending))
    path: list[str] = []
    while key not in path:
        path.append(key)
        key = next(d for d in dependencies(pending[key]) if d in pending)
    return [*path[path.index(key) :], key]


def dependency_order(rollups: Iterable[Rollup], stored_ok: bool = False) -> list[Rollup]:
    """``rollups`` with every dependency first. Raises ``ValueError`` on a dependency that is
    not among ``rollups`` (unless ``stored_ok``: it is read from the store), a duplicate key,
    or a cycle (naming it)."""
    given = list(rollups)
    by_key = {r.key: r for r in given}
    if len(by_key) != len(given):
        raise ValueError("rollups are listed twice")
    for r in given:
        unknown = [d for d in dependencies(r) if d not in by_key]
        if unknown and not stored_ok:
            raise ValueError(f"rollup {r.key} reads unregistered rollups {unknown}")
    done: list[Rollup] = []
    pending = dict(by_key)
    while pending:
        ready = [r for r in pending.values() if not any(d in pending for d in dependencies(r))]
        if not ready:
            raise ValueError(f"rollup dependency cycle: {' -> '.join(_cycle(pending))}")
        for r in ready:
            done.append(r)
            del pending[r.key]
    return done


def dependents(rollups: Sequence[Rollup], key: str) -> set[str]:
    """Every rollup that reads ``key``, directly or through another rollup."""
    out: set[str] = set()
    frontier = {key}
    while frontier:
        frontier = {r.key for r in rollups if r.key not in out and set(dependencies(r)) & frontier}
        out |= frontier
    return out
