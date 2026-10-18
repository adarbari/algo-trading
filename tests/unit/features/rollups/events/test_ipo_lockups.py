"""``ipo_lockups@v1``: the nearest lock-up expiry of an instrument as the session knew it. The
CIK of a prospectus is mapped to an instrument through the company snapshot of the session, never
through the instrument id stored on the row (a later run filled it: a survivorship leak); only
IPO prospectuses with an expiry count; the count runs negative after the expiry down to -20."""

from datetime import date

import pandas as pd

from algotrade.features.rollups.events import ipo_lockups as il

SESSION = date(2026, 10, 9)  # a Friday


def _row(cik: str, expiry: date | None, **changes: object) -> dict[str, object]:
    row: dict[str, object] = {
        "cik": cik, "accession": f"0001-{cik}", "is_ipo": True, "early_release": False,
        "lockup_expiry": expiry, "offer_price": 18.0, "lockup_days": 180,
        "instrument_id": None,
    }  # fmt: skip
    return row | changes


def _inputs(
    rows: list[dict[str, object]] | None, company: list[tuple[str, str]] | None
) -> dict[str, pd.DataFrame | None]:
    return {
        il.EVENTS: None if rows is None else pd.DataFrame(rows),
        il.COMPANY: None if company is None else pd.DataFrame(
            company, columns=["instrument_id", "cik"]
        ),
    }  # fmt: skip


def test_sessions_to_expiry_is_positive_ahead_zero_on_the_day_and_negative_after() -> None:
    out = il.compute(
        _inputs(
            [
                _row("1", date(2026, 10, 14)),
                _row("2", date(2026, 10, 9), early_release=True),
                _row("3", date(2026, 10, 7), lockup_days=90, offer_price=None),
            ],
            [("EQ:A", "1"), ("EQ:B", "2"), ("EQ:C", "3")],
        ),
        SESSION,
        None,
    ).set_index("instrument_id")
    assert out.at["EQ:A", "sessions_to_lockup_expiry"] == 3
    assert out.at["EQ:A", "lockup_expiry_date"] == date(2026, 10, 14)
    assert out.at["EQ:A", "lockup_release_terms"] == "standard"
    assert out.at["EQ:B", "sessions_to_lockup_expiry"] == 0
    assert out.at["EQ:B", "lockup_release_terms"] == "early_release"
    assert out.at["EQ:C", "sessions_to_lockup_expiry"] == -2
    assert out.at["EQ:C", "lockup_days"] == 90
    assert pd.isna(out.at["EQ:C", "ipo_offer_price"])
    assert out.at["EQ:A", "ipo_offer_price"] == 18.0


def test_the_cik_maps_through_the_company_snapshot_never_the_rows_own_instrument() -> None:
    """The row carries ``EQ:LATER`` (filled by a run after the session); the company snapshot of
    the session has the CIK under ``EQ:ASOF`` only. A CIK in no snapshot gives no row."""
    out = il.compute(
        _inputs(
            [
                _row("1", date(2026, 10, 14), instrument_id="EQ:LATER"),
                _row("2", date(2026, 10, 14), instrument_id="EQ:ORPHAN"),
            ],
            [("EQ:ASOF", "1"), ("EQ:OTHER", "9")],
        ),
        SESSION,
        None,
    )
    assert list(out["instrument_id"]) == ["EQ:ASOF"]


def test_a_cik_with_two_share_classes_gives_both_the_event() -> None:
    out = il.compute(
        _inputs([_row("1", date(2026, 10, 14))], [("EQ:A", "1"), ("EQ:A2", "1")]), SESSION, None
    )
    assert sorted(out["instrument_id"]) == ["EQ:A", "EQ:A2"]


def test_only_ipo_rows_with_an_expiry_within_twenty_sessions_back_are_read() -> None:
    out = il.compute(
        _inputs(
            [
                _row("1", date(2026, 10, 14), is_ipo=False),  # a follow-on offering
                _row("2", None),  # no stated expiry
                _row("3", date(2026, 9, 10)),  # 21 sessions ago: over
                _row("4", date(2026, 9, 11)),  # 20 sessions ago: the last read
            ],
            [("EQ:A", "1"), ("EQ:B", "2"), ("EQ:C", "3"), ("EQ:D", "4")],
        ),
        SESSION,
        None,
    ).set_index("instrument_id")
    assert list(out.index) == ["EQ:D"]
    assert out.at["EQ:D", "sessions_to_lockup_expiry"] == -il.AFTER


def test_the_earliest_expiry_in_the_window_is_the_nearest() -> None:
    out = il.compute(
        _inputs(
            [_row("1", date(2026, 12, 1)), _row("1", date(2026, 10, 14), accession="0002")],
            [("EQ:A", "1")],
        ),
        SESSION,
        None,
    )
    assert list(out["lockup_expiry_date"]) == [date(2026, 10, 14)]


def test_no_prospectuses_or_no_company_snapshot_has_no_rows() -> None:
    assert il.compute(_inputs(None, [("EQ:A", "1")]), SESSION, None).empty
    assert il.compute(_inputs([_row("1", date(2026, 10, 14))], None), SESSION, None).empty
