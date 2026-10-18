"""Reading statement lines for the statement groups (``income_statement@v2``, ``cash_flow@v2``).

Input: ``instruments/statements`` rows (ADR 0067), one per us-gaap tag, period and filing, of the
concepts a group asks for. Each (concept, tag, period) takes its latest value filed on or
before the session (a restatement replaces it from its filing date; a filing after the session
is never read, whatever the loader passed). The tag of a row ranks by its place in the concept's
tag list (``statement_concepts.py``, best first): a period takes its best-ranked reported
tag, and a quarter is never derived across tags (``ttm.discrete_quarters``).

``lines`` turns the rows into one ``Fact`` list per instrument and concept and ``trailing``
into each concept's TTM; the groups only name their concepts and decide their statuses.
Pure functions over frames: no storage.
"""

from collections.abc import Mapping, Sequence
from datetime import date, timedelta

import numpy as np
import pandas as pd

from algotrade.features.rollups.statements.ttm import Fact, Total, TtmParams, trailing

PRICE_STATS = "rollups/instrument/price_stats@v2"
STATEMENTS = "instruments/statements_accepted"  # by acceptance session, not filing date
COMPANY = "instruments/company"
EPOCH = date(1970, 1, 1)
PREFIX = "us-gaap:"
FINANCIAL_SIC = (6000, 6411)  # banks, brokers, insurers: their debt and operating income differ
COLUMNS = ("concept", "tag", "period_start", "period_end", "filed", "value")
FIELDS = tuple(f"{STATEMENTS}.{c}" for c in COLUMNS)

type Ranks = Mapping[str, Mapping[str, int]]  # concept -> tag -> rank (0 is the best)
type Lines = dict[str, dict[str, list[Fact]]]  # instrument -> concept -> facts


StatementParams = TtmParams


def tag_ranks(concepts: Mapping[str, Sequence[str]]) -> Ranks:
    """``{concept: {stored tag: rank}}`` from each concept's us-gaap tags, best first."""
    return {c: {f"{PREFIX}{t}": i for i, t in enumerate(tags)} for c, tags in concepts.items()}


def epoch_days(values: pd.Series) -> np.ndarray:
    return pd.to_datetime(values).to_numpy(dtype="datetime64[D]").astype(np.int64)


def day_date(days: int | None) -> date | None:
    return None if days is None else EPOCH + timedelta(days=days)


def stale_before(session: date, p: StatementParams) -> int:
    """The epoch day before which a TTM's period end makes it STALE."""
    return (session - timedelta(days=p.stale_days) - EPOCH).days


def lines(facts: pd.DataFrame | None, ranks: Ranks, session: date, p: StatementParams) -> Lines:
    """The duration facts of the concepts in ``ranks``, per instrument and concept: only those
    filed on or before ``session`` whose period ended within ``history_days``, the newest
    filing of each (tag, period), as ``ttm.Fact`` tuples (tag rank last)."""
    if facts is None or facts.empty or "value" not in facts.columns:
        return {}
    rows = facts[facts["concept"].isin(list(ranks)) & facts["value"].notna()]
    rows = rows[rows[["period_start", "period_end", "filed"]].notna().all(axis=1)]
    out = pd.DataFrame(
        {
            "instrument_id": rows["instrument_id"].astype(str),
            "concept": rows["concept"],
            "tag": rows["tag"].astype(str),
            "start": epoch_days(rows["period_start"]),
            "end": epoch_days(rows["period_end"]),
            "value": rows["value"].astype(float),
            "filed": epoch_days(rows["filed"]),
        }
    )
    today = (session - EPOCH).days
    out = out[(out["filed"] <= today) & (out["end"] >= today - p.history_days)]
    out["rank"] = [ranks[c].get(t, -1) for c, t in zip(out["concept"], out["tag"], strict=True)]
    out = out[out["rank"] >= 0]
    key = ["instrument_id", "concept", "tag", "start", "end"]
    out = out.sort_values([*key, "filed"], kind="stable").drop_duplicates(key, keep="last")
    found: Lines = {}
    cols = (
        out[c].tolist()
        for c in ("instrument_id", "concept", "start", "end", "value", "filed", "rank")
    )
    for iid, concept, start, end, value, filed, rank in zip(*cols, strict=True):
        found.setdefault(iid, {}).setdefault(concept, []).append((start, end, value, filed, rank))
    return found


def totals(
    concepts: Mapping[str, list[Fact]], non_negative: Sequence[str] = ()
) -> dict[str, Total]:
    """The TTM of each concept that has one (``ttm.trailing``): ``(value, newest period end,
    newest filing, annual?)``."""
    found = {c: trailing(f, c in non_negative) for c, f in concepts.items()}
    return {c: t[0] for c, t in found.items() if t is not None}


def financial_ids(company: pd.DataFrame | None) -> set[str]:
    """The instruments whose SIC code is 6000 to 6411 (``instruments/company``); none without
    a company snapshot or a ``sic`` column (an unknown SIC is treated as not financial)."""
    if company is None or "sic" not in company.columns:
        return set()
    sic = pd.to_numeric(company["sic"], errors="coerce")
    flag = (sic >= FINANCIAL_SIC[0]) & (sic <= FINANCIAL_SIC[1])
    return set(company.loc[flag, "instrument_id"].astype(str))
