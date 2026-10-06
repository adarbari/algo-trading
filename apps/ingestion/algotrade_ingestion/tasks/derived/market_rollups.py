"""The ``market-rollups`` task: compute the market-entity feature groups (``entity="market"``,
ADR 0047) for a session, or a named subset, or backfill them over a range of sessions.

It is the one producer of ``rollups/market/<name>@v<N>`` (one ``MKT:US`` row per session,
recorded as the ``market-rollups`` run) and runs the same loop as the ``rollups`` task
(``rollups.compute_rollups``) over the market groups only. A market group reads the
instrument groups' stored rows, so the nightly runs this step after ``rollups``; it is not
critical: a failing market group never holds back the screens.

``TABLES`` (what the task may write) is each market group's table from the site config.
"""

from collections.abc import Sequence
from datetime import date

from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.derived.rollups import compute_rollups, tables_of
from algotrade_ingestion.tasks.framework.run import TaskContext

TASK = "market-rollups"
TABLES = tables_of("market")


def compute_market_rollups(
    ctx: TaskContext,
    session: date,
    start: date | None = None,
    end: date | None = None,
    only: Sequence[str] = (),
) -> RunRecord:
    """The market rollups for ``session``, or for every exchange session in ``start..end``."""
    return compute_rollups(ctx, session, start, end, only, entity="market")
