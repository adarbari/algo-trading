"""``fund_reference@v1``: the stock or basket a leveraged or inverse fund tracks, from its
holdings, then its name (ADR 0050)."""

from datetime import UTC, date, datetime

import pandas as pd

from algotrade.features.framework.feature import not_applicable
from algotrade.features.framework.runner import compute_one
from algotrade.features.rollups.reference import fund_reference
from algotrade.features.rollups.reference.fund_reference import GROUP, compute
from tests.helpers.rollup_store import store
from tests.helpers.stored_frames import holdings_rows, stamped

SESSION = date(2026, 10, 5)
STOCKS = {"TSLA": "EQ:TSLA", "NVDA": "EQ:NVDA", "AAPL": "EQ:AAPL", "MSFT": "EQ:MSFT"}


def line(
    fund: str, name: str, kind: str = "Equity", ticker: str | None = None, weight: float = 0.5,
    sector: str | None = None,
) -> dict[str, object]:  # fmt: skip
    """One ``holdings/etf`` row (only the columns the group reads)."""
    held = STOCKS.get(ticker or "")
    return {
        "instrument_id": fund, "rank": 1, "holding_symbol": ticker, "holding_id": held,
        "holding_name": name, "weight": weight, "asset_class": kind, "sector": sector,
    }  # fmt: skip


def fund(symbol: str, name: str, **flags: object) -> dict[str, object]:
    return {
        "instrument_id": f"EQ:{symbol}", "symbol": symbol, "name": name,
        "security_type": "ETF", "is_leveraged": True, "is_inverse": False, **flags,
    }  # fmt: skip


def result(
    funds: list[dict[str, object]], lines: list[dict[str, object]] | None = None
) -> dict[str, dict[str, object]]:
    """The group's rows by fund, over the stocks above, QQQ (an ETF) and the given funds."""
    plain = [
        {"instrument_id": i, "symbol": s, "name": f"{s} Inc", "security_type": "COMMON_STOCK",
         "is_leveraged": False, "is_inverse": False}
        for s, i in STOCKS.items()
    ]  # fmt: skip
    etf = [fund("QQQ", "Invesco QQQ Trust", is_leveraged=False)]
    reference = pd.DataFrame([*plain, *etf, *funds])
    symbols = pd.DataFrame(
        {"symbol": reference["symbol"], "instrument_id": reference["instrument_id"]}
    )
    holdings = None if not lines else pd.DataFrame(lines)
    inputs = {
        fund_reference.REFERENCE: reference,
        fund_reference.SYMBOLS: symbols,
        fund_reference.HOLDINGS: holdings,
    }
    frame = compute(inputs, SESSION, None)
    return {str(r["instrument_id"]): r for r in frame.to_dict("records")}


def row(found: dict[str, dict[str, object]], symbol: str) -> tuple[object, ...]:
    r = found[f"EQ:{symbol}"]
    cols = ("reference_instrument_id", "reference_kind", "reference_source", "reference_status")
    return tuple(None if pd.isna(r[c]) else r[c] for c in cols)  # type: ignore[call-overload]


def test_only_leveraged_and_inverse_funds_get_a_row() -> None:
    found = result([fund("TSLQ", "Direxion Daily TSLA Bear 1X Shares", is_leveraged=False,
                         is_inverse=True)])  # fmt: skip
    assert set(found) == {"EQ:TSLQ"}  # not the stocks, not QQQ
    assert row(found, "TSLQ") == ("EQ:TSLA", "single_stock", "name_rule", "LINKED")


def test_a_swap_line_that_names_one_ticker_links_the_fund_from_the_holdings() -> None:
    tsll = fund("TSLL", "Leveraged Tesla Fund")  # the name says nothing: the holdings do
    lines = [
        line("EQ:TSLL", "TSLA Total Return Swap Goldman Sachs International", "Derivative"),
        line("EQ:TSLL", "Goldman Sachs Financial Square Treasury Fund", "Equity", None),
    ]
    assert row(result([tsll], lines), "TSLL") == ("EQ:TSLA", "single_stock", "holdings", "LINKED")


