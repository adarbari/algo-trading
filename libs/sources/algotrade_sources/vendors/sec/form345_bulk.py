"""SEC Insider Transactions Data Sets as insider transactions: one quarterly bulk file -> a row
per Form 4 / 4/A transaction line and reporting owner (EB D6; free, no key; the history, from
2006).

``https://www.sec.gov/files/dera/data/insider-transactions-data-sets/<YYYY>q<N>_form345.zip``
holds the quarter's ownership filings, flattened "as filed", as tab-separated tables
(readme: ``insider_transactions_readme.pdf``): ``SUBMISSION`` (accession, ``FILING_DATE``,
``PERIOD_OF_REPORT``, ``DATE_OF_ORIG_SUB``, ``DOCUMENT_TYPE``, issuer CIK and ticker; newer
files add ``AFF10B5ONE``), ``REPORTINGOWNER`` (owner CIK, ``RPTOWNER_RELATIONSHIP`` such as
``DIRECTOR`` / ``OFFICER``, title), ``NONDERIV_TRANS`` and ``DERIV_TRANS`` (one line each:
``TRANS_DATE``, ``TRANS_CODE``, ``TRANS_SHARES``, ``TRANS_PRICEPERSHARE``,
``TRANS_ACQUIRED_DISP_CD``, ``SHRS_OWND_FOLWNG_TRANS``, ``DIRECT_INDIRECT_OWNERSHIP``). Dates are
``DD-MON-YYYY``. The sets carry the FILING DATE only, never the acceptance time, so a row from
here is stamped by the task from the submissions JSON of its issuer (``submissions.py``, joined
by accession): this reader says what the filing contained, not when it became known. A filing
accepted after 17:30 New York time on a quarter's last business day lands in the next file; a
quarter's file is published some weeks after its end (a missing file is ``None``: not yet).

``normalize`` returns ``parsed["insider"]`` (``series.INSIDER_COLUMNS``) for the quarter's
Form 4 and 4/A filings (Forms 3 and 5 are left out), built by ``form4_xml.build_frame`` like a
filing's XML. Same pacing, ``User-Agent`` and 404 rule as the other SEC sources
(``[sec_edgar]``).
"""

import csv
import io
import re
import zipfile

import pandas as pd

from algotrade.core.model.instruments import pad_cik
from algotrade_sources.framework.base import FetchRequest, Normalized
from algotrade_sources.framework.http import Http
from algotrade_sources.framework.series import INSIDER_FORMS, INSIDER_FRAME
from algotrade_sources.vendors.sec.form4_xml import LINE_ORDER, build_frame, flag, insider_request

SOURCE = "sec_edgar"
DATASET = "form345_bulk"
ZIP_URL = "https://www.sec.gov/files/dera/data/insider-transactions-data-sets/{year}q{quarter}_form345.zip"
QUARTER = re.compile(r"(?P<year>20\d{2})q(?P<quarter>[1-4])")
OPTIONAL = {"AFF10B5ONE"}  # newer files only
MAX_TABLE_BYTES = 2 * 1024**3  # a table of a quarter is tens of megabytes
LINE_COLUMNS = {  # our column -> the table's (the same names in both transaction tables)
    "transaction_date": "TRANS_DATE",
    "transaction_code": "TRANS_CODE",
    "shares": "TRANS_SHARES",
    "price": "TRANS_PRICEPERSHARE",
    "acquired_disposed": "TRANS_ACQUIRED_DISP_CD",
    "shares_after": "SHRS_OWND_FOLWNG_TRANS",
    "direct_indirect": "DIRECT_INDIRECT_OWNERSHIP",
}
SUBMISSION_COLUMNS = (
    "ACCESSION_NUMBER",
    "FILING_DATE",
    "PERIOD_OF_REPORT",
    "DATE_OF_ORIG_SUB",
    "DOCUMENT_TYPE",
    "ISSUERCIK",
    "ISSUERTRADINGSYMBOL",
    "AFF10B5ONE",
)
OWNER_COLUMNS = (
    "ACCESSION_NUMBER", "RPTOWNERCIK", "RPTOWNERNAME", "RPTOWNER_RELATIONSHIP", "RPTOWNER_TITLE",
)  # fmt: skip
TRANS_COLUMNS = ("ACCESSION_NUMBER", *LINE_COLUMNS.values())


def zip_url(label: str) -> str:
    """The URL of the file of one quarter (``2019q2``)."""
    match = QUARTER.fullmatch(label)
    if match is None:
        raise ValueError(f"not a quarter label: {label!r}")
    return ZIP_URL.format(year=match["year"], quarter=match["quarter"])


