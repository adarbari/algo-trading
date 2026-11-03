"""The ``attribution`` task: why each big mover of a session moved, from the SEC 8-K filed for its
reaction session -> ``events/attribution`` (ADR 0050 decisions 4-5, EV4a; ``source = "filing"``).

The movers are the session's ``event_reaction@v1`` rows beyond 5% or 2 normal days
(``big_move_5pct_today`` / ``big_move_2x_today``), so the task runs after the ``rollups`` step; a
session with no ``event_reaction`` rows is SKIPPED (nothing to attribute), never an empty success.
The filings are ``events/filing`` 8-Ks whose acceptance session is the session
(``events_by_acceptance``); the item codes name the cause (``services.attributing``, model-free).
Every mover is attributed, an earnings day included (its 8-K Item 2.02 is the cause: `results`).
The last ``LOOKBACK`` sessions are re-read each run, so a filing stored after its session was
first read (the daily index is a night behind, a catch-up session skips the filings step) is
picked up. Headlines classified by the text model (EV4b) are a later source of the same table. A
rerun stores the same rows: the table merges on instrument, session and source."""

from datetime import date

import pandas as pd

from algotrade.core.time.calendar import sessions_ending
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
LOOKBACK = 5  # sessions re-attributed each run


def big_movers(reaction: pd.DataFrame) -> set[str]:
    """The instruments whose move on the session is big by either flag (a null flag is no move);
    a rollup frame with neither flag column is an error, not "no movers"."""
    present = [f for f in FLAGS if f in reaction.columns]
    if not present:
        raise ValueError(f"{REACTION} has none of the columns {FLAGS}")
    flagged = pd.Series(False, index=reaction.index)
    for flag in present:
        flagged |= reaction[flag].fillna(0).astype(float) > 0
    return set(reaction.loc[flagged, "instrument_id"].astype(str))


def attribute_session(run: IngestRun, day: date) -> tuple[pd.DataFrame | None, int]:
    """``(attribution rows of day, movers)``; rows None when the session has no rollup yet."""
    reaction = rollup_on(run.reader, REACTION, day)
    if reaction is None:
        return None, 0
    movers = big_movers(reaction)
    filings = events_by_acceptance(run.reader, FILINGS, day, day)
    if "form" in filings.columns:  # only 8-Ks carry the items that name a cause
        filings = filings[filings["form"].astype(str).str.startswith("8-K")]
    return attribute_from_filings(movers, filings, day), len(movers)


def ingest_attribution(ctx: TaskContext, session: date) -> RunRecord:
    """Store the filing-attributed causes of the big movers of the last ``LOOKBACK`` sessions
    ending at ``session``: a night re-reads a few sessions so a filing stored late (a catch-up
    session, an index day read next) is attributed; the merge keeps a rerun idempotent."""
    with IngestRun(ctx, TASK, session) as run:
        parts, movers, missing = [], 0, []
        for day in sessions_ending(session, LOOKBACK):
            rows, n = attribute_session(run, day)
            if rows is None:
                missing.append(day.isoformat())
                continue
            movers += n
            if not rows.empty:
                parts.append(rows.assign(session_date=day))
        if len(missing) == LOOKBACK:
            run.record_item("movers", f"SKIPPED: no {REACTION} rows for {session}")
            run.stats.update(movers=None, rows=0, missing=missing)
            return run.record
        if parts:
            run.stage_sessions(TABLE, session.isoformat(), pd.concat(parts), SOURCE)
        written = sum(run.publish_sessions(TABLE).values())
        run.record_item("movers", f"OK: {movers} movers, {written} attributed")
        run.stats.update(movers=movers, rows=written, missing=missing)
    return run.record
