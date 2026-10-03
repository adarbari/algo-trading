"""SEC EDGAR: company identity and classification per CIK (free, no key).

- ``https://www.sec.gov/files/company_tickers_exchange.json``: every SEC-registered ticker
  with its CIK, name and exchange (one request). Used when the reference has no CIK.
- ``https://data.sec.gov/submissions/CIK##########.json``: one company: name, SIC code and
  description, state of incorporation, fiscal year end, website, former names, exchanges.

SEC fair-access policy: a ``User-Agent`` naming the requester with a contact email (built by
``user_agent`` from ``ALGOTRADE_SEC_CONTACT``; never stored, logged or committed) and at most
10 requests/second. Every request waits on the shared ``sec`` limiter (``[sec_edgar]
min_interval_s``, 0.2 s). A 404 on
submissions means "no filings for this CIK" (``None``); 403 is an error (we may be blocked).
"""

import json
import re
from typing import Any

import pandas as pd

from algotrade.core.model.fields import COMPANY_COLUMNS
from algotrade.core.model.instruments import pad_cik
from algotrade_ingestion.sources.framework.base import FetchRequest, Normalized
from algotrade_ingestion.sources.framework.http import Http
from algotrade_ingestion.sources.vendors.sec.sic import sic_division, sic_sector

SOURCE = "sec_edgar"
TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
TICKER_COLUMNS = ("cik", "sec_name", "symbol", "sec_exchange")
_PREFERRED = re.compile(r"^([A-Z]+)-P([A-Z]+)$")  # SEC "ABR-PD" == ACT "ABR$D"


def user_agent(contact: str) -> str:
    """The SEC-required identification: who we are plus a contact email."""
    return f"algotrade-ingestion/0.1 {contact}"


def act_symbol(ticker: str) -> str:
    """SEC ticker -> the universe's ACT style (``BRK-B`` -> ``BRK.B``, ``ABR-PD`` -> ``ABR$D``)."""
    upper = ticker.strip().upper()
    match = _PREFERRED.match(upper)
    return f"{match.group(1)}${match.group(2)}" if match else upper.replace("-", ".")


def parse_tickers(payload: bytes) -> pd.DataFrame:
    """``company_tickers_exchange.json`` -> one row per symbol (``TICKER_COLUMNS``)."""
    doc = json.loads(payload)
    fields = list(doc.get("fields") or [])
    rows = []
    for values in doc.get("data") or []:
        r = dict(zip(fields, values, strict=False))
        cik, ticker = pad_cik(r.get("cik")), str(r.get("ticker") or "")
        if cik is None or not ticker.strip():
            continue
        rows.append(
            {
                "cik": cik,
                "sec_name": r.get("name") or None,
                "symbol": act_symbol(ticker),
                "sec_exchange": r.get("exchange") or None,
            }
        )
    frame = pd.DataFrame(rows, columns=list(TICKER_COLUMNS))
    return frame.drop_duplicates("symbol", keep="first").reset_index(drop=True)


def _text(value: Any) -> str | None:
    text = " ".join(str(value or "").split())  # SEC labels carry stray double spaces
    return text or None


def _joined(values: Any) -> str | None:
    items = [str(v).strip() for v in values or [] if str(v or "").strip()]
    return "; ".join(dict.fromkeys(items)) or None


def parse_submissions(payload: bytes) -> pd.DataFrame:
    """One company's submissions document -> a one-row frame (``COMPANY_COLUMNS``)."""
    doc = json.loads(payload)
    cik = pad_cik(doc.get("cik"))
    if cik is None:
        raise ValueError("submissions document has no CIK")
    sic = _text(doc.get("sic"))
    description = _text(doc.get("sicDescription"))
    row = {
        "cik": cik,
        "name": _text(doc.get("name")),
        "entity_type": _text(doc.get("entityType")),
        "sic": sic,
        "sic_description": description,
        "sic_division": sic_division(sic),
        "sector": sic_sector(sic),
        "industry": description,
        "state_of_incorporation": _text(doc.get("stateOfIncorporation")),
        "fiscal_year_end": _text(doc.get("fiscalYearEnd")),  # MMDD, e.g. "0926"
        "website": _text(doc.get("website")),
        "former_names": _joined(f.get("name") for f in doc.get("formerNames") or []),
        "exchanges": _joined(doc.get("exchanges")),
        "tickers": _joined(doc.get("tickers")),
    }
    return pd.DataFrame([row], columns=list(COMPANY_COLUMNS))


class _Sec:
    name = SOURCE
    dataset = ""

    def __init__(self, http: Http) -> None:
        self._http = http

    def _get(self, url: str) -> bytes | None:
        return self._http.get(url)


class SecTickerMap(_Sec):
    """CIK <-> ticker <-> exchange for every SEC registrant. Request key: ``tickers``."""

    dataset = "company_tickers"

    def fetch(self, request: FetchRequest) -> bytes | None:
        return self._get(TICKERS_URL)

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        frame = parse_tickers(payload)
        if frame.empty:
            return None
        return Normalized(session_date=None, tables={}, parsed={"tickers": frame})


class SecSubmissions(_Sec):
    """One company's details. Request key: a CIK (any form, padded to 10 digits)."""

    dataset = "submissions"

    def fetch(self, request: FetchRequest) -> bytes | None:
        cik = pad_cik(request.key)
        if cik is None:
            raise ValueError(f"not a CIK: {request.key!r}")
        return self._get(SUBMISSIONS_URL.format(cik=cik))

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        return Normalized(
            session_date=None, tables={}, parsed={"company": parse_submissions(payload)}
        )
