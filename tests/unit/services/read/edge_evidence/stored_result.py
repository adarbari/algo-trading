"""The stored result the edge evidence tests read: ``drift``'s canonical run with a per-session
series of ``momo`` (a 20-session window each Monday), and the read context of a session."""

from datetime import date, timedelta
from typing import Any

from algotrade.services.read.context import ReadContext
from algotrade.services.read.edge_evidence.basis import OfficialBasis, official_basis
from algotrade.services.read.edge_evidence.series import BasisSeries, load_basis_series
from algotrade.services.read.evaluation.edges import load_edge
from algotrade.services.read.values import Unknown
from algotrade.storage.backends.memory import MemoryBackend
from tests.unit.services.read.edge_desk.conftest import context
from tests.unit.services.read.evaluation.conftest import FROZEN, series_row, write_run

FIRST = FROZEN - timedelta(days=120)
# 30 days apart is at least 20 sessions: windows of 20 sessions do not overlap, so every weight is 1
DAYS = [FIRST + timedelta(days=30 * i) for i in range(8)]  # four before the split, then FROZEN on
EXIT = timedelta(days=29)


def stored_run(
    backend: MemoryBackend, rows: list[dict[str, Any]] | None = None, **kw: Any
) -> list[dict[str, Any]]:
    """Write ``drift``'s canonical run with ``rows`` (default: one measured window per ``DAYS``
    entry) as its series; the rows are returned."""
    found = rows if rows is not None else [series_row(d, FROZEN, pick_mean=0.01) for d in DAYS]
    write_run(backend, "r1", FROZEN, 0.6, series=found, **kw)
    return found


def read(backend: MemoryBackend, day: date = date(2026, 10, 5)) -> ReadContext:
    return context(backend, day)


def basis_of(ctx: ReadContext) -> OfficialBasis:
    edge = load_edge(ctx, "drift")
    assert edge is not None
    return official_basis(ctx, edge)


def series_of(ctx: ReadContext) -> BasisSeries | Unknown:
    return load_basis_series(ctx, basis_of(ctx))
