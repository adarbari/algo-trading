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
"""

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.calendar import sessions_to
from algotrade.data import StoreReader
from algotrade.services.selection import fields_view

DEDUPE_SESSIONS = 40  # one report per name in this many sessions
NO_EVENT_ROW = "no_event_row"  # eligible at D, but the event field has no value for the name
NOT_KNOWN_AT_D = "event_not_known_at_decision"  # the field's event date is after D


@dataclass(frozen=True)
class EventField:
    """Where one event class is read: ``count`` (the field whose value says how far D is from
    the anchor, scaled by ``sign``), ``date`` (the event's date), and whether the event is
    announced ahead (its date may be after D; otherwise it must be on or before D)."""

    count: str
    date: str
    sign: int
    announced_ahead: bool

    def target(self, offset: int) -> int:
        return self.sign * (offset - 1)


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
}


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


def event_field(event_class: str) -> EventField:
    try:
        return EVENT_FIELDS[event_class]
    except KeyError:
        raise ConfigurationError(
            f"event class {event_class!r} has no declared field to read its names from "
            f"(known: {sorted(EVENT_FIELDS)})"
        ) from None


def read_events(
    reader: StoreReader,
    event_class: str,
    offset: int,
    decisions: Sequence[date],
    eligible_of: Callable[[date], frozenset[str]],
) -> EventSchedule:
    """The event names of ``event_class`` at each of ``decisions`` (ascending), restricted to
    the names ``eligible_of(D)`` gives. The eligible names are only looked up on a session
    where some name has the event; the UNKNOWN count is over them."""
    spec = event_field(event_class)
    target = spec.target(offset)
    names: dict[date, frozenset[str]] = {}
    unknown: dict[date, Mapping[str, int]] = {}
    last: dict[str, date] = {}  # name -> the decision session its latest event counted at
    for day in decisions:
        view, _ = fields_view(reader, (spec.count, spec.date), day)
        reads = {i: _read(view.get(i, spec.count), view.get(i, spec.date)) for i in view}
        if not any(count == target for count, _ in reads.values()):
            continue
        reasons: Counter[str] = Counter()
        known: set[str] = set()
        for i in sorted(eligible_of(day)):
            count, when = reads.get(i, (None, None))
            if count is None:
                reasons[NO_EVENT_ROW] += 1
            elif count == target:
                if not spec.announced_ahead and (when is None or when > day):
                    reasons[NOT_KNOWN_AT_D] += 1
                else:
                    known.add(i)
        fresh = {i for i in known if i not in last or sessions_to(last[i], day) >= DEDUPE_SESSIONS}
        last.update(dict.fromkeys(fresh, day))
        if reasons:
            unknown[day] = dict(reasons)
        if fresh:
            names[day] = frozenset(fresh)
    return EventSchedule(names, unknown)


def _read(count: object, when: object) -> tuple[int | None, date | None]:
    """The count field as an int and the date field as a date (None when not stored)."""
    number = int(count) if isinstance(count, (int, float)) and not isinstance(count, bool) else None
    return number, date.fromisoformat(when[:10]) if isinstance(when, str) else None
