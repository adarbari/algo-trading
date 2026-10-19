"""``read_events``: the event names at a decision session D come from a declared field read at
D (never an event known only after D), exactly the names whose count field reads the offset's
value, deduplicated by (name, quarter), with a name that has no value excluded with a reason."""

from datetime import date
from typing import Any

import pytest

from algotrade.config.edges.document import (
    ANNOUNCED_AHEAD,
    EVENT_CLASSES,
    EVENT_SUBTYPES,
    SUBTYPE_REQUIRED,
)
from algotrade.core.model.errors import ConfigurationError
from algotrade.features.registry import GROUPS
from algotrade.services.evaluation.cross_section import events
from algotrade.services.evaluation.cross_section.events import (
    EVENT_FIELDS,
    NO_EVENT_ROW,
    NOT_KNOWN_AT_D,
    EventField,
    event_field,
    read_events,
    read_events_for,
)
from tests.unit.services.evaluation.cross_section.conftest import DAYS, IDS, build_world

ALL = frozenset(IDS)


def test_the_count_field_and_offset_decide_which_names_have_the_event() -> None:
    assert EVENT_FIELDS["earnings_reaction"].target(1) == 0  # offset - 1: D = E+1 itself
    assert EVENT_FIELDS["earnings_reaction"].target(3) == 2
    assert EVENT_FIELDS["earnings_expected"].target(-5) == 6  # sessions_to_expected = 1 - offset
    assert EVENT_FIELDS["earnings_expected"].target(0) == 1  # S = A, D = A - 1
    with pytest.raises(ConfigurationError, match="no declared field"):
        event_field("ex_dividend")  # removed class: no field


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


def test_one_pass_over_several_universes_equals_separate_reads_and_reads_the_fields_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    w = build_world()
    w.write_reactions(DAYS[1], {IDS[i]: 0 for i in (1, 2, 12)})
    w.write_reactions(DAYS[2], {IDS[i]: 0 for i in (2, 3)})  # N02 again: deduplicated per name
    low = frozenset(IDS[:10])
    universes = {"all": lambda _: ALL, "low": lambda _: low}
    separate = {
        k: read_events(w.reader, "earnings_reaction", 1, DAYS[:4], f) for k, f in universes.items()
    }
    reads: list[date] = []
    real = events.fields_view

    def counting(reader: Any, fields: Any, day: date, *a: Any, **k: Any) -> Any:
        reads.append(day)
        return real(reader, fields, day, *a, **k)

    monkeypatch.setattr(events, "fields_view", counting)
    together = read_events_for(w.reader, "earnings_reaction", 1, DAYS[:4], universes)
    assert together == separate
    assert reads == list(DAYS[:4])  # each decision session read once, whatever the universes


def test_every_declared_event_class_has_a_field_to_read() -> None:
    """B2 (EB H0): a class a document may name (``EVENT_CLASSES``) the harness cannot read
    validated, then failed at run time (ex_dividend, index_change, macro_release had no
    field). ex_dividend and macro_release are removed until EB H4 builds their fields."""
    assert set(EVENT_CLASSES) == set(EVENT_FIELDS)


def test_every_declared_subtype_has_a_field_and_the_other_way_round() -> None:
    """EB H4: the class list and its subtypes are a contract (ADR 0050 / 0053 amendment): the
    schedule a document may name (``EVENT_SUBTYPES``) is exactly what the harness reads."""
    assert {c: set(v) for c, v in EVENT_SUBTYPES.items()} == {
        c: set(f.subtypes) for c, f in EVENT_FIELDS.items() if f.subtypes
    }
    assert set(SUBTYPE_REQUIRED) == {c for c, f in EVENT_FIELDS.items() if not f.count}
    for cls in EVENT_FIELDS:
        for sub in [None] if cls not in EVENT_SUBTYPES else list(EVENT_SUBTYPES[cls]):
            if cls in SUBTYPE_REQUIRED and sub is None:
                continue
            assert event_field(cls, sub).count  # resolves to a field


def test_every_event_field_is_a_catalogue_feature() -> None:
    """A field the harness reads that no group stores would fail at run time, not at load."""
    stored = {f"rollup.{g.key}.{f.name}" for g in GROUPS.values() for f in g.features}
    for cls, declared in EVENT_FIELDS.items():
        subs = [None, *declared.subtypes] if declared.count else list(declared.subtypes)
        for sub in subs:
            fields = event_field(cls, sub).fields()
            assert set(fields) <= stored, (cls, sub, set(fields) - stored)


