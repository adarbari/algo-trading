"""``growth_history@v2``: the revenue and diluted EPS trailing twelve months three and five years
back, the bases of the multi-year growth rates (``revenue_cagr_3y`` and its siblings).

Inputs: ``instruments/shares`` rows of the concepts ``revenue`` and ``eps_diluted`` (the same
facts ``financials@v3`` reads, with a longer window: ``history_days``, about seven years), the
session's ``price_stats@v2`` (it sets which instruments get a row), ``events/split`` and nothing
else. Only facts FILED on or before the session are read (checked here, whatever the loader
passed): a restatement filed later never moves a session.

Each TTM is assembled as ``financials@v3``'s are (``ttm.trailing``). The newest TTM of the
concept sets the end the history is counted back from; the ago value is the four consecutive
quarters (else the fiscal year) whose last period ends within 40 days of that end minus three or
five years (``ttm.trailing_ago``). A hole in that history (a missing quarter, no fiscal year
there) is null, never a shorter sum. EPS is split-adjusted to the session exactly as in
``financials@v3`` (``prepare_facts``): a fact filed before a split that took effect on or before
the session is divided by its ratio, so the EPS then and now are per the same share count.

    revenue_ttm_3y_ago, revenue_ttm_5y_ago              the revenue TTM about 3 / 5 years back
    eps_diluted_ttm_3y_ago, eps_diluted_ttm_5y_ago      the diluted EPS TTM about 3 / 5 years back
    gh_status                                           OK / PARTIAL / NO_TTM / NO_FACTS / STALE
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.corporate.financials import (
    EPS,
    FACTS,
    PRICE_STATS,
    REVENUE,
    SPLITS,
    prepare_facts,
    split_lookback,
)
from algotrade.features.rollups.statements.lines import epoch_days, stale_before
from algotrade.features.rollups.statements.ttm import Fact, TtmParams, trailing, trailing_ago

NAME = "growth_history"
VERSION = 2
STATUSES = ("OK", "PARTIAL", "NO_TTM", "NO_FACTS", "STALE")
YEARS = (3, 5)
CONCEPTS = (REVENUE, EPS)
COLUMN_OF = {REVENUE: "revenue_ttm_{}y_ago", EPS: "eps_diluted_ttm_{}y_ago"}


@dataclass(frozen=True)
class GrowthParams(TtmParams):
    """``TtmParams`` with the longer window a five-year base needs (a TTM ending up to
    ``stale_days`` ago, five years back, the 40-day tolerance and the three gaps between four
    quarters: 480 + 1826 + 40 + 273 = 2619 days)."""

    history_days: int = 2700


_COLS = tuple(f"{FACTS}.{c}" for c in ("concept", "value", "period_start", "period_end", "filed"))
_WHY = (
    "no revenue or EPS fact filed by the session (ETFs, funds, no CIK, issuers that report "
    "outside USD): NO_FACTS; or no TTM now; or the history of that concept does not reach back "
    "{n} years (a company listed or reporting for less), or has a gap there (a missing quarter "
    "and no fiscal year ending near it)"
)


def _ago(name: str, kind: str, unit: str, what: str, years: int) -> Feature:
    split = kind != "float"
    return Feature(
        name, kind, unit,
        f"The {what} trailing twelve months about {years} years before the newest TTM (the "
        f"four consecutive quarters, else the fiscal year, ending within 40 days of that date"
        f"{'; split-adjusted to the session like eps_diluted_ttm' if split else ''}): the base "
        f"of {'eps' if split else 'revenue'}_cagr_{years}y",
        _WHY.format(n=years), valid_range=(None, None) if split else (0, None),
        inputs=(*_COLS, f"{SPLITS}.ratio") if split else _COLS,
    )  # fmt: skip


FEATURES = (
    *(_ago(f"revenue_ttm_{n}y_ago", "float", "usd", "revenue", n) for n in YEARS),
    *(
        _ago(f"eps_diluted_ttm_{n}y_ago", "float32", "usd_per_share", "diluted EPS", n)
        for n in YEARS
    ),
    Feature(
        "gh_status", "str", "category",
        "OK (the revenue and EPS TTMs end on the same period and all four values are known); "
        "PARTIAL (some are missing, or the two TTMs end on different periods); NO_TTM (facts, "
        "but no TTM can be formed); NO_FACTS (no "
        "revenue or EPS fact filed); STALE (the newest TTM ended more than stale_days, 480, "
        "before the session; values still shown, checked first)",
        "never", "label", categories=STATUSES, inputs=(f"{FACTS}.concept",),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def _row(facts: dict[str, list[Fact]], before: int) -> dict[str, object]:
    """One instrument's values: each concept's newest TTM, then its TTMs 3 and 5 years back."""
    now = {c: t[0] for c in CONCEPTS if c in facts and (t := trailing(facts[c], c == REVENUE))}
    row: dict[str, object] = {
        COLUMN_OF[c].format(n): trailing_ago(facts[c], now[c][1], n, c == REVENUE)
        for c in now
        for n in YEARS
    }
    if not now:
        return {"gh_status": "NO_TTM"}  # facts are filed, but neither concept has a TTM
    first = now.get(REVENUE) or now.get(EPS)
    if first is not None and first[1] < before:
        return {**row, "gh_status": "STALE"}  # first: an old filer's history is old too
    aligned = len(now) == len(CONCEPTS) and now[REVENUE][1] == now[EPS][1]
    complete = len([v for v in row.values() if v is not None]) == len(CONCEPTS) * len(YEARS)
    return {**row, "gh_status": "OK" if aligned and complete else "PARTIAL"}


def compute(inputs: Inputs, session: date, p: GrowthParams) -> pd.DataFrame:
    stats = inputs[PRICE_STATS]
    assert stats is not None  # required input
    today = stats[stats["session_date"] == session]["instrument_id"].astype(str)
    shares = inputs.get(FACTS)
    if shares is not None and not shares.empty and "filed" in shares.columns:
        known = epoch_days(shares["filed"]) <= (session - date(1970, 1, 1)).days
        shares = shares[shares["concept"].isin(CONCEPTS) & known]
    rows = prepare_facts(shares, inputs.get(SPLITS), session, p)
    by_instrument: dict[str, dict[str, list[Fact]]] = {}
    for iid, concept, start, end, value, filed, rank in zip(
        *(rows[c].tolist() for c in rows.columns), strict=True
    ):
        by_instrument.setdefault(iid, {}).setdefault(concept, []).append(
            (start, end, value, filed, rank)
        )
    before = stale_before(session, p)
    ids = sorted(set(today) | set(by_instrument))
    out = [
        _row(by_instrument[i], before) if i in by_instrument else {"gh_status": "NO_FACTS"}
        for i in ids
    ]
    return pd.DataFrame(out).assign(instrument_id=ids)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Revenue and diluted EPS trailing twelve months three and five years back (SEC company "
    "facts, point in time by filing date, EPS split-adjusted): the bases of the multi-year "
    "growth rates",
    (
        Input(PRICE_STATS),
        Input(FACTS, required=False),
        Input(SPLITS, lookback=split_lookback, required=False),
    ),
    FEATURES,
    compute,
    GrowthParams(),
)
