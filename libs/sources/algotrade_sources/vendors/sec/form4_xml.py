"""SEC Form 4 (and 4/A) ownership XML as insider transactions: one filing's XML -> a row per
transaction line and reporting owner (EB D6, ADR 0050's free SEC family; no key).

``https://www.sec.gov/Archives/edgar/data/<cik>/<accession-no-dashes>/<document>``: the
``primaryDocument`` of the submissions JSON names an ``xsl...`` rendering of the form
(``xslF345X05/wk-form4_1.xml`` is HTML); the raw XML is the same file name without that
directory (``raw_document``). The XML carries what the form says (issuer CIK and ticker, the
reporting owners and their relationship, each transaction's date, code, shares, price, shares
owned after, direct or indirect) but neither the filing date nor the acceptance time: both come
from the submissions JSON (``submissions.py``), which the task joins by accession.

``normalize`` returns ``parsed["insider"]`` (``series.INSIDER_COLUMNS``), ``filing_date`` null.
A line is a ``nonDerivativeTransaction`` or a ``derivativeTransaction`` (holdings are not
transactions); ``derivative`` says which. ``shares`` / ``price`` / ``shares_after`` are the
filing's own numbers ("as filed": a typo stays); null when the filing leaves them out.
``plan_10b5_1`` is the ``aff10b5One`` checkbox where the filing has one, else null. A document
with a DTD or entities is refused (a Form 4 has none; entity expansion is an attack).

``build_frame`` is the one place a filing's three parts (the filing, its owners, its lines)
become the frame; the bulk reader (``form345_bulk.py``) uses it too, so both sources give the
same rows. ``line`` numbers a filing's lines by content (derivative flag, date, code, side,
shares, price, shares after, ownership), so the same filing read from either source has the
same keys whatever order its lines came in. Same pacing, ``User-Agent`` and 404 rule as the
other SEC sources (``[sec_edgar]``).
"""

import re
import xml.etree.ElementTree as ET
from typing import Any

import pandas as pd

from algotrade.core.model.instruments import pad_cik
from algotrade_sources.framework.base import FetchRequest, Normalized
from algotrade_sources.framework.http import Http
from algotrade_sources.framework.series import (
    INSIDER_COLUMNS,
    INSIDER_FRAME,
    INSIDER_LINE_COLUMNS,
    InsiderRequest,
)

SOURCE = "sec_edgar"
DATASET = "form4_xml"
DOCUMENT_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"
_TABLES = (  # (table, transaction element, derivative)
    ("nonDerivativeTable", "nonDerivativeTransaction", False),
    ("derivativeTable", "derivativeTransaction", True),
)
LINE_ORDER = list(INSIDER_LINE_COLUMNS)
_TRUE = {"1", "true", "y", "yes"}
_FALSE = {"0", "false", "n", "no"}


def raw_document(primary_document: str) -> str:
    """The file name of the raw XML from a submissions ``primaryDocument`` (an ``xsl`` directory
    holds the HTML rendering of the same file)."""
    name = primary_document.rsplit("/", 1)[-1]
    if not re.fullmatch(r"[\w.-]+\.xml", name):
        raise ValueError(f"not an XML document name: {primary_document!r}")
    return name


def document_url(cik: str, accession: str, document: str) -> str:
    """The URL of one filing's XML (``cik`` without leading zeros, the accession without dashes)."""
    padded = pad_cik(cik)
    if padded is None or not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession):
        raise ValueError(f"not a CIK / accession: {cik!r} {accession!r}")
    return DOCUMENT_URL.format(
        cik=int(padded), accession=accession.replace("-", ""), document=raw_document(document)
    )


def number(text: object) -> float:
    """A filed number as a float; ``NaN`` when empty or not a number."""
    try:
        return float(str(text).replace(",", "").strip())
    except ValueError:
        return float("nan")


def flag(text: object) -> bool | None:
    """A filed checkbox (``1`` / ``true`` ...) as a bool, ``None`` when absent or unclear."""
    word = str(text if text is not None else "").strip().lower()
    return True if word in _TRUE else False if word in _FALSE else None


def build_frame(filings: pd.DataFrame, owners: pd.DataFrame, lines: pd.DataFrame) -> pd.DataFrame:
    """``INSIDER_COLUMNS`` rows: each line of an accession with each of its owners.

    ``filings``: accession, form, issuer_cik, issuer_symbol, filing_date, period_of_report,
    amends_date, plan_10b5_1; ``owners``: accession, owner_cik, owner_name, is_director, is_officer,
    is_ten_pct_owner, is_other, officer_title; ``lines``: accession and ``LINE_ORDER``. A line
    of an accession with no filing or no owner row is dropped (nothing says whose it is)."""
    ordered = lines.sort_values(LINE_ORDER, kind="stable", na_position="last")
    ordered = ordered.assign(line=ordered.groupby("accession").cumcount() + 1)
    count = owners.groupby("accession")["owner_cik"].transform("size")
    both = ordered.merge(owners.assign(owner_count=count), on="accession")
    out = both.merge(filings, on="accession")
    for column in INSIDER_COLUMNS:
        if column not in out.columns:
            out[column] = None
    return (
        out[list(INSIDER_COLUMNS)]
        .sort_values(["accession", "line", "owner_cik"])
        .reset_index(drop=True)
    )


