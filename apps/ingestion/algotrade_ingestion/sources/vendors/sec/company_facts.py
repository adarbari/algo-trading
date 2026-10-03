"""SEC EDGAR company facts: share counts per CIK from XBRL filings (free, no key).

``https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json`` holds every
non-dimensional XBRL fact a company has filed (MBs for a large filer). We keep only two:

- ``dei:EntityCommonStockSharesOutstanding`` (``dei``): the cover-page count as of a date
  shortly before the filing. A filing that reports several values for the same date (one
  per class, without the class labels: companyfacts drops dimensions) is summed to the
  company total, with ``class_values`` saying how many were summed.
- ``us-gaap:WeightedAverageNumberOfSharesOutstandingBasic`` (``weighted_basic``): the
  fallback for filers that stopped tagging the cover page (most multi-class issuers, e.g.
  Alphabet). Each filing reports several periods (quarter, year to date, prior-year
  comparatives); we keep its current period: the latest ``end``, then the shortest span.

Every row keeps ``filed`` (the point-in-time date), ``period_end``, ``form`` and ``accn``.
Amendments (10-K/A) are separate rows with a later ``filed``. Non-positive counts are
dropped. A 404 means the CIK has no XBRL facts (common for funds).

Requests share the ``sec`` limiter and the contact ``User-Agent`` with the other SEC
sources (``sources/framework/registry.py``; ``[sec_edgar]`` in ``sources.toml``).
"""

import json
from typing import Any

import pandas as pd

from algotrade.core.model.instruments import pad_cik
from algotrade_ingestion.sources.framework.base import FetchRequest, Normalized
from algotrade_ingestion.sources.framework.http import Http

SOURCE = "sec_edgar"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
CONCEPTS = {  # our short name -> (taxonomy, XBRL concept)
    "dei": ("dei", "EntityCommonStockSharesOutstanding"),
    "weighted_basic": ("us-gaap", "WeightedAverageNumberOfSharesOutstandingBasic"),
}
SHARE_COLUMNS = (
    "cik",
    "concept",
    "tag",
    "period_start",
    "period_end",
    "filed",
    "form",
    "accn",
    "fy",
    "fp",
    "shares",
    "class_values",
)


def _facts(doc: dict[str, Any], concept: str) -> pd.DataFrame:
    taxonomy, name = CONCEPTS[concept]
    entry = (doc.get("facts") or {}).get(taxonomy, {}).get(name) or {}
    rows = (entry.get("units") or {}).get("shares") or []
    frame = pd.DataFrame(rows, columns=["start", "end", "val", "accn", "fy", "fp", "form", "filed"])
    frame = frame.dropna(subset=["end", "val", "accn", "filed"])
    frame = frame[pd.to_numeric(frame["val"], errors="coerce") > 0]
    return frame.assign(concept=concept, tag=f"{taxonomy}:{name}", val=frame["val"].astype(float))


def _cover(frame: pd.DataFrame) -> pd.DataFrame:
    """One ``dei`` row per (filing, date): several values are classes, summed."""
    keys = ["accn", "end"]
    first = frame.drop_duplicates(keys).set_index(keys)
    grouped = frame.groupby(keys)["val"]
    first["val"] = grouped.sum()
    first["class_values"] = grouped.size()
    return first.reset_index()


def _current_period(frame: pd.DataFrame) -> pd.DataFrame:
    """One ``weighted_basic`` row per filing: its latest period end, then the shortest span."""
    ordered = frame.assign(start=frame["start"].fillna(frame["end"]))
    ordered = ordered.sort_values(["accn", "end", "start"], kind="stable")
    return ordered.drop_duplicates("accn", keep="last").assign(class_values=1)


def parse_company_facts(payload: bytes) -> pd.DataFrame:
    """A companyfacts document -> share-count rows (``SHARE_COLUMNS``), sorted by
    (concept, filed, period_end)."""
    doc = json.loads(payload)
    cik = pad_cik(doc.get("cik"))
    if cik is None:
        raise ValueError("companyfacts document has no CIK")
    parts = []
    for concept, reduce in (("dei", _cover), ("weighted_basic", _current_period)):
        frame = _facts(doc, concept)
        if not frame.empty:
            parts.append(reduce(frame))
    if not parts:
        return pd.DataFrame(columns=list(SHARE_COLUMNS))
    out = pd.concat(parts, ignore_index=True).rename(
        columns={"start": "period_start", "end": "period_end", "val": "shares"}
    )
    out = out.assign(cik=cik)
    out.loc[out["concept"] == "dei", "period_start"] = None
    out = out.sort_values(["concept", "filed", "period_end", "accn"], kind="stable")
    out = out.astype(object).where(out.notna(), None)
    return out[list(SHARE_COLUMNS)].reset_index(drop=True)


class SecCompanyFacts:
    """One company's share counts. Request key: a CIK (any form, padded to 10 digits)."""

    name = SOURCE
    dataset = "companyfacts"

    def __init__(self, http: Http) -> None:
        self._http = http

    def fetch(self, request: FetchRequest) -> bytes | None:
        cik = pad_cik(request.key)
        if cik is None:
            raise ValueError(f"not a CIK: {request.key!r}")
        return self._http.get(FACTS_URL.format(cik=cik))

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        return Normalized(
            session_date=None, tables={}, parsed={"shares": parse_company_facts(payload)}
        )
