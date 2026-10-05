"""iShares ETF holdings: the CSV each fund page offers as its latest holdings
(``HoldingsSource``).

iShares' product screener (the data behind its fund finder) lists every U.S. iShares fund with
its page path, e.g. ``/us/products/239726/ishares-core-sp-500-etf``. The page advertises its
holdings download as ``<page>/latest-holdings.csv`` (a schema.org ``DataDownload``). The file
starts with a few ``Fund Holdings as of`` lines, then a table with a header row: equity funds
begin ``Ticker,Name,Sector,Asset Class,Market Value,Weight (%)...``; bond funds have no Ticker
and carry ``CUSIP`` / ``ISIN``. Foreign lines use their local ticker (Roche prints as ``ROP``,
which is Roper in the U.S.), so only lines located in the United States count as U.S. listings.
Funds that hold a physical metal or have no file answer HTTP 400 (read as "no file").
"""

import csv
import io
import json
from datetime import date, datetime

from algotrade_sources.framework.base import FetchRequest, Normalized
from algotrade_sources.framework.holdings import (
    clean_text,
    fraction,
    funds_frame,
    holding_ticker,
    holdings_frame,
    number,
)
from algotrade_sources.framework.http import Http, HttpError

SOURCE = "ishares_holdings"
DATASET = "etf_holdings"
DIRECTORY = "directory"
SITE = "https://www.ishares.com"
SCREENER_URL = (
    f"{SITE}/us/product-screener/product-screener-v3.1.jsn"
    "?dcrPath=/templatedata/config/product-screener-v3/data/en/us-ishares/"
    "ishares-product-screener-backend-config&siteEntryPassthrough=true"
)
_US = "United States"


def no_file(error: HttpError) -> bool:
    """HTTP 400 is how iShares says a fund has no holdings file (physical metal trusts)."""
    return error.status == 400


def parse_screener(payload: bytes) -> dict[str, tuple[str, str]]:
    """The product screener -> ticker -> (fund name, page path)."""
    out: dict[str, tuple[str, str]] = {}
    for product in json.loads(payload).values():
        ticker, path = product.get("localExchangeTicker"), product.get("productPageUrl")
        if ticker and path:
            out[str(ticker).strip().upper()] = (str(product.get("fundName") or ticker), str(path))
    return out


def _decode(payload: bytes) -> str:
    try:
        return payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        return payload.decode("latin-1")


def parse_csv(payload: bytes) -> tuple[date | None, list[dict[str, str]]]:
    """-> (the as-of date, the table's lines as dicts keyed by the header row)."""
    rows = list(csv.reader(io.StringIO(_decode(payload))))
    as_of = None
    for row in rows[:6]:
        if len(row) >= 2 and row[0].startswith("Fund Holdings as of"):
            as_of = datetime.strptime(row[1].strip(), "%b %d, %Y").date()  # noqa: DTZ007
    header = next((i for i, r in enumerate(rows) if "Weight (%)" in r), None)
    if header is None:
        return as_of, []
    names = rows[header]
    lines = []
    for row in rows[header + 1 :]:
        if len(row) < len(names):  # blank line or disclaimer text after the table
            break
        lines.append(dict(zip(names, row, strict=False)))
    return as_of, lines


class IsharesHoldings:
    """Implements ``base.HoldingsSource``. Request keys: ``directory``, or an iShares ticker."""

    name = SOURCE
    dataset = DATASET
    directory_key = DIRECTORY
    scope_limited = False
    cadence_days = 1

    def __init__(self, http: Http) -> None:
        self._http = http
        self._pages: dict[str, str] = {}

    def fetch(self, request: FetchRequest) -> bytes | None:
        if request.key == DIRECTORY:
            payload = self._http.get(SCREENER_URL)
            if payload is not None:
                self._pages = {t: p for t, (_, p) in parse_screener(payload).items()}
            return payload
        if not self._pages:
            self.fetch(FetchRequest(DIRECTORY))
        page = self._pages.get(request.key.upper())
        return None if page is None else self._http.get(f"{SITE}{page}/latest-holdings.csv")

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        if request.key == DIRECTORY:
            funds = funds_frame((t, name) for t, (name, _) in parse_screener(payload).items())
            return Normalized(None, {}, parsed={"funds": funds})
        as_of, lines = parse_csv(payload)
        if not lines or as_of is None:
            return None
        rows = []
        for line in lines:
            ticker = holding_ticker(line.get("Ticker"))
            kind = clean_text(line.get("Asset Class"))
            rows.append(
                {
                    "holding_symbol": ticker,
                    "holding_name": clean_text(line.get("Name")),
                    "weight": fraction(line.get("Weight (%)")),
                    "asset_class": kind,
                    "sector": clean_text(line.get("Sector")),
                    "shares": number(line.get("Quantity", line.get("Par Value"))),
                    "identifier": clean_text(line.get("CUSIP")) or clean_text(line.get("ISIN")),
                    "us_listed": ticker is not None
                    and kind == "Equity"
                    and line.get("Location") == _US,
                }
            )
        return Normalized(as_of, {}, parsed={"holdings": holdings_frame(rows)})
