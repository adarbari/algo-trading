"""An instrument's events (ADR 0037 ``Event``): the rows of every ``events/*`` table (earnings,
dividends, splits, reference changes) with their event date in an explicit window.

Event grain (ADR 0007, docs/api/read-model.md "Session resolution"): an event is read by its
event date (``data.events.read_events``: the UTC date of ``ts``), never by the partition it
was stored in; the caller names the window (``start`` / ``end``, None: all time). The session
bounds what was known (ADR 0050 decision 3, ADR 0036 point 4): only rows known on or before
it are read (``known_from``, else the session that stored the row), and each event shows its
latest version among them, so a past session never shows an event or revision learned after
it, and a report backfilled later shows from its report date on. Facts of record (splits,
dividends, reference and index changes: ``data.events.knowledge_bound``) are read by event
date unbounded, as the adjusted bars use them (ADR 0016). The rows are what the
events list shows; the earnings dates a page reads as facts are catalogue features
(``rollup.earnings@v1.*``), never derived from these rows."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from algotrade.core.views.feature_view import FeatureValue as Scalar
from algotrade.data.events import ALL_TIME, knowledge_bound, read_events
from algotrade.services.read.context import ReadContext
from algotrade.services.read.session import Grain, grain_of
from algotrade.services.read.values import stored_values

EVENTS_PREFIX = "events/"


@dataclass(frozen=True)
class Event:
    """One stored event. ``table``: ``events/<kind>``; ``date``: the event date (UTC);
    ``values``: the row's other columns (point-in-time stamps dropped), JSON scalars."""

    instrument_id: str
    table: str
    kind: str
    date: date
    ts: datetime
    values: dict[str, Scalar]


def event_tables(ctx: ReadContext) -> tuple[str, ...]:
    """The stored ``events/*`` tables (event grain: ``session.grain_of``), sorted."""
    names = ctx.reader.table_names()
    tables = sorted(t for t in names if t.startswith(EVENTS_PREFIX))
    assert all(grain_of(t) is Grain.EVENT for t in tables)
    return tuple(tables)


def load_events(
    ctx: ReadContext, instrument_ids: Sequence[str], start: date | None, end: date | None
) -> dict[str, tuple[Event, ...]]:
    """Every event of each of ``instrument_ids`` with its event date in ``start..end``
    (None: unbounded) known on or before the session (facts of record: all), from every
    ``events/*`` table, sorted by date and table: one read per table for them all. An
    instrument with none has an empty tuple."""
    first, last = start or ALL_TIME[0], end or ALL_TIME[1]
    found: dict[str, list[Event]] = {iid: [] for iid in instrument_ids}
    for table in event_tables(ctx):
        through = knowledge_bound(table, ctx.session.date)
        frame = read_events(
            ctx.reader, table, first, last, list(instrument_ids), through=through
        ).frame
        for row in frame.to_dict("records"):
            ts = pd.Timestamp(row["ts"])
            ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
            iid = str(row["instrument_id"])
            values = stored_values(row, ("instrument_id", "ts"))
            kind = table.removeprefix(EVENTS_PREFIX)
            found.setdefault(iid, []).append(
                Event(iid, table, kind, ts.date(), ts.to_pydatetime(), values)
            )
    return {
        iid: tuple(sorted(events, key=lambda e: (e.ts, e.table))) for iid, events in found.items()
    }
