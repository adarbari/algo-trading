"""The pure row logic of ``events/ipo_lockup`` (edge build D8): ``lockup_days`` / ``lockup_expiry``
from the extracted facts (a term in days or months, no date, no term), the hits of a search frame
and the comparison of a fresh row with a stored one."""

from datetime import date

import pandas as pd

from algotrade_ingestion.tasks.events.lockup_rows import (
    COLUMNS,
    VALUES,
    Hit,
    as_frame,
    hits_of,
    lockup_fields,
    same_values,
)
from algotrade_sources.framework.series import HIT_COLUMNS


def facts(**kw: object) -> dict[str, object]:
    base: dict[str, object] = {
        "extraction": "EXTRACTED", "lockup_n": 180, "lockup_unit": "days",
        "prospectus_date": date(2026, 6, 12), "reason": None,
    }  # fmt: skip
    return base | kw


def test_a_day_term_ends_n_days_after_the_prospectus_and_expires_the_next_session() -> None:
    assert lockup_fields(facts()) == {
        "lockup_days": 180, "lockup_expiry": date(2026, 12, 10), "reason": None,
    }  # fmt: skip


def test_a_month_term_is_counted_in_calendar_months_from_the_prospectus() -> None:
    got = lockup_fields(facts(lockup_n=6, lockup_unit="months", prospectus_date=date(2025, 8, 31)))
    assert got["lockup_days"] == 181 and got["lockup_expiry"] == date(2026, 3, 2)


def test_no_date_keeps_a_day_term_but_has_no_expiry_and_a_month_term_has_neither() -> None:
    days = lockup_fields(facts(prospectus_date=None))
    assert days["lockup_days"] == 180 and days["lockup_expiry"] is None and days["reason"]
    months = lockup_fields(facts(prospectus_date=None, lockup_n=6, lockup_unit="months"))
    assert months["lockup_days"] is None and months["lockup_expiry"] is None


def test_without_an_extracted_term_the_extraction_reason_stands_and_nothing_is_derived() -> None:
    got = lockup_fields(
        facts(extraction="AMBIGUOUS", lockup_n=pd.NA, lockup_unit=None, reason="no dominant term")
    )
    assert got == {"lockup_days": None, "lockup_expiry": None, "reason": "no dominant term"}


def test_hits_are_listed_oldest_filing_first() -> None:
    frame = pd.DataFrame(
        [
            ("0000000002", "B", pd.Timestamp("2026-09-10"), "Beta"),
            ("0000000001", "A", pd.Timestamp("2026-09-02"), None),
        ],
        columns=list(HIT_COLUMNS),
    )
    assert hits_of(frame) == [
        Hit("0000000001", "A", date(2026, 9, 2), None),
        Hit("0000000002", "B", date(2026, 9, 10), "Beta"),
    ]


def row(**kw: object) -> dict[str, object]:
    base: dict[str, object] = dict.fromkeys(COLUMNS)
    base |= {
        "ts": pd.Timestamp("2026-06-12T21:30:00Z"), "known_from": date(2026, 6, 12),
        "is_ipo": True, "early_release": False, "lockup_days": 180, "offer_price": 18.0,
        "prospectus_date": date(2026, 6, 12),
    }  # fmt: skip
    return base | kw


def test_a_stored_row_equals_a_fresh_one_across_nulls_dates_and_known_from() -> None:
    stored = row(prospectus_date=pd.Timestamp("2026-06-12"), lockup_days=180.0, ticker=float("nan"))
    fresh = row(known_from=date(2026, 10, 5), ticker=None)  # a version's own known_from is no value
    assert same_values(fresh, stored)
    assert "known_from" not in VALUES


def test_any_changed_value_is_a_difference() -> None:
    assert not same_values(row(lockup_days=90), row())
    assert not same_values(row(instrument_id="EQ:A"), row())
    assert same_values(row(rules_version="v2"), row(rules_version="v1"))  # the rules are no fact


def test_as_frame_has_the_declared_types() -> None:
    frame = as_frame([row(lockup_days=None, offer_price=None)])
    assert list(frame.columns) == COLUMNS and str(frame["lockup_days"].dtype) == "Int64"
    assert str(frame["ts"].dtype).endswith(", UTC]") and frame["is_ipo"].dtype == bool
