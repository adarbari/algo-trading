"""``cash_flow@v1``: trailing-twelve-month operating cash flow and capital expenditure.

Inputs: ``instruments/statements`` rows of the concepts ``ocf`` and ``capex`` (every fact FILED
on or before the session, ADR 0067) and the session's ``price_stats@v2`` (it sets which
instruments get a row).

A 10-Q reports cash flow lines cumulatively from the start of the fiscal year (three, six and
nine months) and the 10-K the whole year, so a discrete quarter is the difference of two
year-to-date facts of one fiscal year and one tag (``ttm.discrete_quarters``; the first quarter
is the three-month figure itself), never across tags, and the two facts must have been filed
close together (one restatement generation). The TTM is the last four consecutive quarters,
else the latest fiscal year, as in ``financials@v2``. A period takes the first tag of its
concept's list that reports it (``statement_concepts``, best first).

``capex_ttm`` is the cash PAID for property, plant and equipment as the filer tags it
(PaymentsToAcquirePropertyPlantAndEquipment, else PaymentsToAcquireProductiveAssets): a
positive number, as stored; free cash flow is ``ocf_ttm - capex_ttm``. A filer that tags
neither (some asset-light and financial issuers) has none: null, never zero.

    ocf_ttm      net cash provided by operating activities (USD; negative when used)
    capex_ttm    cash paid for property, plant and equipment (USD, positive)
    cf_as_of     the period end of the first TTM present (operating cash flow, else capex)
    cf_status    OK / PARTIAL / NO_TTM / NO_FACTS / STALE
"""

from datetime import date

import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.statements.lines import (
    FIELDS,
    PRICE_STATS,
    STATEMENTS,
    StatementParams,
    day_date,
    lines,
    stale_before,
    tag_ranks,
    totals,
)
from algotrade.features.rollups.statements.ttm import Total

NAME = "cash_flow"
VERSION = 1
STATUSES = ("OK", "PARTIAL", "NO_TTM", "NO_FACTS", "STALE")
# The same lists as ``statement_concepts.py``, best first (a test compares them).
CONCEPT_TAGS = {
    "ocf": (
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ),
    "capex": ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"),
}
RANKS = tag_ranks(CONCEPT_TAGS)
COLUMN_OF = {"ocf": "ocf_ttm", "capex": "capex_ttm"}
NON_NEGATIVE = ("capex",)  # a payment: a derived quarter below zero is a restatement mismatch

_WHY = (
    "no cash flow line filed by the session (ETFs, funds, no CIK, issuers that report outside "
    "USD): NO_FACTS; or no TTM can be formed (neither four consecutive quarters nor a fiscal "
    "year of this line): NO_TTM"
)
_UNTAGGED = "; or the filer does not report this line under any of its tags (never zero)"

FEATURES = (
    Feature(
        "ocf_ttm", "float", "usd",
        "Net cash provided by operating activities over the trailing twelve months: the last "
        "four quarters, each the difference of two year-to-date figures of one fiscal year and "
        "one tag (a 10-Q is cumulative), else the latest fiscal year; negative when operations "
        "used cash",
        _WHY + _UNTAGGED, valid_range=(None, None), inputs=FIELDS,
    ),
    Feature(
        "capex_ttm", "float", "usd",
        "Cash paid for property, plant and equipment over the trailing twelve months, as a "
        "positive number (the payment as filed, not a negative cash flow): free cash flow is "
        "ocf_ttm minus capex_ttm",
        _WHY + _UNTAGGED, valid_range=(0, None), inputs=FIELDS,
    ),
    Feature(
        "cf_as_of", "date", "date",
        "The period end of the first TTM present (operating cash flow, else capex): the last "
        "quarter, or the fiscal year end of an annual one",
        _WHY, inputs=("instruments/statements.period_end",),
    ),
    Feature(
        "cf_status", "str", "category",
        "OK (both lines have a TTM ending on the same period); PARTIAL (one, or two ending on "
        "different periods); NO_TTM (facts filed, but no TTM); NO_FACTS (no fact filed); STALE "
        "(the first TTM "
        "present ended more than stale_days, 480, before the session; values still shown)",
        "never", "label", categories=STATUSES, inputs=("instruments/statements.concept",),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def _row(found: dict[str, Total], before: int, has_facts: bool) -> dict[str, object]:
    if not has_facts:
        return {"cf_status": "NO_FACTS"}
    if not found:
        return {"cf_status": "NO_TTM"}
    first = next(found[c] for c in COLUMN_OF if c in found)
    same = len(found) == len(COLUMN_OF) and len({t[1] for t in found.values()}) == 1
    complete = "OK" if same else "PARTIAL"  # OK only when both lines end on one period
    status = "STALE" if first[1] < before else complete
    row: dict[str, object] = {COLUMN_OF[c]: t[0] for c, t in found.items()}
    return {**row, "cf_as_of": day_date(first[1]), "cf_status": status}


def compute(inputs: Inputs, session: date, p: StatementParams) -> pd.DataFrame:
    stats = inputs[PRICE_STATS]
    assert stats is not None  # required input
    today = stats[stats["session_date"] == session]["instrument_id"].astype(str)
    by_instrument = lines(inputs.get(STATEMENTS), RANKS, session, p)
    before = stale_before(session, p)
    ids = sorted(set(today) | set(by_instrument))
    rows = [
        _row(totals(by_instrument.get(i, {}), NON_NEGATIVE), before, bool(by_instrument.get(i)))
        for i in ids
    ]
    return pd.DataFrame(rows).assign(instrument_id=ids)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Trailing-twelve-month operating cash flow and capital expenditure (cash paid, positive) "
    "from the SEC statements, quarters derived from the cumulative 10-Q figures, point in time "
    "by filing date",
    (Input(PRICE_STATS), Input(STATEMENTS, required=False)),
    FEATURES,
    compute,
    StatementParams(),
)
