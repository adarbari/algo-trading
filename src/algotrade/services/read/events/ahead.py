"""What is ahead of a set of instruments as of one session (ADR 0050, the ``ahead`` of
``InstrumentEvents`` and the ``EventCalendar``): the dated events from the session through an
end date, each an ``AheadEvent`` with its label, time, source and ``known_from``.

- ``own_earnings``: the next report date, its time and whether it is confirmed, read by
  catalogue name (``rollup.earnings@v1.*`` through ``load_feature_values``, ADR 0038; exactly
  the session's partition, ADR 0036), never from ``events/earnings`` directly;
- ``reference_earnings``: the same for the stock a leveraged or inverse fund tracks
  (``reference.load_fund_references``);
- ``macro_release``: the ``events/macro_release`` rows known on or before the session
  (``known_from``, ADR 0050 decision 3) still ``scheduled`` in their latest version known by it
  (a ``released`` row is behind us; a ``moved`` row is a date FRED no longer lists, its new
  date being a row of its own);
- ``market_structure``: the monthly and quarterly option expiries, quarter ends and the Russell
  reconstitution, by rule (``market_days``).

Catalogue values carry no ``known_from`` (the session's value is what the session knew); a
rule-based day has none either. What could not be read is a gap (``EventGap``: the part and
its UNKNOWN), never an empty list passed off as "nothing ahead"."""

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade.data.events import ALL_TIME, known_from, read_events
from algotrade.services.read.context import ReadContext
from algotrade.services.read.events.market_days import MarketDay, market_days
from algotrade.services.read.events.reference import FundReference, load_fund_references
from algotrade.services.read.instruments.features import FeatureValue, load_feature_values
from algotrade.services.read.instruments.identity import load_instruments
from algotrade.services.read.values import Unknown, UnknownCode

OWN_EARNINGS, REFERENCE_EARNINGS = "own_earnings", "reference_earnings"
MACRO_RELEASE, MARKET_STRUCTURE = "macro_release", "market_structure"
KINDS = (OWN_EARNINGS, REFERENCE_EARNINGS, MACRO_RELEASE, MARKET_STRUCTURE)
REFERENCE = "reference"  # the gap part of a fund whose reference is not known
NEXT_DATE = "rollup.earnings@v1.next_earnings_date"
EARNINGS_TIME = "rollup.earnings@v1.earnings_time"
CONFIRMED = "rollup.earnings@v1.date_confirmed"
EARNINGS = (NEXT_DATE, EARNINGS_TIME, CONFIRMED)
MACRO_TABLE = "events/macro_release"
SCHEDULED = "scheduled"
# earnings@v1.earnings_time -> the event's time (the 8-K rows' intraday passes through).
TIMES = {"pre": "pre_market", "post": "after_hours", "intraday": "intraday"}
TIME_WORDS = {"pre_market": "before the open", "after_hours": "after the close"}
CLOSE = "close"  # the time of a market-structure day: it happens at the close
RULE = "exchange calendar rule"  # the source of a market-structure day


@dataclass(frozen=True)
class AheadEvent:
    """One dated event ahead. ``time``: pre_market | intraday | after_hours | unknown for a
    report, the release time (``08:30 ET``) for a macro release, ``close`` for a market-
    structure day; ``kind``: own_earnings | reference_earnings | macro_release |
    market_structure; ``label``: short (``Own earnings``, ``NVDA earnings``, ``CPI``,
    ``Quarterly expiry``), ``name``: what it is in words; ``subject_id``: whose event (the
    instrument, the fund's reference, the ``MACRO:`` release; None for a market-structure day);
    ``source``: the catalogue field, the stored row's source or the calendar rule;
    ``known_from``: the first session the stored row was known on (None: a catalogue value, which
    is what the session knew, or a rule)."""

    date: dt.date
    time: str
    kind: str
    label: str
    name: str
    subject_id: str | None
    source: str
    known_from: dt.date | None


@dataclass(frozen=True)
class EventGap:
    """A part of the events read that is not known for the session: ``part`` is the kind of
    event (own_earnings, reference_earnings, macro_release), ``reference``, ``filings`` or
    ``ladder``; ``instrument_id`` None for a market-wide part (the macro calendar)."""

    instrument_id: str | None
    part: str
    unknown: Unknown


@dataclass(frozen=True)
class Ahead:
    """What is ahead through ``end``: each name's own events (``own_earnings``,
    ``reference_earnings``), the market-wide ones (macro releases, market-structure days), the
    funds' references, each name's gaps and the market-wide gaps (``instrument_id`` None)."""

    end: date
    by_name: dict[str, tuple[AheadEvent, ...]]
    market: tuple[AheadEvent, ...]
    references: dict[str, FundReference]
    gaps: dict[str, tuple[EventGap, ...]]
    market_gaps: tuple[EventGap, ...]


def order(event: AheadEvent) -> tuple[date, int, str]:
    """Events by date, then kind (own, reference, macro, market), then label."""
    return (event.date, KINDS.index(event.kind), event.label)


