"""Event schedules of an edge document (ADR 0053 amendment 2026-10-08: ED4 item 7, ADR 0050):
the event classes an
``on_event:<class>[:<subtype>]`` schedule may trigger on with their anchor sessions, the subtypes
a class may be split by, and the parsing and fail-closed validity check of such a schedule.
Split from ``document.py`` (at its line cap); ``document`` re-exports every name."""

from collections.abc import Mapping

from algotrade.config.site.fields import Table
from algotrade.core.model.errors import ConfigurationError

ON_EVENT = "on_event:"
# The event classes a schedule may trigger on, and its ANCHOR session. The entry session is
# S = anchor + start_offset_sessions, the decision session D = S - 1, the outcome's horizons
# count from S's close, and the event must be known by D (``known_from <= D``, ADR 0050): the
# harness skips an event that is not, never reads it early (``cross_section/events.py`` names
# the stored field each class is read from).
EVENT_CLASSES: Mapping[str, str] = {
    "earnings_reaction": "a reported result's two-session reaction (earnings_reaction@v2); "
    "anchor: the reaction's last session, E+1 (E: the report date)",
    "earnings_expected": "a next report expected, scheduled or from the year-ago report "
    "(earnings_expected@v1); anchor: the expected report date's session",
    "index_change": "an S&P 500 membership change (index_changes@v1); anchor: the session it is "
    "first stored (never the announcement)",
    "filing_8k": "an 8-K carrying one Item (filing_events@v1); needs the item as its subtype; "
    "anchor: the session the filing became known, the first whose close is after SEC accepted it",
    "nt_late_filing": "an NT 10-K or NT 10-Q late-filing notice (filing_events@v1); anchor: the "
    "session it became known",
    "tender_offer": "an SC TO-I issuer or SC TO-T third-party tender offer (filing_events@v1); "
    "anchor: the session it became known",
    "earnings_date_shift": "a next report date a week or more away from last year's "
    "(earnings_date_shift@v1); anchor: the session the shifted date was first stored",
    "ipo_lockup": "an IPO lock-up expiry, announced in the prospectus (ipo_lockups@v1; ADR 0075); "
    "anchor: the expiry session; may be entered ahead of it",
    "reverse_split": "a reverse split (reverse_splits@v1; ADR 0075); anchor: the ex-date; "
    "funds are left out by the edge's universe",
    "etf_launch": "the launch of a specialised ETF, a thematic or sector fund (etf_launches@v1; "
    "ADR 0076); anchor: its first listing day (Tiingo), known on that day",
}
# A class may be split by a subtype: ``on_event:<class>:<subtype>``. The subtype is one of the
# class's own values (fail closed on any other, and on a subtype for a class that has none); the
# base of an edge on it is the same class and subtype (``base = "event"``) or the universe. A
# class in ``SUBTYPE_REQUIRED`` has no field of its own to read without one. The stored field of
# each is declared in ``cross_section/events.py`` (kept equal by a fitness test).
EVENT_SUBTYPES: Mapping[str, Mapping[str, str]] = {
    "index_change": {
        "addition": "joined the S&P 500 (sp500_added)",
        "deletion": "left the S&P 500 (sp500_removed)",
    },
    "filing_8k": {
        "1.02": "Item 1.02, termination of a material agreement",
        "2.05": "Item 2.05, exit or disposal costs (a restructuring)",
        "3.01": "Item 3.01, a delisting or listing-standard notice",
        "4.01": "Item 4.01, a change of the auditor",
        "4.02": "Item 4.02, non-reliance on previously issued financial statements",
        "5.02": "Item 5.02, the departure or appointment of a director or an officer",
    },
    "earnings_date_shift": {
        "later": "the next report date is a week or more later than last year's",
        "earlier": "the next report date is a week or more earlier than last year's",
    },
    "etf_launch": {
        "thematic": "a thematic ETF: a story tying several industries (etf_category thematic)",
        "sector": "a sector ETF: one industry (etf_category sector)",
    },
    "ipo_lockup": {
        "standard": "the prospectus gives one lock-up expiry date",
        "early_release": "the prospectus lets part of the lock-up end early (on earnings or a "
        "price condition)",
    },
}
SUBTYPE_REQUIRED = ("filing_8k",)
# ex_dividend and macro_release have no field to read yet (EB H4 follow-ups).


def event_class(schedule: str) -> str | None:
    """The event class of an ``on_event:<class>[:<subtype>]`` schedule, else None."""
    if not schedule.startswith(ON_EVENT):
        return None
    return schedule.removeprefix(ON_EVENT).partition(":")[0]


def event_subtype(schedule: str) -> str | None:
    """The subtype of an ``on_event:<class>:<subtype>`` schedule, else None."""
    if not schedule.startswith(ON_EVENT):
        return None
    return schedule.removeprefix(ON_EVENT).partition(":")[2] or None


def event_schedule_ok(t: Table, schedule: str) -> bool:
    """Whether an ``on_event:`` schedule names a known class and, fail closed, one of its
    subtypes (required for ``SUBTYPE_REQUIRED``, refused for a class that has none)."""
    cls, sub = event_class(schedule), event_subtype(schedule)
    if cls is None or cls not in EVENT_CLASSES:
        return False
    allowed = EVENT_SUBTYPES.get(cls, {})
    if sub is None:
        if cls in SUBTYPE_REQUIRED:
            raise ConfigurationError(
                f"{t.where} schedule: {schedule!r} needs a subtype, one of {sorted(allowed)}"
            )
        return True
    if sub not in allowed:
        raise ConfigurationError(
            f"{t.where} schedule: {sub!r} is not a subtype of {cls!r} "
            f"(known: {sorted(allowed) or 'none'})"
        )
    return True
