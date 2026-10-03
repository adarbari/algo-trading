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