def test_the_one_equity_a_fund_holds_is_its_reference_not_the_money_market_sweep() -> None:
    aapu = fund("AAPU", "Leveraged Apple Fund")
    lines = [
        line("EQ:AAPU", "Apple Inc", "Equity", "AAPL", 0.4),
        line("EQ:AAPU", "PROSHARES GENIUS MNY MKT ETF", "Equity", "IQMM", 0.2),
        line("EQ:AAPU", "NASDAQ 100 SWAP Citibank NA", "Derivative", None, 0.4),
    ]
    assert row(result([aapu], lines), "AAPU") == ("EQ:AAPL", "single_stock", "holdings", "LINKED")


def test_holdings_win_over_the_name_when_they_settle_it() -> None:
    odd = fund("ODD", "Direxion Daily NVDA Bull 2X Shares")
    lines = [line("EQ:ODD", "Total Return Swap on AAPL", "Derivative")]
    assert row(result([odd], lines), "ODD")[:3] == ("EQ:AAPL", "single_stock", "holdings")


def test_an_index_fund_holding_many_stocks_is_a_basket_not_one_stock() -> None:
    tqqq = fund("TQQQ", "ProShares UltraPro QQQ")
    lines = [
        line("EQ:TQQQ", "NVIDIA", "Equity", "NVDA", 0.1, "Technology"),
        line("EQ:TQQQ", "Apple", "Equity", "AAPL", 0.1, "Technology"),
        line("EQ:TQQQ", "Microsoft", "Equity", "MSFT", 0.1, "Technology"),
        line("EQ:TQQQ", "NASDAQ-100 INDEX SWAP", "Derivative", None, 0.7),
    ]
    assert row(result([tqqq], lines), "TQQQ") == (None, "index", "name_rule", "BASKET")


def test_a_basket_without_a_keyword_takes_its_kind_from_the_holdings_sectors() -> None:
    def held(sectors: list[str | None]) -> list[dict[str, object]]:
        stocks = list(STOCKS)
        return [
            line("EQ:BSK", s or "x", "Equity", t, 0.2, s)
            for t, s in zip(stocks, sectors, strict=True)
        ]

    basket = fund("BSK", "Leveraged Thing Fund")
    four = ["Technology", "Financials", "Health Care", "Energy"]
    assert row(result([basket], held(four)), "BSK") == (None, "index", "holdings", "BASKET")
    two = ["Technology", "Technology", "Technology", "Financials"]
    assert row(result([basket], held(two)), "BSK") == (None, "sector", "holdings", "BASKET")
    assert row(result([basket], held([None] * 4)), "BSK")[1] == "index"  # none stated


def test_a_fund_with_no_holdings_stored_is_read_by_its_name() -> None:
    nvdl = fund("NVDL", "GraniteShares 2x Long NVDA Daily ETF")
    assert row(result([nvdl]), "NVDL") == ("EQ:NVDA", "single_stock", "name_rule", "LINKED")
    soxl = fund("SOXL", "Direxion Daily Semiconductor Bull 3X Shares")
    assert row(result([soxl]), "SOXL") == (None, "sector", "name_rule", "BASKET")


def test_a_swap_naming_two_stocks_is_a_basket_and_the_name_is_not_asked_for_a_stock() -> None:
    pair = fund("PAIR", "Direxion Daily NVDA Bull 2X Shares")
    lines = [line("EQ:PAIR", "Swap long NVDA short AAPL", "Derivative")]
    assert row(result([pair], lines), "PAIR")[0] is None
    assert row(result([pair], lines), "PAIR")[3] == "BASKET"


def test_a_ticker_that_is_not_a_stock_is_not_a_single_stock_reference() -> None:
    qld = fund("QLD", "Direxion Daily QQQ Bull 2X Shares")  # QQQ is an ETF in the reference
    assert row(result([qld]), "QLD") == (None, "index", "name_rule", "BASKET")
    etf_only = [line("EQ:QLD", "Invesco QQQ Trust", "Equity", "QQQ", 1.0)]
    assert row(result([fund("QLD", "Leveraged Fund")], etf_only), "QLD")[0] is None


def test_a_named_ticker_the_reference_does_not_list_is_unlisted() -> None:
    zzz = fund("ZZZU", "Direxion Daily ZZZZ Bull 2X Shares")
    assert row(result([zzz]), "ZZZU") == (None, "single_stock", "name_rule", "UNLISTED")
    nasdaq = fund("NDXU", "Direxion Daily NASDAQ Bull 2X Shares")  # a keyword beats a non-ticker
    assert row(result([nasdaq]), "NDXU") == (None, "index", "name_rule", "BASKET")


