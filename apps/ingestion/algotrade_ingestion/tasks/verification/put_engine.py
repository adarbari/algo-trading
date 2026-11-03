"""Cboe's PUT index through the trade engine (ADR 0084 decision 6, ADR 0088 E5): the
``structure_pnl@v2`` rows the history writer stores for one cash-secured short put on SPX, one
non-overlapping trade per roll, compounded with the 3-month bills the collateral earns and set
against the published level. It maps engine rows to a level series and calls
``put_replication.compare`` (the one place the gap statistics live); it holds no strategy of its
own.

Per trade, per unit of collateral ``K``: ``pnl_mid / K`` plus the carry of ``K`` and the premium at
the roll day's 3-month rate, simple, actual / 360 (``put_replication``'s stand-ins, named in the
ADR: Cboe rolls on a roll-time average and settles on the SOQ, the engine on the 16:00 mid). The
rows hold no daily marks, so the series has one point per roll and the RMS ``compare`` reports is
of the roll-to-roll returns; the ADR's daily RMS tolerance stays ``put_check``'s. The tolerance
this function applies is the cumulative gap, at most ``MAX_ANNUAL_GAP_BP`` basis points a year."""

from collections.abc import Callable
from datetime import date
from typing import Any

import pandas as pd

from algotrade.core.model.errors import MissingDataError
from algotrade.core.model.instruments import index_id
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.schemas import STRUCTURE_PNL as TABLE
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext
from algotrade_ingestion.tasks.verification import put_replication
from algotrade_ingestion.tasks.verification.put_check import (
    MAX_ANNUAL_GAP_BP,
    published_levels,
    three_month_rate,
)

DAY_COUNT = put_replication.DAY_COUNT
HISTORY = "option_history"  # the rows' price source
SHOWN = 5


def level_series(rows: pd.DataFrame, rate_on: Callable[[date], float]) -> pd.Series:
    """The compounded level (1 at the first entry) after each trade, indexed by the date the trade
    ended: ``rows`` are one position's COMPLETE trades of one underlying, ``rate_on`` the 3-month
    rate (a fraction) of a date. ``ValueError`` when two trades overlap or one has no
    collateral."""
    done = rows[rows["outcome_status"] == "COMPLETE"].copy()
    done["entry"] = pd.to_datetime(done["ts"]).dt.date
    done["exit"] = pd.to_datetime(done["exit_session"]).dt.date
    done = done.sort_values("entry")
    if (done["exit"].to_numpy()[:-1] > done["entry"].to_numpy()[1:]).any():
        raise ValueError("trades overlap: a ladder is not the PUT index's one put a month")
    level, out = 1.0, {done["entry"].iloc[0]: 1.0}
    trades = zip(
        done["entry"], done["exit"], done["collateral"].astype(float),
        done["entry_net_mid"].astype(float), done["pnl_mid"].astype(float), strict=True,
    )  # fmt: skip
    for entry, exit_day, strike, net, pnl in trades:
        if not strike > 0:
            raise ValueError(f"{entry}: no collateral")
        carry = rate_on(entry) * (exit_day - entry).days / DAY_COUNT * (1 + abs(net) / strike)
        level *= 1 + pnl / strike + carry
        out[exit_day] = level
    return pd.Series(out, dtype=float).sort_index()


def engine_replication(
    rows: pd.DataFrame, rate_on: Callable[[date], float], published: pd.Series
) -> dict[str, Any]:
    """The gap statistics of the engine's series against ``published`` (``put_replication.compare``)
    with ``years``, ``annual_gap_bp`` and ``within_tolerance`` (the cumulative gap per year)."""
    stats = put_replication.compare(level_series(rows, rate_on), published)
    years = (stats["end"] - stats["start"]).days / 365.25
    stats["years"] = years
    stats["annual_gap_bp"] = stats["gap_bp"] / years if years > 0 else float("nan")
    stats["within_tolerance"] = abs(stats["annual_gap_bp"]) <= MAX_ANNUAL_GAP_BP
    return stats


TASK = "option-history-put-engine-check"
UNDERLYING = index_id("SPX")


def put_engine_check(
    ctx: TaskContext, today: date, start: date | None, end: date | None, position: str | None
) -> RunRecord:
    """The check over the stored rows of ``position`` (a ``position_key``; ``None``: the only key
    stored for SPX from the history) in ``start..end`` (the entry sessions): the run record holds
    the gap statistics and FAILs outside the tolerance, reported, never tuned away. ``ctx.reader``
    is the main store (the rows, the Treasury curve, the published level)."""
    with IngestRun(ctx, TASK, today) as run:
        frames = [ctx.reader.table(TABLE, d) for d in ctx.reader.dates(TABLE)]
        found = [f for f in frames if f is not None]
        if not found:
            run.failed("no structure_pnl@v2 rows stored: run option-history-outcomes first")
            return run.record
        rows = pd.concat(found, ignore_index=True)
        rows = rows[(rows["instrument_id"] == UNDERLYING) & (rows["price_source"] == HISTORY)]
        entry = pd.to_datetime(rows["ts"]).dt.date
        rows = rows[(entry >= (start or date.min)) & (entry <= (end or date.max))]
        keys = sorted(set(rows["position_key"]))
        if position is None and len(keys) == 1:
            position = keys[0]
        if position not in keys:
            run.failed(f"name one position with --position; stored for SPX: {keys[:SHOWN]}")
            return run.record
        rows = rows[rows["position_key"] == position]
        run.stats.update(position=position, trades=len(rows))
        try:
            rates = {
                pd.Timestamp(t).date(): three_month_rate(ctx.reader, pd.Timestamp(t).date())
                for t in rows["ts"]
            }
            stats = engine_replication(rows, lambda d: rates[d], published_levels(ctx.reader))
        except (MissingDataError, ValueError, KeyError) as exc:
            run.failed(f"{type(exc).__name__}: {exc}")
            return run.record
        run.stats.update({k: str(v) if isinstance(v, date) else v for k, v in stats.items()})
        if not stats["within_tolerance"]:
            run.failed(
                f"outside tolerance: annual gap {stats['annual_gap_bp']:.1f} bp "
                f"(max {MAX_ANNUAL_GAP_BP}); roll-to-roll RMS {stats['rms_daily_diff_bp']:.1f} bp"
            )
    return run.record
