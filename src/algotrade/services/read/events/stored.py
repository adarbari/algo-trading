"""An instrument's events (ADR 0037 ``Event``): the rows of the ``events/*`` tables of the kinds
asked (the page: ``TIMELINE_KINDS``, the calendar kinds; no kinds: every table) with their event
date in an explicit window.

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
from dataclasses import dataclass, replace
from datetime import date, datetime
from functools import partial

import pandas as pd

from algotrade.config.site.settings import load_nightly
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.views.feature_view import FeatureValue as Scalar
from algotrade.data.events import ALL_TIME, NO_INSTRUMENT_ROWS, knowledge_bound, read_events
from algotrade.services.read.context import Held, ReadContext
from algotrade.services.read.events.filings import load_results_filings
from algotrade.services.read.events.links import source_link
from algotrade.services.read.session import Grain, grain_of
from algotrade.services.read.values import stored_values
from algotrade.storage.tables.schemas.events import EARNINGS_8K_SOURCE

EVENTS_PREFIX = "events/"

# The kinds the Explore events page, the chart and the overview show (owner decision 2026-10-22,
# docs/decisions/log.md "What the Explore Events tab shows", option F): the calendar kinds.
# ``Instrument.events`` reads these unless a caller names others (``kinds``).
TIMELINE_KINDS: tuple[str, ...] = (
    "dividend",
    "earnings",
    "index_change",
    "reference_change",
    "split",
)
# Every other stored ``events/*`` kind and why the timeline leaves it out: a new table joins the
# page only by being added to ``TIMELINE_KINDS`` (fitness test
# ``tests/architecture/api/test_events_timeline_kinds.py``), never by its prefix.
NOT_TIMELINE: dict[str, str] = {
    "bar_flag": "bars the quality check rejected (ADR 0061); applied to prices, not a dated event",
    "filing": "8-K and other filings: read by the event study (``event_study``), no detail line",
    "filing_text": "10-K / 10-Q item text by CIK (``NO_INSTRUMENT_ROWS``): none per instrument",
    "fund_nav": "a closed-end fund's NAV per day: a series (``cef_nav`` features), not an event",
    "insider_transaction": "Form 4 lines (968 for AAPL): ``insider_buys`` features, no detail line",
    "ipo_lockup": "424B4 lock-ups: read as ``ipo_lockup`` features, not shown on the page",
    "macro_release": "the release calendar: market-wide, read by the event study",
    "short_interest": "FINRA short interest: a series (``short_interest`` features), not an event",
    "short_volume": "FINRA daily short volume: a series (features), not an event",
}


@dataclass(frozen=True)
class Event:
    """One stored event. ``table``: ``events/<kind>``; ``date``: the event date (UTC);
    ``values``: the row's other columns (point-in-time stamps dropped), JSON scalars;
    ``source_url``: the page the row came from (``links.source_link``: a report stored from an
    8-K, its filing index; None for every other row)."""

    instrument_id: str
    table: str
    kind: str
    date: date
    ts: datetime
    values: dict[str, Scalar]
    source_url: str | None = None


def event_tables(ctx: ReadContext, kinds: Sequence[str] | None = None) -> tuple[str, ...]:
    """The stored ``events/*`` tables that can hold an instrument's rows (event grain:
    ``session.grain_of``), sorted: the CIK-keyed ones (``data.events.NO_INSTRUMENT_ROWS``)
    return nothing for an instrument and are never opened. ``kinds``: only the tables of these
    kinds (None: every kind)."""
    names = ctx.reader.table_names()
    tables = sorted(
        t
        for t in names
        if t.startswith(EVENTS_PREFIX)
        and t not in NO_INSTRUMENT_ROWS
        and (kinds is None or t.removeprefix(EVENTS_PREFIX) in kinds)
    )
    assert all(grain_of(t) is Grain.EVENT for t in tables)
    return tuple(tables)


def warm_event_copies(ctx: ReadContext) -> tuple[str, ...]:
    """Validate the history copy (ADR 0060) of every ``[history_copy] event_tables`` table for
    all years, so the first events read after a start or a publish finds each partition index's
    digest held instead of reading one file per stored day (about 8,400 for ``events/fund_nav``);
    the tables validated, in name order (none when the copy is off)."""
    settings = load_nightly(ctx.configs).history_copy
    tables = tuple(sorted(settings.event_tables)) if settings.enabled else ()
    for table in tables:
        ctx.reader.warm_history(table)
    return tables


def load_events(
    ctx: ReadContext,
    instrument_ids: Sequence[str],
    start: date | None,
    end: date | None,
    kinds: tuple[str, ...] | None = None,
) -> dict[str, tuple[Event, ...]]:
    """Every event of each of ``instrument_ids`` with its event date in ``start..end``
    (None: unbounded) known on or before the session (facts of record: all), from the
    ``events/*`` tables of ``kinds`` (None: every table; the page asks ``TIMELINE_KINDS``;
    the tables of other kinds are not opened), sorted by date and table: one read for the
    instruments not yet held.
    An instrument with none has an empty tuple. Stored rows are the same for every viewer
    (no licence filter here), so each instrument's events are kept in one ``Held`` container
    per (session, own run, publish) in ``ctx.cache`` under (instrument, window, kinds): a page asked
    again reads nothing, and a publish makes the container unreachable (ADR 0022)."""
    first, last = start or ALL_TIME[0], end or ALL_TIME[1]
    key = ("instrument-events", ctx.session.date, ctx.reader.own_run, ctx.reader.version())
    held: Held[tuple[Event, ...]] = ctx.cache.get_or_compute(key, Held)
    missing = [i for i in dict.fromkeys(instrument_ids) if not held.holds((i, first, last, kinds))]
    fresh: dict[str, tuple[Event, ...]] | None = None

    def read(iid: str) -> tuple[Event, ...]:
        nonlocal fresh
        if fresh is None:
            fresh = _read_events(ctx, missing, first, last, kinds)
        return fresh.get(iid, ())

    grew = False
    out: dict[str, tuple[Event, ...]] = {}
    for iid in instrument_ids:
        out[iid], added = held.get_or_read((iid, first, last, kinds), partial(read, iid))
        grew = grew or added
    if grew:
        ctx.cache.put(key, held)  # its weight changed
    return out


def load_timeline_events(
    ctx: ReadContext,
    instrument_ids: Sequence[str],
    start: date | None,
    end: date | None,
    kinds: tuple[str, ...] | None = None,
) -> dict[str, tuple[Event, ...]]:
    """``load_events`` for a page: ``kinds`` None is ``TIMELINE_KINDS`` (the calendar kinds);
    a kind that is neither on the timeline nor in ``NOT_TIMELINE`` is a ``ConfigurationError``
    (a typo is loud; a declared kind with no stored table is simply empty)."""
    unknown = sorted(set(kinds or ()) - set(TIMELINE_KINDS) - set(NOT_TIMELINE))
    if unknown:
        known = sorted({*TIMELINE_KINDS, *NOT_TIMELINE})
        raise ConfigurationError(f"unknown event kind(s) {unknown}; the kinds are {known}")
    asked = TIMELINE_KINDS if kinds is None else tuple(sorted(set(kinds)))
    return load_events(ctx, instrument_ids, start, end, asked)


def _read_events(
    ctx: ReadContext,
    instrument_ids: Sequence[str],
    first: date,
    last: date,
    kinds: tuple[str, ...] | None,
) -> dict[str, tuple[Event, ...]]:
    """The uncached read of ``load_events``: one read per table of ``kinds``."""
    found: dict[str, list[Event]] = {iid: [] for iid in instrument_ids}
    from_8k: list[Event] = []  # reports stored from an 8-K: their page is its Item 2.02 filing
    for table in event_tables(ctx, kinds):
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
            event = Event(iid, table, kind, ts.date(), ts.to_pydatetime(), values)
            found.setdefault(iid, []).append(event)
            if kind == "earnings" and row.get("source") == EARNINGS_8K_SOURCE:
                from_8k.append(event)
    links = _links(ctx, from_8k)
    return {
        iid: tuple(sorted((links.get(id(e), e) for e in events), key=lambda e: (e.ts, e.table)))
        for iid, events in found.items()
    }


def _links(ctx: ReadContext, reports: Sequence[Event]) -> dict[int, Event]:
    """Each report stored from an 8-K with its ``source_url`` (the Item 2.02 filing it came
    from; none found: the report as it is), keyed by the identity of the event it replaces."""
    filings = load_results_filings(ctx, [e.instrument_id for e in reports])
    out: dict[int, Event] = {}
    for event in reports:
        url = source_link(
            event.kind,
            source=EARNINGS_8K_SOURCE,
            at=event.ts,
            filings=filings.get(event.instrument_id, ()),
        )
        if url is not None:
            out[id(event)] = replace(event, source_url=url)
    return out
