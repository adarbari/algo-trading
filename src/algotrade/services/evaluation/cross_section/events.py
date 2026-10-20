"""The names an event schedule triggers on at each decision session D (ADR 0053 amendment of
2026-10-08, decision 7): never an event table read at the entry session, always a declared field
of a feature group read at D (one session, through the existing feature reads), so an event not
yet known at D is absent by construction.

Each event class names a count field and a date field (``EVENT_FIELDS``). With the entry
session S = anchor + offset and D = S - 1, a name has the event at D when its count field reads
``sign * (offset - 1)``: ``earnings_reaction@v1.sessions_since_reaction == offset - 1`` and
``earnings_expected@v1.sessions_to_expected_report == 1 - offset``. A name with no value in the
count field is UNKNOWN (counted with its reason, never read as "no event"); a reaction whose
date is after D is not known at D and is excluded the same way. An event is counted once per
name within ``DEDUPE_SESSIONS`` sessions: a PRIOR_YEAR expectation that turns SCHEDULED, or a
report date that moves, can match on two decision sessions (even across a quarter end), and
only the earlier one counts.

**Subtypes** (``on_event:<class>:<subtype>``, EB H4): a class may declare ``subtypes``, each its own
count and date fields (an 8-K item) or a ``field`` that must read ``value`` (an index addition:
``last_index_change`` reads ``sp500_added``) beside the class's own. An unknown subtype, or none
for a class whose fields are all per subtype, is a ``ConfigurationError``; a name whose count
is at the target but whose subtype field is another value is no event of this subtype (not
UNKNOWN), one with no value there is UNKNOWN (``NO_EVENT_ROW``).
"""

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any

from algotrade.core.model.errors import ConfigurationError, MissingDataError
from algotrade.core.time.calendar import sessions_to
from algotrade.data import StoreReader
from algotrade.services.licences import HARNESS_ALL
from algotrade.services.selection import fields_view

ADDED, REMOVED = "sp500_added", "sp500_removed"  # ``index_changes@v1.last_index_change``
SHIFT_DIRECTION = "rollup.earnings_date_shift@v1.earnings_shift_direction"
LOCKUP_TERMS = "rollup.ipo_lockups@v1.lockup_release_terms"
ETF_CATEGORY = "rollup.etf_launches@v1.etf_category"
DEDUPE_SESSIONS = 40  # one report per name in this many sessions
NO_EVENT_ROW = "no_event_row"  # eligible at D, but the event field has no value for the name
NOT_KNOWN_AT_D = "event_not_known_at_decision"  # the field's event date is after D


class EventDayMissingError(MissingDataError):
    """An event field has no data for a decision session: ``day`` says which (a lookback day
    of the paper record is not tonight)."""

    def __init__(self, error: MissingDataError, day: date) -> None:
        super().__init__(error.dataset, str(error), "see the first error")
        self.day = day


@dataclass(frozen=True)
class Subtype:
    """One subtype of a class: its own ``count`` and ``date`` fields (None: the class's), and,
    when set, the label ``field`` that must read ``value`` for the name to have it."""

    count: str | None = None
    date: str | None = None
    field: str | None = None
    value: str | None = None


@dataclass(frozen=True)
class EventField:
    """Where one event class is read: ``count`` (the field whose value says how far D is from
    the anchor, scaled by ``sign``), ``date`` (the event's date), and whether the event is
    announced ahead (its date may be after D; otherwise it must be on or before D).
    ``subtypes``: the class's subtypes (module doc); ``where``: the (field, value) a resolved
    subtype requires. An empty ``count`` means every field is per subtype."""

    count: str
    date: str
    sign: int
    announced_ahead: bool
    subtypes: Mapping[str, Subtype] = field(default_factory=dict)
    where: tuple[str, str] | None = None

    def target(self, offset: int) -> int:
        return self.sign * (offset - 1)

    def fields(self) -> tuple[str, ...]:
        """The field names one read of this (resolved) class needs."""
        return (self.count, self.date, *(self.where[:1] if self.where else ()))


