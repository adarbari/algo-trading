"""``reverse_splits@v1``: the latest reverse split per instrument, the stored ratio convention
(new shares per old: a 4-for-1 forward split is 4, a 1-for-10 reverse split 0.1), a forward
split is no event, a split with an ex-date after the session is never read, and an instrument
with none has no row."""

from datetime import date

import pandas as pd

from algotrade.features.rollups.events import reverse_splits as rs
from algotrade_sources.vendors.massive.corporate_actions import parse_splits

SESSION = date(2026, 10, 9)  # a Friday


def _inputs(rows: list[tuple[str, date, float]] | None) -> dict[str, pd.DataFrame | None]:
    if rows is None:
        return {rs.EVENTS: None}
    return {rs.EVENTS: pd.DataFrame(rows, columns=["instrument_id", "event_date", "ratio"])}


def test_the_stored_ratio_convention_a_reverse_split_is_below_one() -> None:
    out = rs.compute(
        _inputs(
            [
                ("EQ:FWD", date(2026, 10, 8), 4.0),  # a 4-for-1 forward split, stored as 4
                ("EQ:REV", date(2026, 10, 8), 0.1),  # a 1-for-10 reverse split
                ("EQ:ONE", date(2026, 10, 8), 1.0),  # no change
                ("EQ:ODD", date(2026, 10, 8), 0.0),  # not a ratio
            ]
        ),
        SESSION,
        None,
    ).set_index("instrument_id")
    assert list(out.index) == ["EQ:REV"]
    assert out.at["EQ:REV", "reverse_split_ratio"] == 0.1


def test_the_latest_split_its_sessions_since_and_the_count() -> None:
    out = rs.compute(
        _inputs(
            [
                ("EQ:A", date(2026, 1, 5), 0.5),
                ("EQ:A", date(2026, 10, 7), 0.2),
                ("EQ:A", date(2026, 10, 1), 3.0),  # a forward split between: not counted
                ("EQ:B", date(2026, 10, 9), 0.25),
            ]
        ),
        SESSION,
        None,
    ).set_index("instrument_id")
    assert out.at["EQ:A", "last_reverse_split_date"] == date(2026, 10, 7)
    assert out.at["EQ:A", "sessions_since_reverse_split"] == 2
    assert out.at["EQ:A", "reverse_split_ratio"] == 0.2
    assert out.at["EQ:A", "reverse_splits_1y"] == 2
    assert out.at["EQ:B", "sessions_since_reverse_split"] == 0  # the ex-date is the session
    assert out.at["EQ:B", "reverse_splits_1y"] == 1


def test_a_split_with_an_ex_date_after_the_session_is_never_read() -> None:
    out = rs.compute(
        _inputs([("EQ:A", date(2026, 10, 12), 0.1), ("EQ:B", date(2026, 10, 8), 0.1)]),
        SESSION,
        None,
    )
    assert list(out["instrument_id"]) == ["EQ:B"]


def test_no_splits_stored_has_no_rows() -> None:
    assert rs.compute(_inputs(None), SESSION, None).empty
    assert rs.compute(_inputs([]), SESSION, None).empty


def test_the_massive_normaliser_stores_a_one_for_ten_reverse_split_as_point_one() -> None:
    rows = parse_splits(
        [
            {"execution_date": "2026-10-08", "ticker": "AAA", "split_from": 10, "split_to": 1},
            {"execution_date": "2026-10-08", "ticker": "BBB", "split_from": 1, "split_to": 4},
        ]
    ).set_index("symbol")
    assert rows.at["AAA", "ratio"] == 0.1  # reverse: below 1, the rollup reads it
    assert rows.at["BBB", "ratio"] == 4.0  # forward 4-for-1: stored as 4
