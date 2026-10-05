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

Funds that overlay futures (IJH, IJR) publish a second layout: no ``Weight (%)``, but ``Market
Weight`` and ``Notional Weight`` (the futures line has a notional weight and no market weight).
``Market Weight`` is the share of the fund's market value and adds up to 100%, so it is the
weight; the futures line has none and is dropped, like any line whose weight does not read.
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
UNLISTED = ("NO MARKET (E.G. UNLISTED)",)  # an unlisted line is not a US listing
WEIGHT_COLUMNS = ("Weight (%)", "Market Weight")  # the two layouts' weight column
MAX_WEIGHT_DRIFT = 0.001  # market-value weights may differ from the published ones by 0.1 pt


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
    if as_of is None:  # a changed "Fund Holdings as of" line is a layout change
        raise ValueError("the file does not say what date it is as of")
    header = next((i for i, r in enumerate(rows) if any(c in r for c in WEIGHT_COLUMNS)), None)
    if header is None:
        raise ValueError("the file has no table with a Weight (%) or Market Weight column")
    names = rows[header]
    lines = []
    for row in rows[header + 1 :]:
        if len(row) < len(names):  # blank line or disclaimer text after the table
            break
        lines.append(dict(zip(names, row, strict=False)))
    if not lines:
        raise ValueError("the file's table has no lines")
    return as_of, lines


def weight_column(lines: list[dict[str, str]]) -> str:
    """The weight column the file's table has (``WEIGHT_COLUMNS``, in that order of preference)."""
    return next(c for c in WEIGHT_COLUMNS if c in lines[0])


def line_weights(
    lines: list[dict[str, str]], column: str = WEIGHT_COLUMNS[0]
) -> list[float | None]:
    """Each line's weight as a fraction of the fund. The published ``Weight (%)`` has two
    decimals (a 13k-line bond fund sums to 82%), so when every line has a market value the
    weight is its share of the sum of market values, provided that agrees with the published
    weights to 0.1 point; otherwise the published weights stand (an unreadable one is ``None``
    and the line is dropped)."""
    published = [fraction(line.get(column)) for line in lines]
    values = [number(line.get("Market Value")) for line in lines]
    total = sum(v for v in values if v is not None)
    if any(v is None for v in values) or total <= 0:
        return published
    derived = [round(v / total, 12) for v in values if v is not None]
    if any(
        p is None or abs(d - p) > MAX_WEIGHT_DRIFT for d, p in zip(derived, published, strict=True)
    ):
        return published
    return [*derived]


MAX_ZERO_SHARE = 0.25  # more lines than this published as 0.00% (a bond fund): no judging


def published_sum(lines: list[dict[str, str]], column: str = WEIGHT_COLUMNS[0]) -> float | None:
    """The sum of the file's own ``Weight (%)`` column as a fraction, when it can be judged: two
    decimals round most lines of a bond fund to 0.00 (AGG's 13k lines sum to 82%), so it is
    reported only when few lines are zero. A file cut short sums to less than 100%, which the
    market-value weights (they always add up to 100% of what is left) cannot show."""
    published = [fraction(line.get(column)) for line in lines]
    readable = [w for w in published if w is not None]
    zeros = sum(1 for w in readable if w == 0)
    if len(readable) < len(lines) or zeros > MAX_ZERO_SHARE * len(lines):
        return None
    return sum(readable)


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
        assert as_of is not None  # parse_csv raises without a date
        column = weight_column(lines)
        weights = line_weights(lines, column)
        rows = []
        for line, weight in zip(lines, weights, strict=True):
            ticker = holding_ticker(line.get("Ticker"))
            kind = clean_text(line.get("Asset Class"))
            rows.append(
                {
                    "holding_symbol": ticker,
                    "holding_name": clean_text(line.get("Name")),
                    "weight": weight,
                    "asset_class": kind,
                    "sector": clean_text(line.get("Sector")),
                    "shares": number(line.get("Quantity", line.get("Par Value"))),
                    "identifier": clean_text(line.get("CUSIP")) or clean_text(line.get("ISIN")),
                    "us_listed": ticker is not None
                    and kind == "Equity"
                    and line.get("Location") == _US
                    and line.get("Exchange") not in UNLISTED,
                    "filed": None,
                }
            )
        holdings = holdings_frame(rows)
        if holdings.empty:
            raise ValueError("no line of the file has a readable weight")
        notes = {"unreadable_lines": len(rows) - len(holdings)}
        published = published_sum(lines, column)
        if published is not None:
            notes["published_weight_bp"] = round(published * 10_000)
        return Normalized(as_of, {}, notes=notes, parsed={"holdings": holdings})
