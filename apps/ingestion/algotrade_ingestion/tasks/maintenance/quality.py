"""Data-quality checks: fail loudly instead of screening on bad or missing data.

Each check is PASS, WARN or FAIL with a detail line. The nightly runs them as the acceptance
checks of the steps that wrote the data (ADR 0039, ``workflows/nightly/nightly.py``): a FAIL
fails that step, which holds back the steps that need it. The ``quality`` task runs them all
for a session by hand (any FAIL makes that run PARTIAL). Thresholds come from
``config/site/sources.toml`` ``[quality]``.
"""

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date

from algotrade.config.site.settings import SourcesSettings
from algotrade.data import StoreReader
from algotrade.data.chains import chain_status
from algotrade.data.reference import snapshot
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext

TASK = "data_quality"


@dataclass(frozen=True)
class Check:
    name: str
    status: str  # PASS | WARN | FAIL
    detail: str
    pending: bool = False  # a FAIL that only means "the source has not published it yet" (ADR 0043)


def _rows(reader: StoreReader, table: str, day: date | None) -> int | None:
    if day is None:
        return None
    frame = reader.table(table, day)
    return None if frame is None else len(frame)


def _latest(reader: StoreReader, table: str, session: date) -> date | None:
    """The partition a read for ``session`` sees; ``None`` if every one is after it."""
    snap = snapshot(reader, table, session)
    return None if snap is None or snap.pre_snapshot else snap.snapshot_date


def _previous(reader: StoreReader, table: str, session: date) -> date | None:
    dates = [d for d in reader.dates(table) if d < session]
    return dates[-1] if dates else None


BARS_TASK = "daily_bars"  # the bars task's run-record job name (tasks/market/bars.py)
NOT_PUBLISHED = "NOT_PUBLISHED"  # the bars task's item status (tasks/market/bars.py)


def _bars_not_published(reader: StoreReader, session: date) -> bool:
    """Whether the latest bars run for ``session`` found it not published yet (the vendor
    answers for the session before: ``tasks/market/bars.py``)."""
    runs = [r for r in reader.runs(BARS_TASK, session) if r.finished_at is not None]
    if not runs:
        return False
    latest = max(runs, key=lambda r: r.finished_at or r.started_at)
    return str(latest.items.get(session.isoformat(), "")).startswith(NOT_PUBLISHED)


def check_bars(reader: StoreReader, session: date, s: SourcesSettings) -> list[Check]:
    latest = _latest(reader, "bars/1d", session)
    if latest is None:
        return [Check("bars_present", "FAIL", "no bars stored (backfill not run)")]
    checks = [
        Check(
            "bars_fresh",
            "PASS" if latest == session else "FAIL",
            f"latest bars session {latest}, expected {session}",
            pending=latest != session and _bars_not_published(reader, session),
        )
    ]
    today, before = (
        _rows(reader, "bars/1d", latest),
        _rows(reader, "bars/1d", _previous(reader, "bars/1d", latest)),
    )
    if today and before:
        drop = 1 - today / before
        status = "FAIL" if drop > s.max_bar_count_drop else "PASS"
        checks.append(
            Check(
                "bars_count",
                status,
                f"{today} bars vs {before} the session before ({drop:+.1%} drop)",
            )
        )
    return checks


def check_bars_resolved(reader: StoreReader, session: date, s: SourcesSettings) -> list[Check]:
    """The share of the session's bars whose ticker the resolver did not know (the latest
    bars run for the session); nothing when the session's bars were stored earlier."""
    runs = [r for r in reader.runs(BARS_TASK, session) if r.finished_at is not None]
    rows = _rows(reader, "bars/1d", session)
    if not runs or not rows:
        return []
    latest = max(runs, key=lambda r: r.finished_at or r.started_at)
    unresolved = int(latest.stats.get("unresolved", 0))
    share = unresolved / rows
    return [
        Check(
            "bars_resolved",
            "FAIL" if share > s.max_bar_unresolved else "PASS",
            f"{unresolved} of {rows} bars unresolved ({share:.1%}, max {s.max_bar_unresolved:.0%})",
        )
    ]


def check_universe(reader: StoreReader, session: date, s: SourcesSettings) -> list[Check]:
    latest = _latest(reader, "universe", session)
    if latest is None:
        return [Check("universe_present", "FAIL", "no universe snapshot")]
    today, before = (
        _rows(reader, "universe", latest),
        _rows(reader, "universe", _previous(reader, "universe", latest)),
    )
    if not today:
        return [Check("universe_present", "FAIL", f"empty universe on {latest}")]
    if not before:
        return [Check("universe_size", "PASS", f"{today} instruments (no earlier snapshot)")]
    change = today / before - 1
    status = "FAIL" if abs(change) > s.max_universe_change else "PASS"
    return [
        Check(
            "universe_size",
            status,
            f"{today} vs {before} instruments ({change:+.1%}); "
            "an unexplained jump means UNIVERSE INCOMPLETE",
        )
    ]


