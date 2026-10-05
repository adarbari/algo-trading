"""SEC Form N-PORT: the quarterly portfolio of every registered fund (``HoldingsSource``).

The only free source that covers funds whose issuer publishes no daily file (Vanguard, Invesco
QQQ, most smaller issuers). Registered funds file N-PORT-P with the SEC; the public part is the
quarter-end portfolio, available about 60 days after the quarter ends, so it is months old but
complete. It is a fallback: a fund an issuer's own daily file covers is read from there.

- Directory: ``company_tickers_mf.json`` maps a ticker to its trust (CIK) and series id.
- A trust files one N-PORT per series, and the filing list does not say which series a filing
  is for. The filing's header page (``<accession>-index-headers.html``, a few KB) does, so a
  fund's filing is found by reading headers newest first (cached for the run, so a trust's
  other funds cost nothing more).
- The portfolio is ``primary_doc.xml`` (0.1 to 4 MB). It names no tickers; each line has a
  name, CUSIP / ISIN, value and ``pctVal`` (percent of net assets), so holdings are linked to
  tickers by the task through CUSIPs other issuers published.
- Unit trusts (SPY, DIA) and commodity or crypto trusts do not file N-PORT.

SEC fair-access rules apply as for the other SEC sources (contact in the User-Agent, shared
``sec`` limiter).
"""

import io
import json
import re
from datetime import date, timedelta
from typing import Any
from xml.etree import ElementTree

from algotrade.core.model.instruments import pad_cik
from algotrade_sources.framework.base import FetchRequest, Normalized
from algotrade_sources.framework.holdings import (
    clean_text,
    fraction,
    funds_frame,
    holding_ticker,
    holdings_frame,
    number,
)
from algotrade_sources.framework.http import Http

SOURCE = "sec_nport"
DATASET = "nport_holdings"
DIRECTORY = "directory"
FUNDS_URL = "https://www.sec.gov/files/company_tickers_mf.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{folder}"
MAX_HEADERS_PER_TRUST = 400  # filings whose series we look up before giving up on a fund
FORM = "NPORT-P"
FILING_LAG_DAYS = 60  # N-PORT-P is due 60 days after the period it reports
_SERIES = re.compile(r"<SERIES-ID>(S\d{9})")
_ASSET = {
    "EC": "Equity",
    "EP": "Preferred",
    "DBT": "Fixed Income",
    "ABS-MBS": "Fixed Income",
    "ABS-O": "Fixed Income",
    "ABS-CBDO": "Fixed Income",
    "LON": "Loan",
    "STIV": "Cash",
    "RA": "Repo",
    "SN": "Structured Note",
    "DE": "Derivative",
    "DC": "Derivative",
    "DCO": "Derivative",
    "DFE": "Derivative",
    "DIR": "Derivative",
    "DO": "Derivative",
    "DCR": "Derivative",
    "DY": "Derivative",
    "DO-": "Derivative",
}


def parse_funds(payload: bytes) -> dict[str, tuple[str, str]]:
    """``company_tickers_mf.json`` -> ticker -> (CIK, series id)."""
    doc = json.loads(payload)
    fields = list(doc["fields"])
    out: dict[str, tuple[str, str]] = {}
    for values in doc["data"]:
        row = dict(zip(fields, values, strict=True))
        cik = pad_cik(row.get("cik"))
        if cik and row.get("symbol") and row.get("seriesId"):
            out[str(row["symbol"]).strip().upper()] = (cik, str(row["seriesId"]))
    return out


def parse_filings(payload: bytes) -> list[tuple[str, date]]:
    """A trust's submissions -> (accession number, filing date) of its N-PORT-P filings,
    newest first (the recent block only)."""
    recent = json.loads(payload)["filings"]["recent"]
    found = [
        (str(acc), date.fromisoformat(str(filed)))
        for form, acc, filed in zip(
            recent["form"], recent["accessionNumber"], recent["filingDate"], strict=True
        )
        if form == FORM
    ]
    return sorted(found, key=lambda f: (f[1], f[0]), reverse=True)


def _folder(accession: str) -> str:
    return accession.replace("-", "")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(element: ElementTree.Element, name: str) -> ElementTree.Element | None:
    return next((c for c in element if _local(c.tag) == name), None)


def _text(element: ElementTree.Element, name: str) -> str | None:
    child = _child(element, name)
    return clean_text(child.text) if child is not None and child.text else None


