"""State Street SPDR ETF holdings: one daily workbook per fund (``HoldingsSource``).

State Street's public fund finder lists every U.S. SPDR ETF with the path of its daily holdings
file (``Holdings-daily``): ``/library-content/products/fund-data/etfs/us/holdings-daily-us-en-
<ticker>.xlsx``, the same file SPY's membership is read from. Funds without one (the gold
trusts) are not listed. Equity funds give a ticker and a CUSIP per line, bond funds an ISIN and
no ticker. Weights are percent of the fund.
"""

import json
import re

from algotrade_sources.framework.base import FetchRequest, Normalized
from algotrade_sources.framework.holdings import (
    clean_text,
    fraction,
    funds_frame,
    holding_ticker,
    holdings_frame,
    is_cusip,
    number,
)
from algotrade_sources.framework.http import Http
from algotrade_sources.vendors.ssga.workbook import read_workbook

SOURCE = "ssga_holdings"
DATASET = "etf_holdings"
DIRECTORY = "directory"
SITE = "https://www.ssga.com"
FINDER_URL = (
    f"{SITE}/bin/v1/ssmp/fund/fundfinder"
    "?country=us&language=en&role=intermediary&product=etfs&ui=fund-finder"
)
_MARK = re.compile(r"[®™]")  # the finder prints fund names and tickers with trademark signs


def _plain(text: object) -> str:
    return _MARK.sub("", str(text)).strip()


def parse_finder(payload: bytes) -> dict[str, tuple[str, str]]:
    """The fund finder -> ticker -> (fund name, holdings file path), funds with a file only."""
    funds = json.loads(payload)["data"]["funds"]["etfs"]["datas"]
    out: dict[str, tuple[str, str]] = {}
    for fund in funds:
        for document in fund.get("documentPdf") or []:
            if document.get("docType") == "Holdings-daily" and document.get("docs"):
                out[_plain(fund["fundTicker"]).upper()] = (
                    _plain(fund["fundName"]),
                    str(document["docs"][0]["path"]),
                )
    return out


_FUTURE = re.compile(r"\b(FUTURES?|E-MINI)\b", re.IGNORECASE)
_MONEY_MARKET = re.compile(r"MONEY MARKET|LIQUID RESERVES|\bSTIF\b|SWEEP", re.IGNORECASE)


def asset_class(name: str | None, identifier: str | None, bonds: bool) -> str:
    """The workbook has no asset class column: cash by its ``CASH_*`` id, futures and money
    market sweeps by their names (a heuristic), else the fund's kind."""
    if (identifier or "").upper().startswith("CASH"):
        return "Cash"
    if _FUTURE.search(name or ""):
        return "Futures"
    if _MONEY_MARKET.search(name or ""):
        return "Money Market"
    return "Fixed Income" if bonds else "Equity"


class SsgaHoldings:
    """Implements ``base.HoldingsSource``. Request keys: ``directory``, or a SPDR ticker."""

    name = SOURCE
    dataset = DATASET
    directory_key = DIRECTORY
    scope_limited = False
    cadence_days = 1

    def __init__(self, http: Http) -> None:
        self._http = http
        self._paths: dict[str, str] = {}

    def fetch(self, request: FetchRequest) -> bytes | None:
        if request.key == DIRECTORY:
            payload = self._http.get(FINDER_URL)
            if payload is not None:
                self._paths = {t: p for t, (_, p) in parse_finder(payload).items()}
            return payload
        if not self._paths:
            self.fetch(FetchRequest(DIRECTORY))
        path = self._paths.get(request.key.upper())
        return None if path is None else self._http.get(f"{SITE}{path}")

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        if request.key == DIRECTORY:
            funds = funds_frame((t, name) for t, (name, _) in parse_finder(payload).items())
            return Normalized(None, {}, parsed={"funds": funds})
        book = read_workbook(payload)
        if book.fund is not None and book.fund != request.key.upper():
            raise ValueError(f"{request.key}: the file is for {book.fund}")
        table = book.table
        if book.as_of is None:  # a changed "Holdings: As of ..." line is a layout change
            raise ValueError(f"{request.key}: the workbook does not say what date it is as of")
        if table.empty:
            raise ValueError(f"{request.key}: the workbook's table has no lines")
        bonds = "Maturity" in table.columns
        size = "Par Value" if bonds else "Shares Held"
        rows = []
        for line in table.to_dict("records"):
            ticker = holding_ticker(line.get("Ticker"))
            identifier = clean_text(line.get("Identifier"))
            kind = asset_class(clean_text(line.get("Name")), identifier, bonds)
            rows.append(
                {
                    "holding_symbol": ticker,
                    "holding_name": clean_text(line.get("Name")),
                    "weight": fraction(line.get("Weight")),
                    "asset_class": kind,
                    "sector": clean_text(line.get("Sector")),
                    "shares": number(line.get(size)),
                    "identifier": None if kind == "Cash" else identifier,
                    # The file has no exchange or country: a USD line with a U.S. CUSIP.
                    "us_listed": ticker is not None
                    and kind == "Equity"
                    and line.get("Local Currency") == "USD"
                    and is_cusip(identifier),
                    "filed": None,
                }
            )
        holdings = holdings_frame(rows)
        if holdings.empty:
            raise ValueError(f"{request.key}: no line of the workbook has a readable weight")
        notes = {"unreadable_lines": len(rows) - len(holdings)}
        return Normalized(book.as_of, {}, notes=notes, parsed={"holdings": holdings})
