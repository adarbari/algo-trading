"""Tiingo's monthly symbol cap, counted once for every task that spends it.

The free tier allows 500 distinct symbols a calendar month. Two tasks ask for symbols:
``bars-history`` (items ``hist:<instrument id>``) and ``winners-sample`` (items
``win:<ticker>:<start>``). ``month_symbols`` returns what both spent in the UTC month of the run's
clock, whatever the item status (a ``FETCH_ERROR`` request may still have counted), over EVERY
run of either task in any status (a crashed or failed run spent its requests) other than the
current run, in each month between its start and its finish (now, when unfinished), plus the
current run's own items. A symbol both tasks asked for counts twice (the two keys differ: safe
side of the cap).
"""

from datetime import datetime

from algotrade_ingestion.tasks.framework.run import IngestRun

TASKS = ("bars_history", "winners-sample")
PREFIXES = ("hist:", "win:")


def _months(first: datetime, last: datetime) -> set[tuple[int, int]]:
    """The UTC (year, month) pairs from ``first`` to ``last``."""
    year, month = first.year, first.month
    found = set()
    while (year, month) <= (last.year, last.month):
        found.add((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return found


def _symbol(key: str) -> str | None:
    """``hist:EQ:X`` -> itself; ``win:T:2010-01-04`` -> ``win:T``; other items -> None."""
    if key.startswith("hist:"):
        return key
    if key.startswith("win:"):
        return "win:" + key.split(":")[1]
    return None


def month_symbols(run: IngestRun) -> set[str]:
    """The symbol keys spent this month by both tasks (see the module docstring)."""
    now = run.clock()
    used = {s for k in run.items if (s := _symbol(k))}
    for task in TASKS:
        for record in run.writer.runs_for(task):
            if record.run_id == run.run_id:
                continue
            end = record.finished_at or max(now, record.started_at)
            if (now.year, now.month) in _months(record.started_at, end):
                used |= {s for k in record.items if (s := _symbol(k))}
    return used
