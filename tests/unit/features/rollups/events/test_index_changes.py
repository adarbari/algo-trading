"""``index_changes@v1``: the latest S&P 500 membership change per instrument and the sessions
since it; an instrument with no change in the window has no row (UNKNOWN), a later change
replaces an earlier one, and a change after the session is never read."""

from datetime import date

import pandas as pd

from algotrade.features.rollups.events import index_changes as ic

SESSION = date(2026, 10, 9)  # a Friday


def _inputs(rows: list[tuple[str, date, str]] | None) -> dict[str, pd.DataFrame | None]:
    if rows is None:
        return {ic.EVENTS: None}
    frame = pd.DataFrame(rows, columns=["instrument_id", "event_date", "change"])
    return {ic.EVENTS: frame}


def test_the_latest_change_and_the_sessions_since_it() -> None:
    out = ic.compute(
        _inputs(
            [
                ("EQ:A", date(2026, 10, 1), ic.ADDED),
                ("EQ:A", date(2026, 10, 8), ic.REMOVED),
                ("EQ:B", date(2026, 10, 9), ic.ADDED),
                ("EQ:C", date(2026, 10, 12), ic.ADDED),  # after the session: never read
            ]
        ),
        SESSION,
        None,
    ).set_index("instrument_id")
    assert list(out.index) == ["EQ:A", "EQ:B"]
    assert out.at["EQ:A", "last_index_change"] == ic.REMOVED
    assert out.at["EQ:A", "sessions_since_index_change"] == 1
    assert out.at["EQ:B", "sessions_since_index_change"] == 0
    assert out.at["EQ:B", "last_index_change_date"] == SESSION


def test_no_change_stored_is_no_row() -> None:
    assert ic.compute(_inputs(None), SESSION, None).empty
    assert ic.compute(_inputs([]), SESSION, None).empty
