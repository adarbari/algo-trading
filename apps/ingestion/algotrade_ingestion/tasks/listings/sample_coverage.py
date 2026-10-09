"""Coverage of one sampled listing's Tiingo bars against the listing's own dates (edges ED6c).

Pure functions over the bars a ticker request returned (all of them, from 2010) and the exchange
sessions: how many bars fall inside the listing's window, where they start and end, the sessions
missing between the first and last bar, the bars Tiingo returned for dates outside the listing
(a recycled ticker's other company), and, for the hand-listed winners, the split-adjusted
price ratio from 2010 to 2016 that says whether the name really was one. ``summarize`` turns the
rows into the study's pass criteria: at least ``MIN_TO_END`` of the delisted names have bars to
their end date, under ``MAX_GAP_SHARE`` of the sessions between a name's first and last bar are
missing, and no recycled ticker returns a bar outside its own listing's dates.
"""

from bisect import bisect_left, bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

MIN_TO_END = 0.90
MAX_GAP_SHARE = 0.02
END_TOLERANCE_DAYS = 5  # "bars to the end date": the last bar within this many calendar days
RATIO_FROM_YEAR, RATIO_TO_YEAR = 2010, 2016
DELISTED, LIVE, WINNER = "delisted", "live", "winner"


@dataclass(frozen=True)
class Pick:
    """One sampled listing: a name of the stratum, its vendor dates, and whether its ticker
    belongs to more than one listing in the file (recycled)."""

    ticker: str
    start_date: date
    end_date: date | None
    stratum: str
    recycled: bool = False


def _count(sessions: Sequence[date], first: date, last: date) -> int:
    """Sessions in ``first..last`` (both ends included)."""
    return max(0, bisect_right(sessions, last) - bisect_left(sessions, first))


def split_adjusted_ratio(bars: pd.DataFrame, actions: pd.DataFrame) -> float | None:
    """Value in 2016 of one share held at the 2010 close, over that close: the last 2016 close
    times the splits since the last 2010 close (Tiingo's ``splitFactor``: 2 = two for one),
    over the 2010 close. Price only (dividends ignored). ``None`` without a bar in both years."""
    days = pd.to_datetime(bars["ts"]).dt.date
    first = bars[[d.year == RATIO_FROM_YEAR for d in days]]
    last = bars[[d.year == RATIO_TO_YEAR for d in days]]
    if first.empty or last.empty:
        return None
    start, end = pd.Timestamp(first["ts"].iloc[-1]), pd.Timestamp(last["ts"].iloc[-1])
    splits = 1.0
    if len(actions):
        when = pd.to_datetime(actions["ts"])
        factors = actions.loc[(when > start) & (when <= end), "split_factor"]
        splits = float(np.prod(factors.to_numpy(dtype=float)))
    closes = (first["close"].to_numpy(dtype=float)[-1], last["close"].to_numpy(dtype=float)[-1])
    return float(closes[1] * splits / closes[0])


def coverage_row(
    pick: Pick,
    bars: pd.DataFrame,
    actions: pd.DataFrame,
    sessions: Sequence[date],
    since: date,
    until: date,
) -> dict[str, Any]:
    """The coverage of ``pick`` by ``bars`` (``ts`` + OHLCV, every row Tiingo returned for the
    ticker) over its window ``max(start, since)..(end or until)``; ``sessions`` is sorted."""
    first_day = max(pick.start_date, since)
    last_day = pick.end_date or until
    days = sorted(pd.to_datetime(bars["ts"]).dt.date) if len(bars) else []
    inside = [d for d in days if first_day <= d <= last_day]
    row: dict[str, Any] = {
        "ticker": pick.ticker,
        "stratum": pick.stratum,
        "recycled": pick.recycled,
        "start_date": pick.start_date.isoformat(),
        "end_date": pick.end_date.isoformat() if pick.end_date else None,
        "bars_returned": len(days),
        "bars": len(inside),
        "outside_rows": len(days) - len(inside),
        "expected_sessions": _count(sessions, first_day, last_day),
        "first_bar": inside[0].isoformat() if inside else None,
        "last_bar": inside[-1].isoformat() if inside else None,
    }
    if inside:
        span = _count(sessions, inside[0], inside[-1])
        row["span_sessions"] = span
        row["gap_days"] = span - len(set(inside) & set(sessions))
        row["start_gap_days"] = _count(sessions, first_day, inside[0]) - 1
        row["end_gap_days"] = _count(sessions, inside[-1], last_day) - 1
        row["to_end"] = (last_day - inside[-1]).days <= END_TOLERANCE_DAYS
    else:
        row.update(
            span_sessions=0, gap_days=0, start_gap_days=None, end_gap_days=None, to_end=False
        )
    row["ratio_2010_2016"] = (
        split_adjusted_ratio(bars, actions) if pick.stratum == WINNER and len(bars) else None
    )
    return row


def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The study's pass criteria over the per-name rows."""
    delisted = [r for r in rows if r["stratum"] == DELISTED]
    to_end = sum(1 for r in delisted if r["to_end"])
    span = sum(int(r["span_sessions"]) for r in rows)
    gaps = sum(int(r["gap_days"]) for r in rows)
    leaked = sum(int(r["outside_rows"]) for r in rows if r["recycled"])
    share = to_end / len(delisted) if delisted else None
    gap_share = gaps / span if span else None
    ratios = sorted(
        (r["ratio_2010_2016"] for r in rows if r.get("ratio_2010_2016") is not None), reverse=True
    )
    return {
        "names": len(rows),
        "no_bars": sum(1 for r in rows if r["bars"] == 0),
        "by_stratum": {
            s: sum(1 for r in rows if r["stratum"] == s) for s in (DELISTED, LIVE, WINNER)
        },
        "delisted_with_bars_to_end": share,
        "gap_share": gap_share,
        "recycled_names": sum(1 for r in rows if r["recycled"]),
        "recycled_outside_rows": leaked,
        "winner_ratios_top": [round(x, 2) for x in ratios[:5]],
        "winner_ratios_median": round(ratios[len(ratios) // 2], 2) if ratios else None,
        "pass_delisted_to_end": share is not None and share >= MIN_TO_END,
        "pass_gap_share": gap_share is not None and gap_share < MAX_GAP_SHARE,
        "pass_recycled_clipped": leaked == 0,
    }
