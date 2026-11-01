"""Fixed settlement rules (ADR 0088 F1): the ex-date assignment, expiry assignment, the cash-settled
index root, and the report skip (stock vs ETF, N3)."""

from datetime import date

from algotrade.engines.structures.settlement import (
    ASSIGNED,
    EXPIRED,
    early_assignment,
    expiry_kind,
    report_in_life,
)

EX = date(2026, 10, 20)
DAY = date(2026, 10, 19)


def test_ex_date_assignment_when_dividend_exceeds_extrinsic() -> None:
    # spot 110 vs strike 100: intrinsic 10; mid 10.20 -> extrinsic 0.20 < dividend 0.50
    assert early_assignment(DAY, EX, 0.50, 110.0, 100.0, 10.20)
    assert not early_assignment(DAY, EX, 0.10, 110.0, 100.0, 10.20)  # dividend below extrinsic


def test_no_early_assignment_for_otm_put_long_unknown_or_after_ex() -> None:
    assert not early_assignment(DAY, EX, 5.0, 90.0, 100.0, 0.3)  # OTM call
    assert not early_assignment(DAY, EX, 0.5, 110.0, 100.0, 10.2, short=False)
    assert not early_assignment(DAY, EX, 0.5, 110.0, 100.0, 10.2, is_call=False)
    assert not early_assignment(DAY, EX, None, 110.0, 100.0, 10.2)
    assert not early_assignment(DAY, EX, 0.5, 110.0, 100.0, float("nan"))
    assert not early_assignment(EX, EX, 0.5, 110.0, 100.0, 10.2)


def test_expiry_assignment() -> None:
    assert expiry_kind(95.0, 100.0, False, True, False) == ASSIGNED
    assert expiry_kind(105.0, 100.0, False, True, False) == EXPIRED
    assert expiry_kind(95.0, 100.0, False, False, False) == EXPIRED  # long
    assert expiry_kind(95.0, 100.0, False, True, True) == EXPIRED  # cash-settled index


def test_report_skip_stock_and_etf() -> None:
    entry, expiry = date(2026, 10, 5), date(2026, 11, 6)
    assert report_in_life("COMMON_STOCK", date(2026, 10, 25), entry, expiry) is True
    assert report_in_life("COMMON_STOCK", date(2026, 12, 1), entry, expiry) is False
    assert report_in_life("COMMON_STOCK", None, entry, expiry) is None
    assert report_in_life("ETF", None, entry, expiry) is False  # no report: passes


def test_unknown_spot_is_not_an_expiry() -> None:
    assert expiry_kind(float("nan"), 100.0, False, True, False) is None