# Chain statuses (``tasks/market/option_chains``) by what they say about the night's fetch:
# a failed or missing fetch is a source problem (FAIL); a stale chain is the feed serving an
# older session (FAIL above the share: a later retry usually gets the session's chains); the
# rest are answers.
FETCH_FAILURES = ("FETCH_ERROR", "NOT_ATTEMPTED")  # FETCH_ERROR includes an open circuit
STALE = "STALE_DATA"
REPORTED = ("OK", "STALE_DATA", "NO_CHAIN", "NO_STANDARD_SERIES")


def check_chains(reader: StoreReader, session: date, s: SourcesSettings) -> list[Check]:
    status_frame = chain_status(reader, session)
    if status_frame is None or status_frame.empty:
        return [Check("chains_present", "FAIL", f"no option chains for {session}")]
    labels = status_frame["status"].astype(str).str.split(":", n=1).str[0].str.strip()
    total = len(labels)
    counts = labels.value_counts()
    failed = int(labels.isin(FETCH_FAILURES).sum())
    stale = int(counts.get(STALE, 0))
    breakdown = ", ".join(f"{k} {int(counts.get(k, 0))}" for k in REPORTED)
    detail = f"of {total} underlyings: {breakdown}, fetch failures {failed}"
    return [
        Check(
            "chains_fetch",
            "FAIL" if failed / total > s.max_chain_fetch_failures else "PASS",
            f"{failed / total:.1%} failed to fetch "
            f"(max {s.max_chain_fetch_failures:.0%}); {detail}",
        ),
        Check(
            "chains_stale",
            "FAIL" if stale / total > s.max_chain_stale_share else "PASS",
            f"{stale / total:.1%} stale (max {s.max_chain_stale_share:.0%}); {detail}",
            pending=True,  # Cboe has not rolled to the session yet (ADR 0043)
        ),
    ]


def check_earnings(reader: StoreReader, session: date, s: SourcesSettings) -> list[Check]:
    rows = _rows(reader, "events/earnings", _latest(reader, "events/earnings", session))
    if not rows:
        return [Check("earnings_present", "FAIL", "no earnings calendar stored")]
    return [Check("earnings_present", "PASS", f"{rows} upcoming earnings rows")]


VERIFICATION = "verification/ibkr"
GRADED = ("PASS", "WARN", "FAIL")  # NA checks (either side without a value) are not graded


def check_verification(reader: StoreReader, session: date, s: SourcesSettings) -> list[Check]:
    """The live verification vs IBKR (``verify``): FAIL above ``max_verify_failures`` of the
    graded checks failing, WARN on any FAIL. Nothing when ``[ibkr]`` is disabled."""
    if not s.vendor("ibkr").enabled:
        return []
    frame = reader.table(VERIFICATION, session)
    if frame is None or frame.empty:
        return [
            Check(
                "verification",
                "WARN",
                f"no verification vs IBKR for {session} (IB Gateway not reachable?)",
            )
        ]
    counts = frame["status"].astype(str).value_counts()
    graded = sum(int(counts.get(k, 0)) for k in GRADED)
    failed = int(counts.get("FAIL", 0))
    share = failed / graded if graded else 0.0
    status = "FAIL" if share > s.max_verify_failures else "WARN" if failed else "PASS"
    breakdown = ", ".join(f"{k} {int(counts.get(k, 0))}" for k in (*GRADED, "NA"))
    names = frame.loc[frame["status"] == "FAIL", "symbol"].astype(str).unique()[:5]
    worst = f"; failing: {', '.join(names)}" if failed else ""
    return [
        Check(
            "verification",
            status,
            f"{share:.1%} of {graded} graded checks failed vs IBKR "
            f"(max {s.max_verify_failures:.0%}); {breakdown}{worst}",
        )
    ]


CHECKS: tuple[Callable[[StoreReader, date, SourcesSettings], list[Check]], ...] = (
    check_universe,
    check_bars,
    check_bars_resolved,
    check_chains,
    check_earnings,
    check_verification,
)


def run_quality(ctx: TaskContext, session: date) -> RunRecord:
    with IngestRun(ctx, TASK, session) as run:
        checks = [c for fn in CHECKS for c in fn(ctx.reader, session, ctx.settings)]
        for check in checks:
            run.record_item(check.name, check.status)
        failed = [c.name for c in checks if c.status == "FAIL"]
        for name in failed:
            run.partial(f"check {name} failed")
        run.stats.update(checks=[asdict(c) for c in checks], failed=failed)
    return run.record
