"""``filing_events@v1``: per instrument the sessions since each kind of event filing became known
(an 8-K item, a late-filing notice, a tender offer), counted from the session the filing is known
from; an amendment is no event, a filing known after the session is never read, a filing with
several items counts for each, and an instrument with none has no row."""

from datetime import date

import pandas as pd

from algotrade.config.edges.document import EVENT_SUBTYPES
from algotrade.features.rollups.events import filing_events as fe

SESSION = date(2026, 10, 9)  # a Friday


def _inputs(rows: list[tuple[str, str, str, date]] | None) -> dict[str, pd.DataFrame | None]:
    if rows is None:
        return {fe.EVENTS: None}
    frame = pd.DataFrame(rows, columns=["instrument_id", "form", "items", "event_date"])
    return {fe.EVENTS: frame}


def test_each_item_counts_from_the_session_its_latest_filing_became_known() -> None:
    out = fe.compute(
        _inputs(
            [
                ("EQ:A", "8-K", "4.02,9.01", date(2026, 10, 6)),
                ("EQ:A", "8-K", "5.02", date(2026, 10, 8)),
                ("EQ:A", "8-K", "4.02", date(2026, 10, 2)),  # an earlier 4.02: the later one wins
                ("EQ:A", "NT 10-Q", "", date(2026, 10, 9)),
                ("EQ:B", "SC TO-T", "", date(2026, 10, 7)),
                ("EQ:B", "SC TO-I", "", date(2026, 10, 1)),
            ]
        ),
        SESSION,
        None,
    ).set_index("instrument_id")
    assert list(out.index) == ["EQ:A", "EQ:B"]
    assert out.at["EQ:A", "sessions_since_8k_4_02"] == 3
    assert out.at["EQ:A", "last_8k_4_02_date"] == date(2026, 10, 6)
    assert out.at["EQ:A", "sessions_since_8k_5_02"] == 1  # the 5.02 does not move the 4.02
    assert out.at["EQ:A", "sessions_since_late_filing"] == 0
    assert out.at["EQ:B", "sessions_since_tender_offer"] == 2
    assert pd.isna(out.at["EQ:B", "sessions_since_8k_4_02"])
    assert pd.isna(out.at["EQ:A", "sessions_since_tender_offer"])


def test_an_amendment_a_later_filing_and_an_untracked_item_are_no_event() -> None:
    out = fe.compute(
        _inputs(
            [
                ("EQ:A", "8-K/A", "4.02", date(2026, 10, 8)),  # an amendment
                ("EQ:B", "8-K", "4.02", date(2026, 10, 12)),  # known only on Monday
                ("EQ:C", "8-K", "2.02,9.01", date(2026, 10, 8)),  # results: not a tracked item
            ]
        ),
        SESSION,
        None,
    )
    assert out.empty


def test_nothing_stored_is_no_row() -> None:
    assert fe.compute(_inputs(None), SESSION, None).empty
    assert fe.compute(_inputs([]), SESSION, None).empty


def test_the_items_are_the_ones_the_class_list_names() -> None:
    assert set(fe.ITEMS) == set(EVENT_SUBTYPES["filing_8k"])