def test_subtypes_fail_closed() -> None:
    with pytest.raises(ConfigurationError, match="no subtype 'sideways'"):
        event_field("index_change", "sideways")
    with pytest.raises(ConfigurationError, match="no subtype 'x'"):
        event_field("nt_late_filing", "x")  # a class with none
    with pytest.raises(ConfigurationError, match="needs a subtype"):
        event_field("filing_8k")
    assert event_field("index_change").where is None  # no subtype: every change
    assert event_field("index_change", "deletion").where == (
        "rollup.index_changes@v1.last_index_change",
        "sp500_removed",
    )
    assert isinstance(event_field("filing_8k", "4.02"), EventField)


INDEX = "rollups/instrument/index_changes@v1"


def test_a_subtype_with_a_label_keeps_only_names_whose_label_matches() -> None:
    """``index_change:deletion`` is the names whose latest change reads ``sp500_removed``: a
    name added the same day is no event of it (and not UNKNOWN), a null label is UNKNOWN."""
    w = build_world()
    d = DAYS[1]
    rows = [
        {"instrument_id": IDS[0], "sessions_since_index_change": 0, "last_index_change_date": d,
         "last_index_change": "sp500_removed"},
        {"instrument_id": IDS[1], "sessions_since_index_change": 0, "last_index_change_date": d,
         "last_index_change": "sp500_added"},
        {"instrument_id": IDS[2], "sessions_since_index_change": 0, "last_index_change_date": d,
         "last_index_change": None},
        {"instrument_id": IDS[3], "sessions_since_index_change": 4, "last_index_change_date": d,
         "last_index_change": "sp500_removed"},
    ]  # fmt: skip
    w.write_rollup(INDEX, d, rows)
    every = read_events(w.reader, "index_change", 1, [d], lambda _: ALL)
    deleted = read_events(w.reader, "index_change", 1, [d], lambda _: ALL, "deletion")
    added = read_events(w.reader, "index_change", 1, [d], lambda _: ALL, "addition")
    assert every.names == {d: frozenset(IDS[:3])}
    assert deleted.names == {d: frozenset({IDS[0]})}
    assert added.names == {d: frozenset({IDS[1]})}
    assert deleted.unknown[d] == {NO_EVENT_ROW: 17}  # 16 names with no row, N02 with a null label


FILINGS = "rollups/instrument/filing_events@v1"


def test_an_8k_item_subtype_reads_its_own_count_and_date_fields() -> None:
    w = build_world()
    d = DAYS[1]
    w.write_rollup(
        FILINGS,
        d,
        [
            {"instrument_id": IDS[0], "sessions_since_8k_4_02": 0, "last_8k_4_02_date": d,
             "sessions_since_8k_5_02": 3, "last_8k_5_02_date": d},
            {"instrument_id": IDS[1], "sessions_since_8k_4_02": 1, "last_8k_4_02_date": d,
             "sessions_since_8k_5_02": 0, "last_8k_5_02_date": d},
        ],
    )  # fmt: skip
    got = read_events(w.reader, "filing_8k", 1, [d], lambda _: ALL, "4.02")
    other = read_events(w.reader, "filing_8k", 1, [d], lambda _: ALL, "5.02")
    assert got.names == {d: frozenset({IDS[0]})}
    assert other.names == {d: frozenset({IDS[1]})}


LOCKUPS = "rollups/instrument/ipo_lockups@v1"
SPLITS = "rollups/instrument/reverse_splits@v1"


