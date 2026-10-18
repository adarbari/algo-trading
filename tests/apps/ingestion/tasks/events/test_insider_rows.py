"""``insider_rows``: a Form 4 line's ``known_from`` (the New York session of SEC's acceptance,
rolled to a trading session, never the fetch's time), its restatement floor (the fetch's next
session; unchanged lines keep their stored stamp; a 4/A whose original is stored is a restatement)
and its id as of the filing date (a recycled ticker is two ids by date)."""

from datetime import UTC, date, datetime

import pandas as pd

from algotrade.data.resolver import SymbolResolver
from algotrade_ingestion.tasks.events import insider_rows as rows

FLOOR = date(2026, 10, 21)  # the earliest session a restated row may be known from


def line(accession: str = "A1", ts: str = "2026-09-30T20:30:00Z", **over: object) -> dict:
    base = {
        "instrument_id": "EQ:EXMP", "ts": pd.Timestamp(ts), "accession": accession, "line": 1,
        "owner_cik": "0000888001", "form": "4", "issuer_cik": "0000999001",
        "filing_date": date(2026, 9, 30), "period_of_report": date(2026, 9, 28),
        "amends_date": None, "transaction_date": date(2026, 9, 28), "derivative": False,
        "transaction_code": "P", "acquired_disposed": "A", "shares": 1000.0, "price": 12.5,
        "shares_after": 26000.0, "direct_indirect": "D", "is_director": True,
        "is_officer": True, "is_ten_pct_owner": False, "is_other": False,
        "officer_title": "CFO", "plan_10b5_1": None, "owner_count": 1,
    }  # fmt: skip
    return {**base, **over}


def frame(*lines: dict) -> pd.DataFrame:
    return pd.DataFrame(list(lines))


def test_known_from_is_the_first_session_whose_close_is_after_the_acceptance() -> None:
    ts = pd.Series(
        pd.to_datetime(
            [
                "2026-09-30T13:29:59Z",  # 09:29 ET, before the open: that session
                "2026-09-30T19:59:59Z",  # 15:59:59 ET, before the close: that session
                "2026-09-30T20:00:00Z",  # 16:00 ET, at the close: the next session
                "2026-09-30T20:30:00Z",  # 16:30 ET, after the close: the next session
                "2026-09-30T21:00:00Z",  # 17:00 ET: the next session
                "2026-10-01T02:00:00Z",  # 22:00 ET on the 30th: the next session
                "2026-01-15T14:35:00Z",  # winter: 09:35 ET
            ],
            utc=True,
        )
    )
    known = rows.known_session(ts)
    assert list(known) == [date(2026, 9, 30)] * 2 + [date(2026, 10, 1)] * 4 + [date(2026, 1, 15)]


def test_an_acceptance_on_a_closed_day_is_known_from_the_next_session() -> None:
    ts = pd.Series(
        pd.to_datetime(
            ["2026-04-03T15:00:00Z", "2026-10-10T15:00:00Z", "2026-09-07T15:00:00Z"], utc=True
        )
    )  # Good Friday (EDGAR open, market closed), a Saturday, Labor Day
    assert list(rows.known_session(ts)) == [date(2026, 4, 6), date(2026, 10, 12), date(2026, 9, 8)]


def test_a_backfilled_row_is_known_from_its_real_acceptance_not_the_fetch() -> None:
    fresh = frame(line(ts="2012-03-08T21:10:00Z"))  # 16:10 ET: after that day's close
    out = rows.stamp_known_from(fresh, pd.DataFrame(columns=rows.COLUMNS), FLOOR)
    assert out["known_from"].tolist() == [date(2012, 3, 9)]  # 2026's fetch changes nothing


def test_the_restatement_floor_is_the_session_after_the_fetch_day() -> None:
    friday_evening = datetime(2026, 10, 16, 23, 30, tzinfo=UTC)  # 19:30 ET Friday
    assert rows.restatement_floor(friday_evening) == date(2026, 10, 19)
    monday_morning = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)  # 05:00 ET Monday
    assert rows.restatement_floor(monday_morning) == date(2026, 10, 20)  # never the same day


def stored_line(known: date, **over: object) -> pd.DataFrame:
    return frame({**line(**over), "known_from": known})


def test_the_same_line_with_the_same_content_keeps_its_stored_stamp() -> None:
    stored = stored_line(date(2026, 10, 15))  # stored as restated on the 15th
    out = rows.stamp_known_from(frame(line()), stored, FLOOR)
    assert out["known_from"].tolist() == [date(2026, 10, 15)]


def test_a_line_that_changed_is_known_from_the_floor_not_its_acceptance() -> None:
    stored = stored_line(date(2026, 10, 1))
    out = rows.stamp_known_from(frame(line(price=12.0)), stored, FLOOR)
    assert out["known_from"].tolist() == [FLOOR]
    late = frame(line(price=12.0, ts="2026-11-02T15:00:00Z"))  # accepted after the floor: its own
    assert rows.stamp_known_from(late, stored, FLOOR)["known_from"].tolist() == [date(2026, 11, 2)]


def test_an_amendment_is_its_own_filing_known_from_its_own_acceptance() -> None:
    stored = stored_line(date(2026, 10, 1))  # the original
    amendment = line("A2", ts="2012-10-02T14:00:00Z", form="4/A", amends_date=date(2026, 9, 30))
    out = rows.stamp_known_from(frame(amendment), stored, FLOOR)
    assert out["known_from"].tolist() == [date(2012, 10, 2)]  # a historical 4/A: no floor


def test_the_original_and_its_amendment_read_together_keep_their_own_sessions() -> None:
    original = line(ts="2026-09-30T20:30:00Z")
    amendment = line("A2", ts="2026-10-02T14:00:00Z", form="4/A", amends_date=date(2026, 9, 30))
    out = rows.stamp_known_from(
        frame(original, amendment), pd.DataFrame(columns=rows.COLUMNS), FLOOR
    )
    assert out["known_from"].tolist() == [date(2026, 10, 1), date(2026, 10, 2)]


def test_symbols_resolve_as_of_the_filing_date_and_a_recycled_ticker_is_two_ids() -> None:
    old = SymbolResolver(ids={"OLD": "EQ:OLD1"})
    new = SymbolResolver(ids={"OLD": "EQ:OLD2", "BRK.B": "EQ:BRKB"})
    resolver = lambda day: old if day < date(2014, 1, 1) else new  # noqa: E731
    data = pd.DataFrame(
        {
            "issuer_symbol": ["OLD", "OLD", "BRK-B", "GOOG, GOOGL", "ZZZZ", None, "NONE"],
            "filing_date": [date(2010, 5, 1), date(2020, 5, 1)] + [date(2020, 5, 1)] * 5,
        }
    )
    out, unresolved = rows.resolve_ids(data, resolver)
    assert out["instrument_id"].tolist() == ["EQ:OLD1", "EQ:OLD2", "EQ:BRKB"]
    assert unresolved == 4  # GOOG / GOOGL, ZZZZ, none and "NONE" are in no listing of the day
    assert (
        rows.symbol_candidates("GOOG, GOOGL")[:1] == ["GOOG"] and rows.symbol_candidates("") == []
    )