def _table(archive: zipfile.ZipFile, stem: str, columns: tuple[str, ...]) -> pd.DataFrame:
    """The ``columns`` present in the tab-separated table ``stem`` of the archive, all text."""
    members = {m.filename.rsplit("/", 1)[-1].upper(): m for m in archive.infolist()}
    member = members.get(f"{stem}.TSV") or members.get(f"{stem}.TXT")
    if member is None:
        raise ValueError(f"insider data set has no {stem} table")
    if member.file_size > MAX_TABLE_BYTES:
        raise ValueError(f"insider data set table {stem} is {member.file_size} bytes")
    with archive.open(member) as handle:
        frame = pd.read_csv(
            handle,
            sep="\t",
            dtype=str,
            quoting=csv.QUOTE_NONE,
            keep_default_na=False,
            usecols=lambda name: name in columns,
            encoding="utf-8",
            encoding_errors="replace",
        )
    missing = [c for c in columns if c not in frame.columns and c not in OPTIONAL]
    if missing:
        raise ValueError(f"insider data set table {stem} lacks columns {missing}")
    return frame


def _text(column: pd.Series) -> pd.Series:
    """The column with blank cells as ``None``."""
    return column.astype(object).where(column != "", None)


def _days(column: pd.Series) -> pd.Series:
    """``DD-MON-YYYY`` text as midnight Timestamps (``NaT`` for blank)."""
    return pd.to_datetime(_text(column), format="%d-%b-%Y", errors="coerce")


def _numbers(column: pd.Series) -> pd.Series:
    return pd.to_numeric(column.str.replace(",", ""), errors="coerce").astype("float64")


def _filings(table: pd.DataFrame) -> pd.DataFrame:
    table = table[table["DOCUMENT_TYPE"].isin(INSIDER_FORMS)]
    plan = (
        table["AFF10B5ONE"] if "AFF10B5ONE" in table.columns else pd.Series("", index=table.index)
    )
    return pd.DataFrame(
        {
            "accession": table["ACCESSION_NUMBER"],
            "form": table["DOCUMENT_TYPE"],
            "issuer_cik": table["ISSUERCIK"].map(pad_cik),
            "issuer_symbol": _text(table["ISSUERTRADINGSYMBOL"]),
            "filing_date": _days(table["FILING_DATE"]),
            "period_of_report": _days(table["PERIOD_OF_REPORT"]),
            "amends_date": _days(table["DATE_OF_ORIG_SUB"]),
            "plan_10b5_1": plan.map(flag).astype(object),
        }
    ).drop_duplicates("accession")


def _owners(table: pd.DataFrame, accessions: set[str]) -> pd.DataFrame:
    table = table[table["ACCESSION_NUMBER"].isin(accessions)]
    relation = table["RPTOWNER_RELATIONSHIP"].str.upper()
    return pd.DataFrame(
        {
            "accession": table["ACCESSION_NUMBER"],
            "owner_cik": table["RPTOWNERCIK"].map(pad_cik),
            "owner_name": _text(table["RPTOWNERNAME"].str.strip()),
            "is_director": relation.str.contains("DIRECTOR"),
            "is_officer": relation.str.contains("OFFICER"),
            "is_ten_pct_owner": relation.str.contains("TENPERCENT"),
            "is_other": relation.str.contains("OTHER"),
            "officer_title": _text(table["RPTOWNER_TITLE"]),
        }
    ).drop_duplicates(["accession", "owner_cik"])


def _lines(table: pd.DataFrame, accessions: set[str], derivative: bool) -> pd.DataFrame:
    table = table[table["ACCESSION_NUMBER"].isin(accessions)]
    out = pd.DataFrame(
        {
            "accession": table["ACCESSION_NUMBER"],
            "derivative": derivative,
            "transaction_date": _days(table["TRANS_DATE"]),
            "transaction_code": _text(table["TRANS_CODE"]),
            "acquired_disposed": _text(table["TRANS_ACQUIRED_DISP_CD"]),
            "shares": _numbers(table["TRANS_SHARES"]),
            "price": _numbers(table["TRANS_PRICEPERSHARE"]),
            "shares_after": _numbers(table["SHRS_OWND_FOLWNG_TRANS"]),
            "direct_indirect": _text(table["DIRECT_INDIRECT_OWNERSHIP"]),
        }
    )
    return out[["accession", *LINE_ORDER]]


def parse_bulk(payload: bytes) -> pd.DataFrame:
    """One quarter's zip -> ``INSIDER_COLUMNS`` rows of its Form 4 / 4/A filings (module doc)."""
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        filings = _filings(_table(archive, "SUBMISSION", SUBMISSION_COLUMNS))
        accessions = set(filings["accession"])
        owners = _owners(_table(archive, "REPORTINGOWNER", OWNER_COLUMNS), accessions)
        plain = _lines(_table(archive, "NONDERIV_TRANS", TRANS_COLUMNS), accessions, False)
        derived = _lines(_table(archive, "DERIV_TRANS", TRANS_COLUMNS), accessions, True)
    return build_frame(filings, owners, pd.concat([plain, derived], ignore_index=True))


class SecForm345Bulk:
    """Implements ``sources.base.Source``. Request: an ``InsiderRequest`` (``key`` = the quarter,
    ``2019q2``)."""

    name = SOURCE
    dataset = DATASET

    def __init__(self, http: Http) -> None:
        self._http = http  # paced by the shared ``sec`` limiter; sets the User-Agent itself

    def fetch(self, request: FetchRequest) -> bytes | None:
        return self._http.get(zip_url(insider_request(request).key))

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        return Normalized(session_date=None, tables={}, parsed={INSIDER_FRAME: parse_bulk(payload)})