def _identifier(element: ElementTree.Element, name: str) -> str | None:
    child = _child(element, "identifiers")
    found = _child(child, name) if child is not None else None
    return clean_text(found.get("value")) if found is not None else None


def parse_report(payload: bytes) -> tuple[date | None, str | None, list[dict[str, Any]]]:
    """-> (the report date, the series id, one row per holding in ``holdings_frame`` terms)."""
    as_of: date | None = None
    series: str | None = None
    rows: list[dict[str, Any]] = []
    for _, element in ElementTree.iterparse(io.BytesIO(payload), events=("end",)):
        name = _local(element.tag)
        if name == "repPdDate" and element.text:
            as_of = date.fromisoformat(element.text.strip())
        elif name == "seriesId" and element.text and series is None:
            series = element.text.strip()
        elif name == "invstOrSec":
            rows.append(_holding(element))
            element.clear()
    return as_of, series, rows


def _holding(line: ElementTree.Element) -> dict[str, Any]:
    ticker = holding_ticker(_identifier(line, "ticker"))
    code = _text(line, "assetCat") or ""
    kind = _ASSET.get(code, code or None)
    cusip = _text(line, "cusip")
    cusip = None if cusip and set(cusip) == {"0"} else cusip
    return {
        "holding_symbol": ticker,
        "holding_name": _text(line, "name") or _text(line, "title"),
        "weight": fraction(_text(line, "pctVal")),
        "asset_class": kind,
        "sector": None,
        "shares": number(_text(line, "balance")) if _text(line, "units") == "NS" else None,
        "identifier": cusip or _identifier(line, "isin"),
        "us_listed": ticker is not None and kind == "Equity" and _text(line, "invCountry") == "US",
        "filed": None,
    }


class NportHoldings:
    """Implements ``base.HoldingsSource``. Request keys: ``directory``, or a fund ticker."""

    name = SOURCE
    dataset = DATASET
    directory_key = DIRECTORY
    scope_limited = True
    cadence_days = 90

    def __init__(self, http: Http) -> None:
        self._http = http
        self._funds: dict[str, tuple[str, str]] = {}
        self._filings: dict[str, list[tuple[str, date]]] = {}  # CIK -> its N-PORT-P filings
        self._series: dict[str, str] = {}  # accession -> series id (read from the header page)
        self._filed: dict[str, date] = {}  # series id -> filing date of the report fetched

    def fetch(self, request: FetchRequest) -> bytes | None:
        if request.key == DIRECTORY:
            payload = self._http.get(FUNDS_URL)
            if payload is not None:
                self._funds = parse_funds(payload)
            return payload
        if not self._funds:
            self.fetch(FetchRequest(DIRECTORY))
        found = self._funds.get(request.key.upper())
        if found is None:
            return None
        cik, series = found
        accession = self._accession(cik, series)
        if accession is None:
            return None
        url = ARCHIVE.format(cik=int(cik), folder=_folder(accession)) + "/primary_doc.xml"
        return self._http.get(url)

    def _accession(self, cik: str, series: str) -> str | None:
        """The newest N-PORT-P filing of ``series`` under trust ``cik``."""
        if cik not in self._filings:
            payload = self._http.get(SUBMISSIONS_URL.format(cik=cik))
            self._filings[cik] = [] if payload is None else parse_filings(payload)
        for accession, _ in self._filings[cik][:MAX_HEADERS_PER_TRUST]:
            if accession not in self._series:
                header = self._http.get(
                    ARCHIVE.format(cik=int(cik), folder=_folder(accession))
                    + f"/{accession}-index-headers.html"
                )
                match = _SERIES.search((header or b"").decode("utf-8", errors="replace"))
                self._series[accession] = match.group(1) if match else ""
            if self._series[accession] == series:
                self._filed[series] = dict(self._filings[cik])[accession]
                return accession
        return None

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        if request.key == DIRECTORY:
            funds = funds_frame((t, series) for t, (_, series) in parse_funds(payload).items())
            return Normalized(None, {}, parsed={"funds": funds})
        as_of, series, rows = parse_report(payload)
        if not rows or as_of is None:
            return None
        # The report is public from its filing date (months after the period). A replay from
        # raw has no filing list, so it assumes the filing deadline, 60 days after the period.
        filed = self._filed.get(series or "") or as_of + timedelta(days=FILING_LAG_DAYS)
        holdings = holdings_frame(rows).assign(filed=filed)
        if holdings.empty:
            return None
        notes = {"unreadable_lines": len(rows) - len(holdings)}
        return Normalized(as_of, {}, notes=notes, parsed={"holdings": holdings})