EVENT_FIELDS: Mapping[str, EventField] = {
    "earnings_reaction": EventField(
        "rollup.earnings_reaction@v1.sessions_since_reaction",
        "rollup.earnings_reaction@v1.reaction_end_date",
        sign=1,
        announced_ahead=False,
    ),
    "earnings_expected": EventField(
        "rollup.earnings_expected@v1.sessions_to_expected_report",
        "rollup.earnings_expected@v1.expected_report_date",
        sign=-1,
        announced_ahead=True,
    ),
    "index_change": EventField(
        "rollup.index_changes@v1.sessions_since_index_change",
        "rollup.index_changes@v1.last_index_change_date",
        sign=1,
        announced_ahead=False,
        subtypes={
            "addition": Subtype(field="rollup.index_changes@v1.last_index_change", value=ADDED),
            "deletion": Subtype(field="rollup.index_changes@v1.last_index_change", value=REMOVED),
        },
    ),
    "filing_8k": EventField(
        "", "", sign=1, announced_ahead=False,
        subtypes={
            item: Subtype(
                count=f"rollup.filing_events@v1.sessions_since_8k_{item.replace('.', '_')}",
                date=f"rollup.filing_events@v1.last_8k_{item.replace('.', '_')}_date",
            )
            for item in ("1.02", "2.05", "3.01", "4.01", "4.02", "5.02")
        },
    ),
    "nt_late_filing": EventField(
        "rollup.filing_events@v1.sessions_since_late_filing",
        "rollup.filing_events@v1.last_late_filing_date",
        sign=1,
        announced_ahead=False,
    ),
    "tender_offer": EventField(
        "rollup.filing_events@v1.sessions_since_tender_offer",
        "rollup.filing_events@v1.last_tender_offer_date",
        sign=1,
        announced_ahead=False,
    ),
    "earnings_date_shift": EventField(
        "rollup.earnings_date_shift@v1.sessions_since_earnings_shift",
        "rollup.earnings_date_shift@v1.earnings_shift_known_date",
        sign=1,
        announced_ahead=False,
        subtypes={
            "later": Subtype(field=SHIFT_DIRECTION, value="later"),
            "earlier": Subtype(field=SHIFT_DIRECTION, value="earlier"),
        },
    ),
    "ipo_lockup": EventField(
        "rollup.ipo_lockups@v1.sessions_to_lockup_expiry",
        "rollup.ipo_lockups@v1.lockup_expiry_date",
        sign=-1,
        announced_ahead=True,
        subtypes={
            "standard": Subtype(field=LOCKUP_TERMS, value="standard"),
            "early_release": Subtype(field=LOCKUP_TERMS, value="early_release"),
        },
    ),
    "etf_launch": EventField(
        "rollup.etf_launches@v1.sessions_since_etf_launch",
        "rollup.etf_launches@v1.last_etf_launch_date",
        sign=1,
        announced_ahead=False,
        subtypes={
            "thematic": Subtype(field=ETF_CATEGORY, value="thematic"),
            "sector": Subtype(field=ETF_CATEGORY, value="sector"),
        },
    ),
    "reverse_split": EventField(
        "rollup.reverse_splits@v1.sessions_since_reverse_split",
        "rollup.reverse_splits@v1.last_reverse_split_date",
        sign=1,
        announced_ahead=False,
    ),
}  # fmt: skip


@dataclass(frozen=True)
class EventSchedule:
    """The event names by decision session (only sessions with at least one), and, per
    session where some name had the event, the names excluded as UNKNOWN by reason."""

    names: Mapping[date, frozenset[str]]
    unknown: Mapping[date, Mapping[str, int]]

    def unknown_total(self) -> Mapping[str, int]:
        total: Counter[str] = Counter()
        for reasons in self.unknown.values():
            total.update(reasons)
        return dict(total)


def event_field(event_class: str, subtype: str | None = None) -> EventField:
    """The field of ``event_class`` (resolved for ``subtype``); fail closed on an unknown class
    or subtype, on a subtype for a class that has none, and on none for a class with only
    per-subtype fields."""
    try:
        declared = EVENT_FIELDS[event_class]
    except KeyError:
        raise ConfigurationError(
            f"event class {event_class!r} has no declared field to read its names from "
            f"(known: {sorted(EVENT_FIELDS)})"
        ) from None
    if subtype is None:
        if not declared.count:
            raise ConfigurationError(
                f"event class {event_class!r} needs a subtype (known: {sorted(declared.subtypes)})"
            )
        return declared
    chosen = declared.subtypes.get(subtype)
    if chosen is None:
        raise ConfigurationError(
            f"event class {event_class!r} has no subtype {subtype!r} "
            f"(known: {sorted(declared.subtypes) or 'none'})"
        )
    where = (chosen.field, chosen.value) if chosen.field and chosen.value else None
    return replace(
        declared,
        count=chosen.count or declared.count,
        date=chosen.date or declared.date,
        subtypes={},
        where=where,
    )


