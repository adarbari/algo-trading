"""The ``attribution`` task: why each big mover of a session moved, from the SEC 8-K filed for its
reaction session -> ``events/attribution`` (ADR 0050 decisions 4-5, EV4a; ``source = "filing"``).

The movers are the session's ``event_reaction@v1`` rows beyond 5% or 2 normal days
(``big_move_5pct_today`` / ``big_move_2x_today``), so the task runs after the ``rollups`` step; a
session with no ``event_reaction`` rows is SKIPPED (nothing to attribute), never an empty success.
The filings are ``events/filing`` 8-Ks whose acceptance session is the session
(``events_by_acceptance``); the item codes name the cause (``services.attributing``, model-free).
Headlines classified by the text model (EV4b) are a later source of the same table. A rerun of a
session stores the same rows again: the table merges on instrument, session and source.
"""

from datetime import date

import pandas as pd

from algotrade.data.events import events_by_acceptance
from algotrade.data.rollups import rollup_on
from algotrade.services.attributing.filing import attribute_from_filings
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.schemas import ATTRIBUTION_EVENTS, FILING_EVENTS
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext

TASK = "attribution"
TABLE = ATTRIBUTION_EVENTS.name
FILINGS = FILING_EVENTS.name
REACTION = "rollups/instrument/event_reaction@v1"
SOURCE = "filing"
FLAGS = ("big_move_5pct_today", "big_move_2x_today")


def big_movers(reaction: pd.DataFrame) -> set[str]:
    """The instruments whose move on the session is big by either flag (a null flag is no move)."""
    flagged = pd.Series(False, index=reaction.index)
    for flag in FLAGS:
        if flag in reaction.columns:
            flagged |= reaction[flag].fillna(0).astype(float) > 0
    return set(reaction.loc[flagged, "instrument_id"].astype(str))


def ingest_attribution(ctx: TaskContext, session: date) -> RunRecord:
    """Store the filing-attributed causes of ``session``'s big movers."""
    with IngestRun(ctx, TASK, session) as run:
        reaction = rollup_on(run.reader, REACTION, session)
        if reaction is None:
            run.record_item("movers", f"SKIPPED: no {REACTION} rows for {session}")
            run.stats.update(movers=None, rows=0)
            return run.record
        movers = big_movers(reaction)
        filings = events_by_acceptance(run.reader, FILINGS, session, session)
        if "form" in filings.columns:  # only 8-Ks carry the items that name a cause
            filings = filings[filings["form"].astype(str).str.startswith("8-K")]
        rows = attribute_from_filings(movers, filings, session)
        if not rows.empty:
            run.stage(TABLE, session.isoformat(), rows, SOURCE)
        written = run.publish(TABLE)
        run.record_item("movers", f"OK: {len(movers)} movers, {written} attributed")
        run.stats.update(movers=len(movers), rows=written, unattributed=len(movers) - written)
    return run.record