def _text(node: ET.Element | None, path: str) -> str | None:
    """The text of ``path`` under ``node`` (inside its ``<value>`` wrapper when it has one)."""
    found = node.find(path) if node is not None else None
    if found is None:
        return None
    inner = found.find("value")
    text = (inner if inner is not None else found).text
    return text.strip() if text and text.strip() else None


def _day(text: str | None) -> Any:
    """A filed date (``2019-05-07``, possibly with a zone suffix) as a Timestamp (NaT if none)."""
    return pd.Timestamp(text[:10]) if text else pd.NaT


def _line(node: ET.Element, derivative: bool) -> dict[str, Any]:
    return {
        "derivative": derivative,
        "transaction_date": _day(_text(node, "transactionDate")),
        "transaction_code": _text(node, "transactionCoding/transactionCode"),
        "acquired_disposed": _text(node, "transactionAmounts/transactionAcquiredDisposedCode"),
        "shares": number(_text(node, "transactionAmounts/transactionShares")),
        "price": number(_text(node, "transactionAmounts/transactionPricePerShare")),
        "shares_after": number(
            _text(node, "postTransactionAmounts/sharesOwnedFollowingTransaction")
        ),
        "direct_indirect": _text(node, "ownershipNature/directOrIndirectOwnership"),
    }


def _owner(node: ET.Element) -> dict[str, Any]:
    relation = node.find("reportingOwnerRelationship")
    return {
        "owner_cik": pad_cik(_text(node, "reportingOwnerId/rptOwnerCik")),
        "owner_name": _text(node, "reportingOwnerId/rptOwnerName"),
        "is_director": flag(_text(relation, "isDirector")) is True,
        "is_officer": flag(_text(relation, "isOfficer")) is True,
        "is_ten_pct_owner": flag(_text(relation, "isTenPercentOwner")) is True,
        "is_other": flag(_text(relation, "isOther")) is True,
        "officer_title": _text(relation, "officerTitle"),
    }


def parse_form4(payload: bytes, accession: str) -> pd.DataFrame:
    """One filing's XML -> ``INSIDER_COLUMNS`` rows (module doc); empty for a filing with no
    transaction lines (a holdings-only form)."""
    if re.search(rb"<!(DOCTYPE|ENTITY)", payload, re.IGNORECASE):
        raise ValueError("ownership XML with a DTD or entity")
    root = ET.fromstring(payload)
    if root.tag != "ownershipDocument":
        raise ValueError(f"not an ownership document: <{root.tag}>")
    issuer = root.find("issuer")
    filing = {
        "accession": accession,
        "form": _text(root, "documentType"),
        "issuer_cik": pad_cik(_text(issuer, "issuerCik")),
        "issuer_symbol": _text(issuer, "issuerTradingSymbol"),
        "filing_date": pd.NaT,
        "period_of_report": _day(_text(root, "periodOfReport")),
        "amends_date": _day(_text(root, "dateOfOriginalSubmission")),
        "plan_10b5_1": flag(_text(root, "aff10b5One")),
    }
    owners = [{"accession": accession, **_owner(o)} for o in root.findall("reportingOwner")]
    lines = [
        {"accession": accession, **_line(tx, derivative)}
        for table, element, derivative in _TABLES
        for tx in root.findall(f"{table}/{element}")
    ]
    if not owners or filing["issuer_cik"] is None:
        raise ValueError("ownership XML without an issuer CIK or a reporting owner")
    columns = ["accession", *LINE_ORDER]
    return build_frame(
        pd.DataFrame([filing]),
        pd.DataFrame(owners),
        pd.DataFrame(lines, columns=columns) if lines else pd.DataFrame(columns=columns),
    )


def insider_request(request: FetchRequest) -> InsiderRequest:
    """``request`` as an ``InsiderRequest`` (this source takes no other kind)."""
    if not isinstance(request, InsiderRequest):
        raise TypeError(f"Form 4 XML needs an InsiderRequest, got {type(request).__name__}")
    return request


class SecForm4Xml:
    """Implements ``sources.base.Source``. Request: an ``InsiderRequest`` (``key`` = the
    accession, ``cik`` the issuer's, ``document`` the ``primaryDocument``)."""

    name = SOURCE
    dataset = DATASET

    def __init__(self, http: Http) -> None:
        self._http = http  # paced by the shared ``sec`` limiter; sets the User-Agent itself

    def fetch(self, request: FetchRequest) -> bytes | None:
        asked = insider_request(request)
        return self._http.get(document_url(asked.cik, asked.key, asked.document))

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        frame = parse_form4(payload, insider_request(request).key)
        return Normalized(session_date=None, tables={}, parsed={INSIDER_FRAME: frame})
