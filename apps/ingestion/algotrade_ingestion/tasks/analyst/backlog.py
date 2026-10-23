"""The analyst fetch backlog: in-scope names the vendor has not been asked about (ADR 0072).

The analyst feature groups read a name nobody asked about as ``NOT_FETCHED`` and a name the
vendor refused as ``NOT_COVERED``; a trader reads both as "not covered", and the coverage check
exempts both (``tasks/maintenance/coverage.py``, else most names would grade as gaps). That hides
the names the nightly rotation has not reached, so this check measures them: of the names the
``analyst-snapshot`` task is meant to ask (``snapshot.scope_names``), the share with no FMP row
and no FMP coverage marker other than FAILED in the last ``[fmp] refused_hold_days`` (90; a
refused name is held that long before it is asked again, so its marker, or its rows, keep it out
of the backlog; an answered name is refreshed every ``refresh_days``, well inside it). A name
whose every attempt FAILED (a symbol the vendor rejects) was not reached: it stays in the
backlog, as the features show it NOT_FETCHED.

WARN only, above ``[quality] max_analyst_backlog``: the step is optional, and a backlog means
the ``[fmp] daily_budget`` is smaller than the names due, not that data is wrong. Nothing without
a finished run of the session. Every attempt writes a coverage marker, so a refused or empty name
is asked, not backlog; only a name no attempt reached in the window is.

The same measure for Finnhub (``check_finnhub_backlog``, the recommendation trend that
``analyst_ratings@v1`` reads): the share with no Finnhub row and no Finnhub coverage marker other
than FAILED in the last four ``[finnhub] refresh_days`` windows, against the same
``max_analyst_backlog``. When the run skipped Finnhub (no key, or the probe says DENIED) it WARNs
with the run's reason: every name then reads NOT_FETCHED, and the ratings group would otherwise
read "not covered" for the whole universe without a word (FMP without a key warns the same way).
"""

from datetime import date, timedelta

from algotrade.data.analyst.reading import COVERAGE, KINDS, stored_snapshots
from algotrade_ingestion.tasks.analyst.snapshot import TASK, retry_days, scope_names
from algotrade_ingestion.tasks.framework.run import PUBLISHED, TaskContext
from algotrade_ingestion.tasks.maintenance.quality import Check

CHECK = "analyst_backlog"
FINNHUB_CHECK = "finnhub_backlog"
VENDOR = "fmp"
FINNHUB = "finnhub"
FAILED = "FAILED"  # a marker of an error: the vendor was not reached, so the name is not asked
EXAMPLES = 10  # names listed in the check's data


def check_analyst_backlog(ctx: TaskContext, session: date) -> list[Check]:
    """WARN when over ``max_analyst_backlog`` of the in-scope names were not asked of FMP in the
    last ``refused_hold_days``; PASS otherwise; nothing without a finished run."""
    return _backlog(ctx, session, VENDOR, CHECK, ctx.settings.fmp_refused_hold_days)


def check_finnhub_backlog(ctx: TaskContext, session: date) -> list[Check]:
    """The same for Finnhub's recommendation trend and its own refresh cadence; a WARN naming the
    reason when the finished run skipped Finnhub."""
    return _backlog(
        ctx, session, FINNHUB, FINNHUB_CHECK, retry_days(ctx.settings.finnhub_refresh_days)
    )


def _backlog(ctx: TaskContext, session: date, vendor: str, check: str, days: int) -> list[Check]:
    done = [r for r in ctx.reader.runs(TASK) if r.status in PUBLISHED and r.session_date == session]
    skipped = [
        str(r.stats[vendor]["skipped"]) for r in done if "skipped" in r.stats.get(vendor, {})
    ]
    if vendor == FINNHUB and skipped:  # no call was made: every name is unasked
        return [Check(check, "WARN", f"Finnhub was not asked tonight: {skipped[0]}")]
    names = scope_names(ctx.reader, ctx, session) if done else []
    if not names:
        return []
    since = session - timedelta(days=days)
    ids = sorted({n.instrument_id for n in names})
    rows = stored_snapshots(ctx.reader, None, KINDS, ids, since=since, through=session)
    reached = (rows["source"] == vendor) & ~(
        (rows["kind"] == COVERAGE) & (rows["status"] == FAILED)
    )
    asked = set(rows.loc[reached, "instrument_id"].astype(str))
    missing = [n for n in names if n.instrument_id not in asked]
    share, limit = len(missing) / len(names), ctx.settings.max_analyst_backlog
    detail = (
        f"{len(missing)} of {len(names)} in-scope names not asked of {vendor.upper()} in the "
        f"last {days} days ({share:.0%}; max {limit:.0%})"
    )
    data = {
        "in_scope": len(names),
        "not_asked": len(missing),
        "examples": sorted(n.symbol for n in missing)[:EXAMPLES],
    }
    return [Check(check, "WARN" if share > limit else "PASS", detail, data=data)]