def test_futures_funds_are_commodity_or_none_never_a_stock() -> None:
    oil = fund("UCOX", "Leveraged Thing Fund")  # no keyword in the name: the holdings say
    futures = [line("EQ:UCOX", "WTI CRUDE FUTURE Nov26", "Futures", None, 0.9)]
    assert row(result([oil], futures), "UCOX") == (None, "commodity", "holdings", "BASKET")
    vix = fund("SVXY", "ProShares Short VIX Short-Term Futures ETF", is_leveraged=False,
               is_inverse=True)  # fmt: skip
    futures = [line("EQ:SVXY", "CBOE VIX FUTURE Nov26", "Futures", None, 1.0)]
    assert row(result([vix], futures), "SVXY") == (None, "none", None, "BASKET")


def test_a_fund_with_neither_holdings_nor_a_name_match_has_no_reference() -> None:
    mystery = fund("MYST", "ProShares Mystery Fund")
    assert row(result([mystery]), "MYST") == (None, "none", None, "NO_REFERENCE")
    nothing = [line("EQ:MYST", "Net Other Assets (Liabilities)", "Cash", None, 1.0)]
    assert row(result([mystery], nothing), "MYST") == (None, "none", None, "NO_REFERENCE")


def test_without_the_symbol_map_a_name_links_nothing() -> None:
    reference = pd.DataFrame([fund("TSLL", "Direxion Daily TSLA Bull 2X Shares")])
    frame = compute({fund_reference.REFERENCE: reference}, SESSION, None)
    assert frame.iloc[0]["reference_status"] == "UNLISTED"


def test_the_group_applies_to_leveraged_funds_only() -> None:
    assert {f.applies_to for f in GROUP.features} == {"leveraged_fund"}
    assert not_applicable(["leveraged_fund"], True, "COMMON_STOCK", None, False, False)
    assert not not_applicable(["leveraged_fund"], True, "ETF", None, True, False)
    assert not not_applicable(["leveraged_fund"], True, "ETF", None, False, True)
    assert not not_applicable(["leveraged_fund"], True, "ETF", None, None, None)  # null: unknown
    assert not not_applicable(["leveraged_fund"], True, "ETF", None, False, None)
    assert not_applicable([], True, "ETF", None, False, False) == ""  # applies to any


def test_computed_from_the_stored_reference_holdings_and_symbols_point_in_time() -> None:
    writer, reader = store()
    names = {"TSLA": "Tesla Inc", "TSLL": "Direxion Daily TSLA Bull 2X Shares", "AAPL": "Apple"}
    rows = [
        {"instrument_id": f"EQ:{s}", "symbol": s, "name": n, "asset_class": "EQ",
         "security_type": "ETF" if s == "TSLL" else "COMMON_STOCK", "multiplier": 1.0,
         "status": "ACTIVE", "is_leveraged": s == "TSLL", "is_inverse": False}
        for s, n in names.items()
    ]  # fmt: skip
    writer.write_table("instruments/reference", SESSION, "r", stamped(rows, SESSION, "r"))
    swap = holdings_rows("EQ:TSLL", date(2026, 10, 2), [(None, "AAPL swap", 1.0)])
    for r in swap:
        r["asset_class"] = "Derivative"
    stored = datetime(2026, 10, 6, 22, tzinfo=UTC)  # the run after the session
    writer.write_table(
        "holdings/etf", date(2026, 10, 6), "h", stamped(swap, date(2026, 10, 6), "h", stored)
    )
    before = compute_one(reader, GROUP, SESSION).frame
    assert before is not None and len(before) == 1
    assert list(before[["reference_instrument_id", "reference_source"]].iloc[0]) == [
        "EQ:TSLA",
        "name_rule",
    ]  # the swap was stored after the session: not seen
    after = compute_one(reader, GROUP, date(2026, 10, 6)).frame
    assert after is not None
    assert list(after[["reference_instrument_id", "reference_source"]].iloc[0]) == [
        "EQ:AAPL",
        "holdings",
    ]
