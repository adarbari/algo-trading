"""``read_events``: the event names at a decision session D come from a declared field read at
D (never an event known only after D), exactly the names whose count field reads the offset's
value, deduplicated by (name, quarter), with a name that has no value excluded with a reason."""

from datetime import date

import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.services.evaluation.cross_section.events import (
    EVENT_FIELDS,
    NO_EVENT_ROW,
    NOT_KNOWN_AT_D,
    event_field,
    read_events,
)
from tests.unit.services.evaluation.cross_section.conftest import DAYS, IDS, build_world

ALL = frozenset(IDS)


def test_the_count_field_and_offset_decide_which_names_have_the_event() -> None:
    assert EVENT_FIELDS["earnings_reaction"].target(1) == 0  # offset - 1: D = E+1 itself
    assert EVENT_FIELDS["earnings_reaction"].target(3) == 2
    assert EVENT_FIELDS["earnings_expected"].target(-5) == 6  # sessions_to_expected = 1 - offset
    assert EVENT_FIELDS["earnings_expected"].target(0) == 1  # S = A, D = A - 1
    with pytest.raises(ConfigurationError, match="no declared field"):
        event_field("ex_dividend")


def test_only_names_at_the_declared_count_have_the_event_and_the_rest_are_excluded_by_reason() -> (
    None
):
    w = build_world()
    d = DAYS[1]
    w.write_reactions(d, {IDS[0]: 0, IDS[1]: 1, IDS[2]: 0, IDS[3]: None})
    found = read_events(w.reader, "earnings_reaction", 1, [d], lambda _: ALL)
    assert found.names == {d: frozenset({IDS[0], IDS[2]})}
    # N01 has a row (a count, just not the offset's): not an event, not unknown. N03 has a null
    # count and the other 16 names no row at all: UNKNOWN, never read as "no event".
    assert found.unknown == {d: {NO_EVENT_ROW: 17}}
    assert read_events(w.reader, "earnings_reaction", 2, [d], lambda _: ALL).names == {
        d: frozenset({IDS[1]})
    }


def test_a_session_where_no_name_has_the_event_is_skipped_without_the_eligible_names() -> None:
    w = build_world()
    w.write_reactions(DAYS[1], {IDS[0]: 5})

    def never(_: date) -> frozenset[str]:
        raise AssertionError("the eligible names are only needed on an event session")

    assert read_events(w.reader, "earnings_reaction", 1, DAYS[:3], never).names == {}


def test_an_event_known_only_after_the_decision_session_is_absent() -> None:
    w = build_world()
    d, nxt = DAYS[1], DAYS[2]
    # At D, N00's reaction is dated D + 1: a report known only from the next session.
    w.write_reactions(d, {IDS[0]: 0, IDS[1]: 0}, ended={IDS[0]: nxt, IDS[1]: d})
    w.write_reactions(nxt, {IDS[0]: 0}, ended=nxt)
    found = read_events(w.reader, "earnings_reaction", 1, [d, nxt], lambda _: ALL)
    assert found.names[d] == frozenset({IDS[1]})  # N00's event has known_from D + 1: not at D
    assert found.unknown[d][NOT_KNOWN_AT_D] == 1
    assert IDS[0] in found.names[nxt]  # and it is an event once its session is the decision
    # An event announced ahead has a date after D by design: only the reaction class checks it.
    assert EVENT_FIELDS["earnings_expected"].announced_ahead


def test_an_event_is_counted_once_per_name_within_forty_sessions() -> None:
    w = build_world()
    first, again, far = date(2026, 9, 2), date(2026, 9, 3), date(2026, 12, 1)
    for day in (first, again, far):
        w.write_reactions(day, {IDS[0]: 0})  # N00 matches on three sessions
    found = read_events(w.reader, "earnings_reaction", 1, [first, again, far], lambda _: ALL)
    # The second match is the same report and drops; the one 60 sessions on is a new event.
    assert found.names == {first: frozenset({IDS[0]}), far: frozenset({IDS[0]})}
    assert found.unknown_total() == {NO_EVENT_ROW: 3 * 19}


def test_a_report_date_that_moves_across_a_quarter_end_is_one_event() -> None:
    w = build_world()
    prior_year, scheduled = date(2026, 9, 29), date(2026, 10, 2)  # Q3 and Q4, three sessions apart
    for day in (prior_year, scheduled):
        w.write_reactions(day, {IDS[0]: 0}, ended=day)
    found = read_events(w.reader, "earnings_reaction", 1, [prior_year, scheduled], lambda _: ALL)
    assert found.names == {prior_year: frozenset({IDS[0]})}


def test_only_the_eligible_names_are_events() -> None:
    w = build_world()
    d = DAYS[1]
    w.write_reactions(d, {IDS[0]: 0, IDS[1]: 0})
    found = read_events(w.reader, "earnings_reaction", 1, [d], lambda _: frozenset({IDS[1]}))
    assert found.names == {d: frozenset({IDS[1]})}
