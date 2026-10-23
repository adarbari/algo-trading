"""What the analyst feature groups share: the population, the vendor's rows as of a session and
the status of a name (``analyst_estimates@v2``, ``analyst_targets@v2``, ``analyst_ratings@v1``,
``analyst_revisions@v3``; ADR 0068, ADR 0072, ADR 0080).

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

The status helpers take the vendor (``source``) whose rows and markers they read: FMP by default,
Finnhub for the recommendation trend (``analyst_ratings@v1``), each with its own markers.

**One vendor per (name, kind)** (ADR 0080; estimates, targets and revisions only: ratings stay
Finnhub's). ``choose_vendor`` resolves a name for FMP and for Yahoo from the frame the session sees
and takes FMP's when its status is OK or STALE, else Yahoo's when Yahoo has a row or a marker that
is not FAILED (status not NOT_FETCHED), else FMP's. ``effective_snapshots`` keeps, per name, only
the chosen vendor's rows of the kind AND its coverage markers and relabels them ``fmp``, so
``vendor_rows``, ``resolve`` and ``history_rows`` read as before and the other vendor's markers
never mix in. The choice reads one name's own rows: a name Yahoo has not reached stays what FMP
says (NOT_COVERED), no name is judged by another. ``history_of_chosen`` restricts the history a
revision compares with to the vendor the estimates chose, so after a flip the new vendor's
revisions are null (BUILDING / NO_PRIOR) until its own snapshots span the windows (90 days).
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.rollups.market.breadth import MEMBER_CLASS

SNAPSHOTS = "analyst/estimate_snapshots"
UNIVERSE = "universe"
# The snapshot kinds the groups read (the reader's own: ``data.analyst.reading``; a test keeps them
# equal, a group never imports ``data``).
ESTIMATES, TARGET, COVERAGE = "estimates_annual", "price_target", "coverage"
RECOMMENDATION = "recommendation"  # Finnhub's monthly analyst counts
VENDOR = "fmp"  # the source column of the rows most of these groups read
FINNHUB = "finnhub"  # the source of the recommendation rows
YAHOO = "yahoo"  # the other source of estimates and targets (ADR 0080), used when FMP has none
SOURCES = (VENDOR, YAHOO)  # in order of preference
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
    "strong_buy",
    "buy",
    "hold",
    "sell",
    "strong_sell",
    "eps_trend_current",  # Yahoo's epsTrend: now, and N days before the fetch
    "eps_trend_30d_ago",
    "eps_trend_60d_ago",
    "eps_trend_90d_ago",
)
LOOKBACK = 70  # sessions of snapshots read: about 100 calendar days, well past the 21 of STALE
# Sessions of snapshots the groups that compare with 90 days back read: the newest snapshot may be
# ``stale_days`` (45, the longest) old, and the one before it 90 + SNAPSHOT_SLACK days earlier:
# 142 calendar days, about 98 sessions (a test checks it against the calendar).
HISTORY_LOOKBACK = 105
SNAPSHOT_SLACK = 7  # days: a refresh window; the snapshot "N days back" is at most this much older


@dataclass(frozen=True)
class AnalystParams:
    stale_days: int = 21  # a snapshot older than this is STALE: its values are not served

    def __post_init__(self) -> None:
        if self.stale_days < 1:
            raise ValueError("stale_days must be >= 1")


def population(
    universe: pd.DataFrame | None, snapshots: pd.DataFrame | None, vendor: str = VENDOR
) -> list[str]:
    """The equities of the session's universe; without one (the group requires it, so only a
    direct call) the names ``vendor`` has rows for."""
    if universe is not None and "asset_class" in universe.columns:
        stocks = universe.loc[universe["asset_class"] == MEMBER_CLASS, "instrument_id"]
        return sorted(set(stocks.astype(str)))
    if snapshots is None or snapshots.empty:
        return []
    return sorted(set(snapshots.loc[snapshots["source"] == vendor, "instrument_id"].astype(str)))


def vendor_rows(snapshots: pd.DataFrame | None, kind: str, vendor: str = VENDOR) -> pd.DataFrame:
    """The vendor's rows of ``kind``, only each name's newest snapshot (its latest
    ``session_date``: an older fetch of a period the newest no longer lists is not mixed in)."""
    if snapshots is None or snapshots.empty:
        return pd.DataFrame(columns=["instrument_id", "session_date", *NEEDED])
    rows = snapshots[(snapshots["source"] == vendor) & (snapshots["kind"] == kind)]
    rows = rows.assign(instrument_id=rows["instrument_id"].astype(str)).reindex(
        columns=[*dict.fromkeys([*rows.columns, *NEEDED])]
    )
    newest = rows.groupby("instrument_id")["session_date"].transform("max")
    return rows[rows["session_date"] == newest]


def history_rows(
    snapshots: pd.DataFrame | None, kind: str, vendor: str, session: date
) -> pd.DataFrame:
    """Every snapshot of ``vendor``'s ``kind`` for a session on or before ``session``, all the
    sessions the input holds (``vendor_rows`` keeps only the newest): what a comparison with
    an earlier snapshot reads. A snapshot of a later session is never read, whatever the frame
    holds."""
    rows = vendor_rows(None, kind, vendor)
    if snapshots is None or snapshots.empty:
        return rows
    rows = snapshots[(snapshots["source"] == vendor) & (snapshots["kind"] == kind)]
    rows = rows[pd.to_datetime(rows["session_date"]).dt.date <= session]
    rows = rows.assign(instrument_id=rows["instrument_id"].astype(str))
    return rows.reindex(columns=[*dict.fromkeys([*rows.columns, *NEEDED])])


def days_back(anchor: pd.Series, days: int) -> tuple[pd.Series, pd.Series]:
    """The window of the snapshot that stands for ``days`` before ``anchor`` (a Series of the
    day of each name's NEWEST snapshot, not of the session: the window then spans ``days``
    whatever the age of the newest snapshot), as ``(first, last)``: from ``days +
    SNAPSHOT_SLACK`` before it to ``days`` before it (a night the fetch missed must not reach
    back to a stale value)."""
    last = anchor - pd.Timedelta(days=days)
    return last - pd.Timedelta(days=SNAPSHOT_SLACK), last


def _markers(snapshots: pd.DataFrame | None, vendor: str) -> dict[str, tuple[date, str]]:
    """Each name's newest coverage marker of the vendor that is not FAILED: ``(day, status)``."""
    if snapshots is None or snapshots.empty:
        return {}
    marks = snapshots[(snapshots["source"] == vendor) & (snapshots["kind"] == COVERAGE)]
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
    vendor: str = VENDOR,
) -> pd.DataFrame:
    """``instrument_id``, ``status`` and ``age_days`` (null unless OK or STALE) of each name;
    ``rows`` are ``vendor_rows`` of the group's kind (and ``vendor``)."""
    seen = rows.groupby("instrument_id")["session_date"].max().to_dict()
    marks = _markers(snapshots, vendor)
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


