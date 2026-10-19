"""``etf_launches@v1``: the sessions since a specialised ETF's launch, the category label the
schedule filters on, the launch source, a launch after the session is never read, and an
instrument with none has no row."""

from datetime import date

import pandas as pd

from algotrade.features.rollups.events import etf_launches as el

SESSION = date(2026, 10, 9)  # a Friday


def _inputs(rows: list[tuple[str, date, str, str]] | None) -> dict[str, pd.DataFrame | None]:
    if rows is None:
        return {el.LAUNCHES: None}
    cols = ["instrument_id", "event_date", "etf_category", "etf_theme"]
    return {el.LAUNCHES: pd.DataFrame(rows, columns=cols)}


def test_sessions_since_the_launch_category_theme_and_source() -> None:
    out = el.compute(
        _inputs(
            [
                ("EQ:A", date(2026, 10, 7), "thematic", "technology"),
                ("EQ:B", date(2026, 10, 9), "sector", "energy"),
            ]
        ),
        SESSION,
        None,
    ).set_index("instrument_id")
    assert out.at["EQ:A", "sessions_since_etf_launch"] == 2
    assert out.at["EQ:A", "last_etf_launch_date"] == date(2026, 10, 7)
    assert out.at["EQ:A", "etf_category"] == "thematic"
    assert out.at["EQ:B", "sessions_since_etf_launch"] == 0  # the launch day is the session
    assert out.at["EQ:B", "etf_theme"] == "energy"
    assert set(out["launch_date_source"]) == {"tiingo_listing"}


def test_a_launch_after_the_session_is_never_read() -> None:
    out = el.compute(
        _inputs(
            [
                ("EQ:LATE", date(2026, 10, 12), "thematic", "health"),
                ("EQ:OK", date(2026, 10, 8), "thematic", "health"),
            ]
        ),
        SESSION,
        None,
    )
    assert list(out["instrument_id"]) == ["EQ:OK"]


def test_no_launches_stored_has_no_rows() -> None:
    assert el.compute(_inputs(None), SESSION, None).empty
    assert el.compute(_inputs([]), SESSION, None).empty


def test_the_constants_match_the_data_read() -> None:
    from algotrade.data.listings import etf_launches as read  # noqa: PLC0415

    assert (el.LAUNCH_SOURCE, el.SPECIALISED) == (read.LAUNCH_SOURCE, read.SPECIALISED)
