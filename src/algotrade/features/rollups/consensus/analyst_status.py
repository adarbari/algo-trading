"""What the analyst feature groups share: the population, the vendor's rows as of a session and
the status of a name (``analyst_estimates@v1``, ``analyst_targets@v1``; ADR 0068, ADR 0072).

The input is ``analyst/estimate_snapshots`` as a session sees it (``data.analyst.reading``: the
latest version of each row published before the next open). One row per universe equity, so the
served table stays one session; without the table every name is ``NOT_FETCHED``.

Status of a name (``resolve``), from the vendor's rows of the group's kind and its coverage
markers (``kind = "coverage"``, one per attempt; a snapshot stored before the markers has none):

    OK           the newest snapshot is at most ``stale_days`` old
    STALE        older: the values are not served (null, read as not stored), the age still is
    NOT_COVERED  the vendor answered and has nothing of this kind for the name: the NEWEST marker
                 that is not FAILED says NOT_COVERED or EMPTY, or says OK and no row of this kind
                 is as new (with older rows the name still reads NOT_COVERED: the vendor now has
                 none)
    NOT_FETCHED  no row and no marker (never asked), or only FAILED markers (an error says
                 nothing about coverage, and never hides an earlier refusal)

A trader reads both of the last two as "not covered"; the stored status tells them apart
(``Feature.uncovered_statuses``, ADR 0072). The age is whole days from the snapshot's
``session_date`` (the session the fetch was for) to the session.
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade.features.rollups.market.breadth import MEMBER_CLASS

SNAPSHOTS = "analyst/estimate_snapshots"
UNIVERSE = "universe"
# The snapshot kinds the groups read (the reader's own: ``data.analyst.reading``; a test keeps them
# equal, a group never imports ``data``).
ESTIMATES, TARGET, COVERAGE = "estimates_annual", "price_target", "coverage"
VENDOR = "fmp"  # the source column of the rows these groups read
OK, STALE, NOT_COVERED, NOT_FETCHED = "OK", "STALE", "NOT_COVERED", "NOT_FETCHED"
STATUSES = (OK, STALE, NOT_COVERED, NOT_FETCHED)
UNCOVERED = (NOT_COVERED, NOT_FETCHED)  # ``Feature.uncovered_statuses`` (ADR 0072)
FAILED = "FAILED"
NEEDED = (  # the snapshot columns the groups read: a store without one reads it as empty
    "period",
    "eps_avg",
    "revenue_avg",
    "num_analysts_eps",
    "num_analysts_revenue",
    "target_consensus",
    "target_median",
    "target_high",
    "target_low",
)
LOOKBACK = 70  # sessions of snapshots read: about 100 calendar days, well past the 21 of STALE


@dataclass(frozen=True)
class AnalystParams:
    stale_days: int = 21  # a snapshot older than this is STALE: its values are not served

    def __post_init__(self) -> None:
        if self.stale_days < 1:
            raise ValueError("stale_days must be >= 1")


def population(universe: pd.DataFrame | None, snapshots: pd.DataFrame | None) -> list[str]:
    """The equities of the session's universe; without one (the group requires it, so only a
    direct call) the names the vendor has rows for."""
    if universe is not None and "asset_class" in universe.columns:
        stocks = universe.loc[universe["asset_class"] == MEMBER_CLASS, "instrument_id"]
        return sorted(set(stocks.astype(str)))
    if snapshots is None or snapshots.empty:
        return []
    return sorted(set(snapshots.loc[snapshots["source"] == VENDOR, "instrument_id"].astype(str)))


def vendor_rows(snapshots: pd.DataFrame | None, kind: str) -> pd.DataFrame:
    """The vendor's rows of ``kind``, only each name's newest snapshot (its latest
    ``session_date``: an older fetch of a period the newest no longer lists is not mixed in)."""
    if snapshots is None or snapshots.empty:
        return pd.DataFrame(columns=["instrument_id", "session_date", *NEEDED])
    rows = snapshots[(snapshots["source"] == VENDOR) & (snapshots["kind"] == kind)]
    rows = rows.assign(instrument_id=rows["instrument_id"].astype(str)).reindex(
        columns=[*dict.fromkeys([*rows.columns, *NEEDED])]
    )
    newest = rows.groupby("instrument_id")["session_date"].transform("max")
    return rows[rows["session_date"] == newest]


def _markers(snapshots: pd.DataFrame | None) -> dict[str, tuple[date, str]]:
    """Each name's newest coverage marker of the vendor that is not FAILED: ``(day, status)``."""
    if snapshots is None or snapshots.empty:
        return {}
    marks = snapshots[(snapshots["source"] == VENDOR) & (snapshots["kind"] == COVERAGE)]
    marks = marks[marks["status"] != FAILED]  # an error says nothing about coverage
    marks = marks.sort_values(["session_date", "knowledge_ts"], kind="stable")
    return {
        str(i): (d, str(s))
        for i, d, s in zip(
            marks["instrument_id"], marks["session_date"], marks["status"], strict=True
        )
    }


def resolve(
    ids: list[str],
    rows: pd.DataFrame,
    snapshots: pd.DataFrame | None,
    session: date,
    p: AnalystParams,
) -> pd.DataFrame:
    """``instrument_id``, ``status`` and ``age_days`` (null unless OK or STALE) of each name;
    ``rows`` are ``vendor_rows`` of the group's kind."""
    seen = rows.groupby("instrument_id")["session_date"].max().to_dict()
    marks = _markers(snapshots)
    out = []
    for iid in ids:
        mark = marks.get(iid)
        if iid in seen:
            if mark and mark[0] > seen[iid]:  # a newer answer with no row of this kind
                out.append((iid, NOT_COVERED, None))
                continue
            age = (session - seen[iid]).days
            out.append((iid, STALE if age > p.stale_days else OK, age))
        else:
            out.append((iid, NOT_COVERED if mark else NOT_FETCHED, None))
    return pd.DataFrame(out, columns=["instrument_id", "status", "age_days"])
