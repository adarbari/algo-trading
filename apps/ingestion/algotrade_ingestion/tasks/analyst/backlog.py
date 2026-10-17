"""The analyst fetch backlog: in-scope names the vendor has not been asked about (ADR 0072).

The analyst feature groups read a name nobody asked about as ``NOT_FETCHED`` and a name the
vendor refused as ``NOT_COVERED``; a trader reads both as "not covered", and the coverage check
exempts both (``tasks/maintenance/coverage.py``, else most names would grade as gaps). That hides
the names the nightly rotation has not reached, so this check measures them: of the names the
``analyst-snapshot`` task is meant to ask (``snapshot.scope_names``), the share with no FMP row
and no FMP coverage marker in the last ``RETRY_WINDOWS`` refresh windows (a refused name is held
that long before it is asked again, so its marker, or its rows, keep it out of the backlog).

WARN only, above ``[quality] max_analyst_backlog``: the step is optional, and a backlog means
the ``[fmp] daily_budget`` is smaller than the names due, not that data is wrong. Nothing without
a finished run of the session. Every attempt writes a coverage marker, so a refused or empty name
is asked, not backlog; only a name no attempt reached in the window is.
"""

from datetime import date, timedelta

from algotrade.data.analyst.reading import KINDS, stored_snapshots
from algotrade_ingestion.tasks.analyst.snapshot import (
    RETRY_WINDOWS,
    TASK,
    scope_names,
)
from algotrade_ingestion.tasks.framework.run import PUBLISHED, TaskContext
from algotrade_ingestion.tasks.maintenance.quality import Check

CHECK = "analyst_backlog"
VENDOR = "fmp"
EXAMPLES = 10  # names listed in the check's data


def check_analyst_backlog(ctx: TaskContext, session: date) -> list[Check]:
    """WARN when over ``max_analyst_backlog`` of the in-scope names were not asked of FMP in the
    last ``RETRY_WINDOWS`` refresh windows; PASS otherwise; nothing without a finished run."""
    done = [r for r in ctx.reader.runs(TASK) if r.status in PUBLISHED and r.session_date == session]
    names = scope_names(ctx.reader, ctx, session) if done else []
    if not names:
        return []
    since = session - timedelta(days=RETRY_WINDOWS * ctx.settings.fmp_refresh_days)
    ids = sorted({n.instrument_id for n in names})
    rows = stored_snapshots(ctx.reader, None, KINDS, ids, since=since, through=session)
    asked = set(rows.loc[rows["source"] == VENDOR, "instrument_id"].astype(str))
    missing = [n for n in names if n.instrument_id not in asked]
    share, limit = len(missing) / len(names), ctx.settings.max_analyst_backlog
    detail = (
        f"{len(missing)} of {len(names)} in-scope names not asked of FMP in the last "
        f"{RETRY_WINDOWS * ctx.settings.fmp_refresh_days} days ({share:.0%}; max {limit:.0%})"
    )
    data = {
        "in_scope": len(names),
        "not_asked": len(missing),
        "examples": sorted(n.symbol for n in missing)[:EXAMPLES],
    }
    return [Check(CHECK, "WARN" if share > limit else "PASS", detail, data=data)]
