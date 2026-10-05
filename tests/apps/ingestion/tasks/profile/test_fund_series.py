"""Matching the ETFs the SEC fund ticker map misses to their SEC fund series."""

import pandas as pd

from algotrade_ingestion.tasks.profile.fund_series import (
    FUND_COLUMNS,
    extend_fund_map,
    normalize_name,
)

FUNDS = pd.DataFrame(
    [("QQQ", "S000000001", "C000000001", "0000000001")], columns=FUND_COLUMNS
)  # the SEC ticker map: QQQ only


def series(*rows: tuple[str, str, str, str, str | None]) -> pd.DataFrame:
    """(series id, series name, class id, class name, class ticker) -> the series / class frame."""
    return pd.DataFrame(
        [(s, sn, c, cn, t, "0000000002") for s, sn, c, cn, t in rows],
        columns=["series_id", "series_name", "class_id", "class_name", "class_ticker", "cik"],
    )


def etfs(*pairs: tuple[str, str]) -> pd.DataFrame:
    return pd.DataFrame(pairs, columns=["symbol", "name"])


def test_names_are_compared_without_case_punctuation_or_ampersand_spelling() -> None:
    assert normalize_name("Innovator U.S. Equity Power Buffer ETF - October") == (
        "INNOVATOR U S EQUITY POWER BUFFER ETF OCTOBER"
    )
    assert normalize_name("S&P 500  Fund") == normalize_name("s and p 500 fund")
    assert normalize_name(None) == "" and normalize_name("") == ""


def test_an_etf_in_the_map_keeps_its_row_and_is_not_matched_again() -> None:
    found = series(("S000000009", "Invesco QQQ Trust", "C000000009", "QQQ", "QQQ"))
    extended, counts = extend_fund_map(FUNDS, found, etfs(("QQQ", "Invesco QQQ Trust")))
    assert extended.equals(FUNDS) and counts == {"by_ticker": 0, "by_name": 0, "ambiguous": 0}


def test_a_class_ticker_that_names_one_series_matches_whatever_the_etf_is_called() -> None:
    found = series(("S000000005", "Some Trust Series", "C000000005", "ETF Shares", "NEWX"))
    extended, counts = extend_fund_map(FUNDS, found, etfs(("NEWX", "A Totally Different Name")))
    added = extended.set_index("symbol").loc["NEWX"]
    assert (added["series_id"], added["class_id"], added["cik"]) == (
        "S000000005", "C000000005", "0000000002",
    )  # fmt: skip
    assert counts == {"by_ticker": 1, "by_name": 0, "ambiguous": 0}


def test_a_name_that_fits_one_series_or_one_of_its_classes_matches() -> None:
    found = series(
        ("S000000006", "Roundhill Memory ETF", "C000000006", "Roundhill Memory ETF", None),
        ("S000000007", "Acme Trust", "C000000007", "Acme Growth ETF", None),
    )
    wanted = etfs(("DRAM", "ROUNDHILL  MEMORY ETF"), ("ACME", "Acme Growth ETF"))
    extended, counts = extend_fund_map(FUNDS, found, wanted)
    got = extended.set_index("symbol")["series_id"]
    assert got["DRAM"] == "S000000006" and got["ACME"] == "S000000007"  # series name; class name
    assert counts == {"by_ticker": 0, "by_name": 2, "ambiguous": 0}


def test_a_name_or_ticker_shared_by_two_series_is_not_matched() -> None:
    found = series(
        ("S000000010", "Bitwise Crypto ETF", "C000000010", "Bitwise Crypto ETF", "BITQ"),
        ("S000000011", "Bitwise Crypto ETF", "C000000011", "Bitwise Crypto ETF", "BITQ"),
    )
    extended, counts = extend_fund_map(FUNDS, found, etfs(("BITQ", "Bitwise Crypto ETF")))
    assert list(extended["symbol"]) == ["QQQ"]
    assert counts == {"by_ticker": 0, "by_name": 0, "ambiguous": 1}


def test_nothing_changes_without_series_or_without_missing_etfs() -> None:
    nothing = series()
    assert extend_fund_map(FUNDS, nothing, etfs(("NEWX", "New ETF")))[0] is FUNDS
    some = series(("S000000012", "New ETF", "C000000012", "New ETF", None))
    assert extend_fund_map(FUNDS, some, etfs(("QQQ", "Invesco QQQ Trust")))[0] is FUNDS
