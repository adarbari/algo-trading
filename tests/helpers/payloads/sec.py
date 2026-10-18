"""Hand-made payloads in the SEC EDGAR formats (shapes copied from real responses, trimmed)."""

import json
from collections.abc import Iterable


def tickers(rows: Iterable[tuple[int, str, str, str]]) -> bytes:
    """``company_tickers_exchange.json``. rows: (cik, name, ticker, exchange)."""
    return json.dumps(
        {"fields": ["cik", "name", "ticker", "exchange"], "data": [list(r) for r in rows]}
    ).encode()


def submissions(
    cik: int,
    name: str,
    sic: str = "3571",
    sic_description: str = "Electronic Computers",
    tickers: tuple[str, ...] = ("AAPL",),
    website: str = "",
    former: tuple[str, ...] = (),
) -> bytes:
    """``submissions/CIK##########.json`` with the fields we read plus some we ignore."""
    return json.dumps(
        {
            "cik": str(cik),
            "entityType": "operating" if sic else "other",
            "sic": sic,
            "sicDescription": sic_description,
            "ownerOrg": "06 Technology",
            "insiderTransactionForOwnerExists": 1,
            "name": name,
            "tickers": list(tickers),
            "exchanges": ["Nasdaq"] * len(tickers),
            "ein": "942404110",
            "description": "",
            "website": website,
            "investorWebsite": "",
            "category": "Large accelerated filer",
            "fiscalYearEnd": "0926",
            "stateOfIncorporation": "CA",
            "stateOfIncorporationDescription": "CA",
            "addresses": {"business": {"city": "CUPERTINO", "stateOrCountry": "CA"}},
            "phone": "(408) 996-1010",
            "flags": "",
            "formerNames": [
                {"name": f, "from": "1994-01-26T00:00:00.000Z", "to": "2007-01-04T00:00:00.000Z"}
                for f in former
            ],
            "filings": {"recent": {"accessionNumber": [], "form": []}, "files": []},
        }
    ).encode()


def search_page(hits: Iterable[tuple[str, str, str, str]], total: int | None = None) -> bytes:
    """One page of EDGAR full-text search (``efts``). hits: (adsh, cik, file_date, name); several
    hits of one accession are several documents of the filing."""
    rows = [
        {
            "_id": f"{adsh}:d.htm",
            "_source": {
                "adsh": adsh,
                "ciks": [cik],
                "display_names": [f"{name}  (CIK {cik})"],
                "file_date": filed,
                "form": "424B4",
            },
        }
        for adsh, cik, filed, name in hits
    ]
    count = len(rows) if total is None else total
    return json.dumps(
        {"hits": {"total": {"value": count, "relation": "eq"}, "hits": rows}}
    ).encode()


COVER = (
    "<html><body><p>PROSPECTUS</p><p>{shares} Shares</p><p>Class A Common Stock</p>"
    "<p>This is the initial public offering of our Class A common stock. Prior to this offering, "
    "there was no public market for our common stock. We have been approved to list our Class A "
    "common stock on the Nasdaq Global Select Market under the symbol &#8220;{ticker}&#8221;.</p>"
    "<table><tr><td></td><td>Per Share</td><td>Total</td></tr>"
    "<tr><td>Initial public offering price</td><td>$</td><td>{price}</td><td>$</td><td>360,000,000"
    "</td></tr></table><p>Prospectus dated {dated}</p>"
)
LOCKUP = (
    "<p>We, our directors, executive officers and holders of substantially all of our "
    "securities have agreed with the underwriters that, subject to certain exceptions, we and "
    "they will not, for a period of {term} after the date of this prospectus, sell any shares. "
    "Goldman Sachs may, in its sole discretion, release any of the securities subject to these "
    "lock-up agreements at any time.</p>"
)


def prospectus(
    ticker: str = "ABCD",
    price: str = "18.00",
    dated: str = "June 12, 2026",
    terms: tuple[str, ...] = ("180 days",),
    repeat: int = 3,
    extra: str = "",
) -> bytes:
    """A 424B4 main document: an IPO cover and the lock-up paragraph (``terms`` each stated
    ``repeat`` times, as a prospectus repeats it in every section)."""
    lock = "".join(LOCKUP.format(term=t) for t in terms for _ in range(repeat))
    cover = COVER.format(shares="20,000,000", ticker=ticker, price=price, dated=dated)
    return f"{cover}{lock}{extra}</body></html>".encode()