def read_events(
    reader: StoreReader,
    event_class: str,
    offset: int,
    decisions: Sequence[date],
    eligible_of: Callable[[date], frozenset[str]],
    subtype: str | None = None,
) -> EventSchedule:
    """The event names of ``event_class`` at each of ``decisions`` (ascending), restricted to
    the names ``eligible_of(D)`` gives. The eligible names are only looked up on a session
    where some name has the event; the UNKNOWN count is over them."""
    found = read_events_for(reader, event_class, offset, decisions, {"": eligible_of}, subtype)
    return found[""]


def read_events_for(
    reader: StoreReader,
    event_class: str,
    offset: int,
    decisions: Sequence[date],
    eligible_of: Mapping[str, Callable[[date], frozenset[str]]],
    subtype: str | None = None,
) -> dict[str, EventSchedule]:
    """``read_events`` for several eligible universes (one per key of ``eligible_of``) in one
    pass: the event fields are read once per decision session, not once per universe, and
    each universe keeps its own once-per-name dedupe. Same schedules as separate calls."""
    spec = event_field(event_class, subtype)
    target = spec.target(offset)
    names: dict[str, dict[date, frozenset[str]]] = {k: {} for k in eligible_of}
    unknown: dict[str, dict[date, Mapping[str, int]]] = {k: {} for k in eligible_of}
    last: dict[str, dict[str, date]] = {k: {} for k in eligible_of}  # name -> latest counted D
    for day in decisions:
        try:
            view, _ = fields_view(reader, spec.fields(), day, historical=True, held=HARNESS_ALL)
        except MissingDataError as error:
            raise EventDayMissingError(error, day) from error
        reads = {i: _read(view.get(i, spec.count), view.get(i, spec.date)) for i in view}
        if not any(count == target for count, _ in reads.values()):
            continue
        for key, eligible in eligible_of.items():
            reasons: Counter[str] = Counter()
            known: set[str] = set()
            for i in sorted(eligible(day)):
                count, when = reads.get(i, (None, None))
                verdict = _verdict(spec, count, when, target, day, _label(view, i, spec))
                if verdict == KNOWN:
                    known.add(i)
                elif verdict:
                    reasons[verdict] += 1
            seen = last[key]
            fresh = {
                i for i in known if i not in seen or sessions_to(seen[i], day) >= DEDUPE_SESSIONS
            }
            seen.update(dict.fromkeys(fresh, day))
            if reasons:
                unknown[key][day] = dict(reasons)
            if fresh:
                names[key][day] = frozenset(fresh)
    return {k: EventSchedule(names[k], unknown[k]) for k in eligible_of}


KNOWN = "known"  # ``_verdict``: the name has the event at D (else a reason, or "" for none)


def _label(view: Any, instrument: str, spec: EventField) -> object:
    """The subtype label field of ``instrument`` (None when the spec has none or it is null)."""
    return view.get(instrument, spec.where[0]) if spec.where else None


def _verdict(
    spec: EventField,
    count: int | None,
    when: date | None,
    target: int,
    day: date,
    label: object,
) -> str:
    """``KNOWN``, the UNKNOWN reason of a name with a row that cannot say, or "" (no event of
    this class and subtype: another count, another subtype)."""
    if count is None:
        return NO_EVENT_ROW
    if count != target:
        return ""
    if spec.where and label is None:
        return NO_EVENT_ROW
    if spec.where and label != spec.where[1]:
        return ""
    if not spec.announced_ahead and (when is None or when > day):
        return NOT_KNOWN_AT_D
    return KNOWN


def _read(count: object, when: object) -> tuple[int | None, date | None]:
    """The count field as an int and the date field as a date (None when not stored)."""
    number = int(count) if isinstance(count, (int, float)) and not isinstance(count, bool) else None
    return number, date.fromisoformat(when[:10]) if isinstance(when, str) else None
