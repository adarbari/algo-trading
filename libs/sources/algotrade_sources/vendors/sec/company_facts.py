"""SEC EDGAR company facts: share counts and basic financials per CIK from XBRL filings
(free, no key).

``https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json`` holds every
non-dimensional XBRL fact a company has filed (MBs for a large filer). We keep two share
counts:

- ``dei:EntityCommonStockSharesOutstanding`` (``dei``): the cover-page count as of a date
  shortly before the filing. A filing that reports several values for the same date (one
  per class, without the class labels: companyfacts drops dimensions) is summed to the
  company total, with ``class_values`` saying how many were summed.
- ``us-gaap:WeightedAverageNumberOfSharesOutstandingBasic`` (``weighted_basic``): the
  fallback for filers that stopped tagging the cover page (most multi-class issuers, e.g.
  Alphabet). Each filing reports several periods (quarter, year to date, prior-year
  comparatives); we keep its current period: the latest ``end``, then the shortest span.

and three flows (``FLOWS``), the inputs of ``financials@v1``:

- ``revenue`` (``us-gaap:Revenues``, else ``RevenueFromContractWithCustomerExcludingAssessedTax``,
  else ``SalesRevenueNet``; the best-ranked tag that has the period wins, per period),
  ``net_income`` (``NetIncomeLoss``) in USD, and ``eps_diluted``
  (``EarningsPerShareDiluted``) in USD per share, in ``value`` with ``unit``;
- only periodic filings (10-K, 10-Q, 20-F, 40-F and their amendments) and only periods of a
  quarter, half year, nine months or a year (``SPAN_DAYS``): the year-to-date facts are how
  the fourth quarter is derived (annual minus nine months);
- a period is reported again as a comparative in later filings: we keep the filing that
  first reported it and any later filing whose value differs (a restatement), so a
  point-in-time read sees exactly the values that were public at each date, without the
  repeats.

Every row keeps ``filed`` (the point-in-time date), ``period_end``, ``form`` and ``accn``.
Amendments (10-K/A) are separate rows with a later ``filed``. Non-positive share counts are
dropped (losses and negative EPS are kept). A 404 means the CIK has no XBRL facts (common
for funds).

Requests share the ``sec`` limiter and the contact ``User-Agent`` with the other SEC
sources (``sources/framework/registry.py``; ``[sec_edgar]`` in ``sources.toml``).
"""

import json
from typing import Any

import pandas as pd

from algotrade.core.model.instruments import pad_cik
from algotrade_sources.framework.base import FetchRequest, Normalized
from algotrade_sources.framework.http import Http

SOURCE = "sec_edgar"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
CONCEPTS = {  # our short name -> (taxonomy, XBRL concept)
    "dei": ("dei", "EntityCommonStockSharesOutstanding"),
    "weighted_basic": ("us-gaap", "WeightedAverageNumberOfSharesOutstandingBasic"),
}
FLOWS = {  # short name -> (unit key in the document, our unit, us-gaap tags best first)
    "revenue": (
        "USD",
        "usd",
        ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"),
    ),
    "net_income": ("USD", "usd", ("NetIncomeLoss",)),
    "eps_diluted": ("USD/shares", "usd_per_share", ("EarningsPerShareDiluted",)),
}
PERIODIC_FORMS = ("10-K", "10-Q", "20-F", "40-F")  # prefixes: 10-K/A, 10-KT, 10-Q/A ...
# Days from period start to end of a quarter, half year, nine months and a year (52 / 53-week
# fiscal years included).
SPAN_DAYS = ((75, 105), (160, 200), (250, 290), (340, 380))
FACT_COLUMNS = (
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
    "value",
    "unit",
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


def _flow_facts(doc: dict[str, Any], concept: str) -> pd.DataFrame:
    """One flow's periodic facts: the best-ranked tag per period, first filing and
    restatements only (see the module docstring)."""
    unit_key, unit, tags = FLOWS[concept]
    taxonomy = (doc.get("facts") or {}).get("us-gaap", {})
    parts = []
    for rank, tag in enumerate(tags):
        rows = ((taxonomy.get(tag) or {}).get("units") or {}).get(unit_key) or []
        if rows:
            parts.append(pd.DataFrame(rows).assign(tag=f"us-gaap:{tag}", rank=rank))
    columns = ["start", "end", "val", "accn", "fy", "fp", "form", "filed", "tag", "rank"]
    frame = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=columns)
    frame = frame.reindex(columns=columns).dropna(subset=["start", "end", "val", "accn", "filed"])
    frame = frame[frame["form"].astype(str).str.startswith(PERIODIC_FORMS)]
    span = (pd.to_datetime(frame["end"]) - pd.to_datetime(frame["start"])).dt.days
    frame = frame[pd.concat([span.between(lo, hi) for lo, hi in SPAN_DAYS], axis=1).any(axis=1)]
    period = ["start", "end"]
    frame = frame[frame["rank"] == frame.groupby(period)["rank"].transform("min")]
    frame = frame.sort_values([*period, "filed", "accn"], kind="stable")
    frame = frame[frame["val"].ne(frame.groupby(period)["val"].shift())]
    return frame.assign(concept=concept, unit=unit, val=frame["val"].astype(float), class_values=1)


def parse_company_facts(payload: bytes) -> pd.DataFrame:
    """A companyfacts document -> fact rows (``FACT_COLUMNS``), sorted by
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
    parts += [flow for c in FLOWS if not (flow := _flow_facts(doc, c)).empty]
    if not parts:
        return pd.DataFrame(columns=list(FACT_COLUMNS))
    out = pd.concat(parts, ignore_index=True).rename(
        columns={"start": "period_start", "end": "period_end", "val": "value"}
    )
    out = out.assign(cik=cik)
    counts = out["concept"].isin(["dei", "weighted_basic"])
    out["shares"] = out["value"].where(counts)  # a share count is `shares`, a flow is `value`
    out["value"] = out["value"].where(~counts)
    out.loc[out["concept"] == "dei", "period_start"] = None
    out = out.sort_values(["concept", "filed", "period_end", "accn"], kind="stable")
    out = out.astype(object).where(out.notna(), None)
    return out.reindex(columns=list(FACT_COLUMNS)).reset_index(drop=True)


class SecCompanyFacts:
    """One company's share counts and financials. Request key: a CIK (any form, padded to 10
    digits)."""

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