def _earnings(
    values: tuple[FeatureValue, ...],
    kind: str,
    start: date,
    end: date,
    subject: str,
    who: str | None,
) -> AheadEvent | Unknown | None:
    """The next report as an event in ``start..end`` (None: later), else its UNKNOWN.
    ``who``: the reference's symbol (None: the instrument's own report)."""
    when, time_label, confirmed = values
    if when.unknown is not None:
        return when.unknown
    day = date.fromisoformat(str(when.value))
    if not start <= day <= end:
        return None
    time = TIMES.get(str(time_label.value), "unknown")
    words = TIME_WORDS.get(time, "time not announced")
    status = "confirmed" if confirmed.value is True else "not confirmed"
    return AheadEvent(
        date=day,
        time=time,
        kind=kind,
        label=f"{who} earnings" if who else "Earnings",
        name=f"{f'{who} reports' if who else 'Reports'} {words} ({status})",
        subject_id=subject,
        source=NEXT_DATE,
        known_from=None,
    )


def _macro(ctx: ReadContext, end: date) -> tuple[tuple[AheadEvent, ...], Unknown | None]:
    """The scheduled macro releases of ``session..end`` known by the session; UNKNOWN when
    the calendar has nothing known by the session at all (NO_PARTITION), or no scheduled
    release dated on or after the session (NO_ROW: the calendar is not current)."""
    day = ctx.session.date
    frame = read_events(ctx.reader, MACRO_TABLE, day, ALL_TIME[1], through=day).frame
    frame = frame[frame["status"] == SCHEDULED] if not frame.empty else frame
    if frame.empty:
        anything = read_events(ctx.reader, MACRO_TABLE, *ALL_TIME, through=day).frame
        code, detail = (
            (UnknownCode.NO_PARTITION, "no release dates known by")
            if anything.empty
            else (UnknownCode.NO_ROW, "no future release dates known by")
        )
        return (), Unknown(code, f"{MACRO_TABLE} has {detail} the session {day.isoformat()}")
    days = pd.to_datetime(frame["release_date"]).dt.date
    frame = frame[days <= end]
    events = tuple(
        AheadEvent(
            date=pd.Timestamp(row["release_date"]).date(),
            time=f"{row['time_et']} ET",
            kind=MACRO_RELEASE,
            label=str(row["release_key"]),
            name=str(row["release_name"]),
            subject_id=str(row["instrument_id"]),
            source=str(row["source"]),
            known_from=pd.Timestamp(stamp).date(),
        )
        for row, stamp in zip(frame.to_dict("records"), known_from(frame), strict=True)
    )
    return events, None


def _market(day: MarketDay) -> AheadEvent:
    return AheadEvent(day.date, CLOSE, MARKET_STRUCTURE, day.label, day.name, None, RULE, None)


def load_ahead(ctx: ReadContext, instrument_ids: Sequence[str], end: date) -> Ahead:
    """What is ahead of ``instrument_ids`` from the session through ``end``: one feature read
    for the funds' references (ETFs only: a stock tracks nothing), one for the names' and the
    references' earnings, one read of the macro calendar."""
    start, ids = ctx.session.date, list(dict.fromkeys(instrument_ids))
    funds = [i for i, d in load_instruments(ctx, ids).items() if d.is_etf]  # no stock has one
    references, reference_gaps = load_fund_references(ctx, funds) if funds else ({}, {})
    linked = {f: r.instrument_id for f, r in references.items() if r.instrument_id is not None}
    symbols = {f: r.symbol for f, r in references.items() if r.symbol is not None}
    stocks = list(dict.fromkeys([*ids, *linked.values()]))
    earnings = load_feature_values(ctx, stocks, EARNINGS) if stocks else {}
    by_name: dict[str, list[AheadEvent]] = {iid: [] for iid in ids}
    gaps: dict[str, list[EventGap]] = {iid: [] for iid in ids}
    for iid, unknown in reference_gaps.items():
        gaps[iid].append(EventGap(iid, REFERENCE, unknown))
    asked: list[tuple[str, str, str, str | None]] = [(i, i, OWN_EARNINGS, None) for i in ids]
    asked += [
        (fund, stock, REFERENCE_EARNINGS, symbols.get(fund, stock))
        for fund, stock in linked.items()
    ]
    for iid, subject, kind, who in asked:
        found = _earnings(earnings[subject], kind, start, end, subject, who)
        if isinstance(found, AheadEvent):
            by_name[iid].append(found)
        elif isinstance(found, Unknown):
            gaps[iid].append(EventGap(iid, kind, found))
    macro, macro_gap = _macro(ctx, end)
    rules = (_market(d) for d in market_days(start, end))
    market = tuple(sorted((*macro, *rules), key=order))
    return Ahead(
        end=end,
        by_name={iid: tuple(sorted(events, key=order)) for iid, events in by_name.items()},
        market=market,
        references=references,
        gaps={iid: tuple(found) for iid, found in gaps.items()},
        market_gaps=(EventGap(None, MACRO_RELEASE, macro_gap),) if macro_gap else (),
    )