def choose_vendor(
    snapshots: pd.DataFrame | None, ids: list[str], kind: str, session: date, p: AnalystParams
) -> pd.Series:
    """``instrument_id`` -> ``fmp`` / ``yahoo``: the vendor whose ``kind`` rows and markers the
    group reads for the name (the module doc): FMP when OK or STALE, else Yahoo when it has a row
    or a marker that is not FAILED, else FMP."""
    status = {}
    for vendor in SOURCES:
        rows = vendor_rows(snapshots, kind, vendor)
        found = resolve(ids, rows, snapshots, session, p, vendor)
        status[vendor] = found.set_index("instrument_id")["status"]
    fmp, yahoo = status[VENDOR], status[YAHOO]
    use_yahoo = ~fmp.isin([OK, STALE]) & (yahoo != NOT_FETCHED)
    return pd.Series(np.where(use_yahoo, YAHOO, VENDOR), index=fmp.index, dtype=object)


def effective_snapshots(
    snapshots: pd.DataFrame | None, chosen: pd.Series, kind: str
) -> pd.DataFrame | None:
    """``snapshots`` reduced to each name's chosen vendor: its rows of ``kind`` and its coverage
    markers, labelled ``fmp``; nothing of the other vendor and no other kind (``chosen`` from
    ``choose_vendor``). ``None`` and an empty frame pass through."""
    if snapshots is None or snapshots.empty:
        return snapshots
    own = snapshots["instrument_id"].astype(str).map(chosen)
    keep = snapshots["kind"].isin([kind, COVERAGE]) & (snapshots["source"] == own)
    return snapshots[keep].assign(source=VENDOR)


def history_of_chosen(
    snapshots: pd.DataFrame | None, kind: str, chosen: pd.Series, session: date
) -> pd.DataFrame:
    """``history_rows`` of ``kind`` over the vendors, only each name's chosen vendor's rows
    (``chosen``: the estimates' source per name), labelled ``fmp``."""
    both = [history_rows(snapshots, kind, vendor, session) for vendor in SOURCES]
    rows = pd.concat(both, ignore_index=True)
    if "source" not in rows.columns:  # no snapshot table: no history
        return rows
    own = rows["instrument_id"].map(chosen)
    return rows[rows["source"] == own].assign(source=VENDOR).reset_index(drop=True)
