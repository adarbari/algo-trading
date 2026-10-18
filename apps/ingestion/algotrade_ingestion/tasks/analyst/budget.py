"""FMP's daily call budget, counted once for every analyst task that spends it.

The free plan allows about 250 calls a day; ``[fmp] daily_budget`` (200) is what the analyst tasks
may spend, a hand run's headroom included. ``fmp_calls_today`` returns what the tasks in ``TASKS``
spent in the UTC day of the run's clock, over EVERY run of them in any status (a crashed or failed
run spent its calls) other than the current run, plus the current run's own items. An item is one
call when its key starts with ``fmp:`` and its status is not ``OVER_BUDGET`` (not made). Later
analyst tasks add their name to ``TASKS`` and key their FMP items the same way.
"""

from algotrade_ingestion.tasks.framework.run import IngestRun, status_label

TASKS = ("analyst-probe", "analyst-snapshot")
PREFIX = "fmp:"
NOT_MADE = "OVER_BUDGET"


def _calls(items: dict[str, str]) -> int:
    return sum(
        1
        for key, status in items.items()
        if key.startswith(PREFIX) and status_label(status) != NOT_MADE
    )


def fmp_calls_today(run: IngestRun) -> int:
    """The FMP calls spent in the UTC day of ``run`` (see the module docstring)."""
    today = run.clock().date()
    spent = _calls(run.items)
    for task in TASKS:
        for record in run.writer.runs_for(task):
            if record.run_id != run.run_id and record.started_at.date() == today:
                spent += _calls(record.items)
    return spent
