"""Hand-made payloads in the SEC EDGAR formats (shapes copied from real responses, trimmed)."""

import io
import json
import zipfile
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


FORM345_TABLES = {
    "SUBMISSION": "ACCESSION_NUMBER FILING_DATE PERIOD_OF_REPORT DATE_OF_ORIG_SUB DOCUMENT_TYPE "
    "ISSUERCIK ISSUERNAME ISSUERTRADINGSYMBOL AFF10B5ONE",
    "REPORTINGOWNER": "ACCESSION_NUMBER RPTOWNERCIK RPTOWNERNAME RPTOWNER_RELATIONSHIP "
    "RPTOWNER_TITLE RPTOWNER_STREET1",
    "NONDERIV_TRANS": "ACCESSION_NUMBER NONDERIV_TRANS_SK SECURITY_TITLE TRANS_DATE TRANS_CODE "
    "TRANS_SHARES TRANS_PRICEPERSHARE TRANS_ACQUIRED_DISP_CD SHRS_OWND_FOLWNG_TRANS "
    "DIRECT_INDIRECT_OWNERSHIP",
    "DERIV_TRANS": "ACCESSION_NUMBER DERIV_TRANS_SK SECURITY_TITLE TRANS_DATE TRANS_CODE "
    "TRANS_SHARES TRANS_PRICEPERSHARE TRANS_ACQUIRED_DISP_CD SHRS_OWND_FOLWNG_TRANS "
    "DIRECT_INDIRECT_OWNERSHIP",
}


def form345_zip(rows: dict[str, list[dict[str, str]]]) -> bytes:
    """A quarterly Insider Transactions Data Set (zip of tab-separated tables, header first).
    rows: table name -> row dicts; a column a row leaves out is blank, one the tables do not
    declare is ignored."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for table, header in FORM345_TABLES.items():
            names = header.split()
            lines = ["\t".join(names)]
            lines += ["\t".join(row.get(name, "") for name in names) for row in rows.get(table, [])]
            archive.writestr(f"{table}.tsv", "\n".join(lines) + "\n")
    return buffer.getvalue()


ISSUER = {"ISSUERCIK": "0000999001", "ISSUERNAME": "Example Corp", "ISSUERTRADINGSYMBOL": "EXMP"}
OWNER = {
    "RPTOWNERCIK": "0000888001",
    "RPTOWNERNAME": " Doe Jane ",
    "RPTOWNER_RELATIONSHIP": "Director,Officer",
}


def example_quarter(amend: bool = True, price: str = "12.5") -> bytes:
    """A small quarter: a Form 4 with a purchase, a sale and an option exercise (EXMP), its 4/A,
    a Form 3 (left out), a Form 4 of an issuer nobody lists (ZZZZ) and a Form 4 of EXMP with no
    reporting owner row (dropped). ``amend=False`` leaves the 4/A out; ``price`` the purchase's."""
    first, amended, bare = "0000999001-26-000001", "0000999001-26-000002", "0000999001-26-000003"
    buy = {"TRANS_DATE": "28-SEP-2026", "TRANS_CODE": "P", "TRANS_SHARES": "1000",
           "TRANS_PRICEPERSHARE": price, "TRANS_ACQUIRED_DISP_CD": "A",
           "SHRS_OWND_FOLWNG_TRANS": "26000", "DIRECT_INDIRECT_OWNERSHIP": "D"}  # fmt: skip
    sale = {**buy, "TRANS_DATE": "29-SEP-2026", "TRANS_CODE": "S", "TRANS_SHARES": "200",
            "TRANS_PRICEPERSHARE": "13", "TRANS_ACQUIRED_DISP_CD": "D"}  # fmt: skip
    option = {**buy, "TRANS_CODE": "M", "TRANS_SHARES": "300", "TRANS_PRICEPERSHARE": "0",
              "TRANS_ACQUIRED_DISP_CD": "D"}  # fmt: skip
    filed = {"FILING_DATE": "30-SEP-2026", "PERIOD_OF_REPORT": "28-SEP-2026"}
    tables = {
        "SUBMISSION": [
            {"ACCESSION_NUMBER": first, "DOCUMENT_TYPE": "4", **filed, **ISSUER},
            {
                "ACCESSION_NUMBER": amended,
                "DOCUMENT_TYPE": "4/A",
                **filed,
                **ISSUER,
                "DATE_OF_ORIG_SUB": "30-SEP-2026",
                "AFF10B5ONE": "1",
            },
            {
                "ACCESSION_NUMBER": "0000999001-26-000009",
                "DOCUMENT_TYPE": "3",
                **filed,
                **ISSUER,
            },
            {
                "ACCESSION_NUMBER": "0000999002-26-000001",
                "DOCUMENT_TYPE": "4",
                **filed,
                **{**ISSUER, "ISSUERCIK": "0000999002", "ISSUERTRADINGSYMBOL": "ZZZZ"},
            },
            {"ACCESSION_NUMBER": bare, "DOCUMENT_TYPE": "4", **filed, **ISSUER},
        ],
        "REPORTINGOWNER": [
            {"ACCESSION_NUMBER": first, **OWNER, "RPTOWNER_TITLE": "Chief Financial Officer"},
            {"ACCESSION_NUMBER": amended, **OWNER, "RPTOWNER_TITLE": "Chief Financial Officer"},
            {"ACCESSION_NUMBER": "0000999002-26-000001", **OWNER},
        ],
        "NONDERIV_TRANS": [
            {"ACCESSION_NUMBER": first, "NONDERIV_TRANS_SK": "1", **buy},
            {"ACCESSION_NUMBER": first, "NONDERIV_TRANS_SK": "2", **sale},
            {"ACCESSION_NUMBER": amended, "NONDERIV_TRANS_SK": "1", **buy},
            {"ACCESSION_NUMBER": "0000999002-26-000001", "NONDERIV_TRANS_SK": "1", **buy},
            {"ACCESSION_NUMBER": bare, "NONDERIV_TRANS_SK": "1", **buy},
        ],
        "DERIV_TRANS": [{"ACCESSION_NUMBER": first, "DERIV_TRANS_SK": "1", **option}],
    }
    if not amend:
        tables = {
            name: [r for r in rows if r["ACCESSION_NUMBER"] != amended]
            for name, rows in tables.items()
        }
    return form345_zip(tables)


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
