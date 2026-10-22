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
from functools import partial

import pandas as pd

from algotrade.core.views.feature_view import FeatureValue as Scalar
from algotrade.data.events import (
    ALL_TIME,
    CLOSED_END_FUND_ROWS,
    NO_INSTRUMENT_ROWS,
    knowledge_bound,
    read_events,
)
from algotrade.data.reference import instruments, is_closed_end
from algotrade.services.read.context import Held, ReadContext
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
    """The stored ``events/*`` tables that can hold an instrument's rows (event grain:
    ``session.grain_of``), sorted: the CIK-keyed ones (``data.events.NO_INSTRUMENT_ROWS``)
    return nothing for an instrument and are never opened."""
    names = ctx.reader.table_names()
    tables = sorted(t for t in names if t.startswith(EVENTS_PREFIX) and t not in NO_INSTRUMENT_ROWS)
    assert all(grain_of(t) is Grain.EVENT for t in tables)
    return tuple(tables)


def _not_funds(ctx: ReadContext, instrument_ids: Sequence[str]) -> frozenset[str]:
    """The ids the session's reference snapshot HAS and says are not closed-end funds
    (``reference.is_closed_end``); an id it lacks, a reference taken after the session
    (``pre_snapshot``) or one without the columns is unknown, so never in the set."""
    ref = ctx.session.reference_snapshot
    if ref is None or ref > ctx.session.date or not instrument_ids:
        return frozenset()
    frame = instruments(ctx.reader, ctx.session.date, list(instrument_ids))
    if frame.empty or not {"instrument_id", "security_type", "name", "symbol"} <= set(frame):
        return frozenset()
    flags = is_closed_end(frame)
    return frozenset(frame.loc[~flags, "instrument_id"].astype(str)) - frozenset(
        frame.loc[flags, "instrument_id"].astype(str)
    )


def load_events(
    ctx: ReadContext, instrument_ids: Sequence[str], start: date | None, end: date | None
) -> dict[str, tuple[Event, ...]]:
    """Every event of each of ``instrument_ids`` with its event date in ``start..end``
    (None: unbounded) known on or before the session (facts of record: all), from every
    ``events/*`` table, sorted by date and table: one read for the instruments not yet held.
    An instrument with none has an empty tuple. Stored rows are the same for every viewer
    (no licence filter here), so each instrument's events are kept in one ``Held`` container
    per (session, own run, publish) in ``ctx.cache`` under (instrument, window): a page asked
    again reads nothing, and a publish makes the container unreachable (ADR 0022)."""
    first, last = start or ALL_TIME[0], end or ALL_TIME[1]
    key = ("instrument-events", ctx.session.date, ctx.reader.own_run, ctx.reader.version())
    held: Held[tuple[Event, ...]] = ctx.cache.get_or_compute(key, Held)
    missing = [i for i in dict.fromkeys(instrument_ids) if not held.holds((i, first, last))]
    fresh: dict[str, tuple[Event, ...]] | None = None

    def read(iid: str) -> tuple[Event, ...]:
        nonlocal fresh
        if fresh is None:
            fresh = _read_events(ctx, missing, first, last)
        return fresh.get(iid, ())

    grew = False
    out: dict[str, tuple[Event, ...]] = {}
    for iid in instrument_ids:
        out[iid], added = held.get_or_read((iid, first, last), partial(read, iid))
        grew = grew or added
    if grew:
        ctx.cache.put(key, held)  # its weight changed
    return out


def _read_events(
    ctx: ReadContext, instrument_ids: Sequence[str], first: date, last: date
) -> dict[str, tuple[Event, ...]]:
    """The uncached read of ``load_events``: one read per table for ``instrument_ids``."""
    found: dict[str, list[Event]] = {iid: [] for iid in instrument_ids}
    skip = _not_funds(ctx, instrument_ids)
    for table in event_tables(ctx):
        # a table of one instrument kind is never opened for instruments of another
        wanted = (
            [i for i in instrument_ids if i not in skip]
            if table in CLOSED_END_FUND_ROWS
            else list(instrument_ids)
        )
        if not wanted:
            continue
        through = knowledge_bound(table, ctx.session.date)
        frame = read_events(ctx.reader, table, first, last, wanted, through=through).frame
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
