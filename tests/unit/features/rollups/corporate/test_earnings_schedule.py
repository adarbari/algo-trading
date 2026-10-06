"""``earnings_schedule@v1``: SCHEDULED where ``earnings@v1`` has a next date on the session,
NOT_ANNOUNCED where it has only a last one, no row where it has none (ADR 0046)."""

from datetime import date

import pandas as pd

from algotrade.features.framework.runner import compute_one
from algotrade.features.rollups.corporate import earnings, earnings_schedule
from tests.helpers.rollup_store import store, write_earnings


def test_status_follows_the_earnings_row_of_the_session() -> None:
    writer, reader = store()
    write_earnings(
        writer,
        date(2026, 9, 1),
        [("EQ:A", date(2026, 9, 15), "pre_market"), ("EQ:C", date(2026, 10, 5), "after_hours")],
    )
    session = date(2026, 9, 21)  # A reported on 09-15, nothing after; C is still due
    frame = compute_one(reader, earnings_schedule.GROUP, session).frame
    assert frame is not None
    status = frame.set_index("instrument_id")["next_status"].to_dict()
    assert status == {"EQ:A": "NOT_ANNOUNCED", "EQ:C": "SCHEDULED"}
    dates = compute_one(reader, earnings.GROUP, session).frame
    assert dates is not None and set(dates["instrument_id"]) == set(status)  # same rows
    assert pd.isna(dates.set_index("instrument_id").loc["EQ:A", "next_earnings_date"])
    write_earnings(writer, date(2026, 9, 22), [("EQ:A", date(2026, 12, 1), "after_hours")])
    later = compute_one(reader, earnings_schedule.GROUP, date(2026, 9, 22)).frame
    assert later is not None  # the new snapshot covers 10-05 without C: cancelled, no row
    assert later.set_index("instrument_id")["next_status"].to_dict() == {"EQ:A": "SCHEDULED"}
    before = compute_one(reader, earnings_schedule.GROUP, session).frame  # point in time
    assert before is not None and before.equals(frame)


def test_the_next_report_features_read_it_as_their_status() -> None:
    nxt = earnings.GROUP.feature("next_earnings_date")
    assert nxt.status_field == "rollup.earnings_schedule@v1.next_status"
    assert nxt.explained_statuses == ("NOT_ANNOUNCED",)
    assert earnings_schedule.GROUP.feature("next_status").applies_to == "operating_company"