def test_a_lockup_announced_ahead_is_known_before_its_expiry_and_split_by_its_terms() -> None:
    """ADR 0075: ``ipo_lockup`` is read at ``sessions_to_lockup_expiry == 1 - offset`` (offset 0:
    the entry is the expiry session, D the one before), its date is after D by design, and the
    subtype is the release terms; a null terms value is UNKNOWN, another value no event."""
    w = build_world()
    d, expiry = DAYS[1], DAYS[2]
    rows = [
        {"instrument_id": IDS[0], "sessions_to_lockup_expiry": 1, "lockup_expiry_date": expiry,
         "lockup_release_terms": "standard"},
        {"instrument_id": IDS[1], "sessions_to_lockup_expiry": 1, "lockup_expiry_date": expiry,
         "lockup_release_terms": "early_release"},
        {"instrument_id": IDS[2], "sessions_to_lockup_expiry": 1, "lockup_expiry_date": expiry,
         "lockup_release_terms": None},
        {"instrument_id": IDS[3], "sessions_to_lockup_expiry": 9, "lockup_expiry_date": expiry,
         "lockup_release_terms": "standard"},
    ]  # fmt: skip
    w.write_rollup(LOCKUPS, d, rows)
    assert EVENT_FIELDS["ipo_lockup"].sign == -1 and EVENT_FIELDS["ipo_lockup"].announced_ahead
    base = read_events(w.reader, "ipo_lockup", 0, [d], lambda _: ALL)
    standard = read_events(w.reader, "ipo_lockup", 0, [d], lambda _: ALL, "standard")
    early = read_events(w.reader, "ipo_lockup", 0, [d], lambda _: ALL, "early_release")
    assert base.names == {d: frozenset(IDS[:3])}  # the expiry is after D: still known at D
    assert standard.names == {d: frozenset({IDS[0]})}
    assert early.names == {d: frozenset({IDS[1]})}
    assert standard.unknown[d] == {NO_EVENT_ROW: 17}  # 16 names with no row, N02's null terms
    # Three sessions after the expiry the count reads -3: entry offset 4 (D = S - 1 = expiry + 3).
    w.write_rollup(LOCKUPS, DAYS[5], [{"instrument_id": IDS[0], "sessions_to_lockup_expiry": -3,
                                       "lockup_expiry_date": expiry,
                                       "lockup_release_terms": "standard"}])  # fmt: skip
    after = read_events(w.reader, "ipo_lockup", 4, [DAYS[5]], lambda _: ALL)
    assert after.names == {DAYS[5]: frozenset({IDS[0]})}


def test_a_reverse_split_is_an_event_on_its_ex_date_and_never_before_it() -> None:
    w = build_world()
    d, nxt = DAYS[1], DAYS[2]
    w.write_rollup(
        SPLITS,
        d,
        [
            {"instrument_id": IDS[0], "sessions_since_reverse_split": 0,
             "last_reverse_split_date": d},
            {"instrument_id": IDS[1], "sessions_since_reverse_split": 0,
             "last_reverse_split_date": nxt},  # an ex-date after D: not known at D
        ],
    )  # fmt: skip
    found = read_events(w.reader, "reverse_split", 1, [d], lambda _: ALL)
    assert found.names == {d: frozenset({IDS[0]})}
    assert found.unknown[d][NOT_KNOWN_AT_D] == 1
    assert not EVENT_FIELDS["reverse_split"].announced_ahead
    with pytest.raises(ConfigurationError, match="has no subtype 'x'"):
        event_field("reverse_split", "x")  # no subtypes


def test_an_etf_launch_is_an_event_on_its_listing_day_split_by_category() -> None:
    """ADR 0076: ``etf_launch`` is read at ``sessions_since_etf_launch == 0`` for entry offset 1
    (D is the launch day); a launch dated after D is not known at D; the subtype is the category."""
    w = build_world()
    d, nxt = DAYS[1], DAYS[2]
    w.write_rollup(
        "rollups/instrument/etf_launches@v1",
        d,
        [
            {"instrument_id": IDS[0], "sessions_since_etf_launch": 0, "last_etf_launch_date": d,
             "etf_category": "thematic"},
            {"instrument_id": IDS[1], "sessions_since_etf_launch": 0, "last_etf_launch_date": d,
             "etf_category": "sector"},
            {"instrument_id": IDS[2], "sessions_since_etf_launch": 0,
             "last_etf_launch_date": nxt, "etf_category": "thematic"},  # after D: not known
        ],
    )  # fmt: skip
    base = read_events(w.reader, "etf_launch", 1, [d], lambda _: ALL)
    thematic = read_events(w.reader, "etf_launch", 1, [d], lambda _: ALL, "thematic")
    sector = read_events(w.reader, "etf_launch", 1, [d], lambda _: ALL, "sector")
    assert base.names == {d: frozenset(IDS[:2])}
    assert thematic.names == {d: frozenset({IDS[0]})}
    assert sector.names == {d: frozenset({IDS[1]})}
    assert base.unknown[d][NOT_KNOWN_AT_D] == 1
    assert not EVENT_FIELDS["etf_launch"].announced_ahead


def test_the_document_and_the_harness_agree_on_which_classes_are_announced_ahead() -> None:
    """The two lists drifted once (``ipo_lockup`` was read ahead by the harness but refused a
    negative offset by the document): kept equal here, as config cannot import services."""
    assert set(ANNOUNCED_AHEAD) == {k for k, v in EVENT_FIELDS.items() if v.announced_ahead}
