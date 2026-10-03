"""Nightly data-quality checks: fail loudly instead of screening on bad or missing data.

Each check is PASS, WARN or FAIL with a detail line; any FAIL makes the run PARTIAL (and the
nightly job PARTIAL). Thresholds come from ``config/site/sources.toml`` ``[quality]``.
"""

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime

from algotrade.data import StoreReader
from algotrade.data.chains import chain_status
from algotrade.data.reference import snapshot
from algotrade.storage.runs import RunRecord, RunStatus, new_run_id
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.settings import SourcesSettings

JOB = "data_quality"


@dataclass(frozen=True)
class Check:
    name: str
    status: str  # PASS | WARN | FAIL
    detail: str


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


def check_bars(reader: StoreReader, session: date, s: SourcesSettings) -> list[Check]:
    latest = _latest(reader, "bars/1d", session)
    if latest is None:
        return [Check("bars_present", "WARN", "no bars stored yet (backfill not run)")]
    checks = [
        Check(
            "bars_fresh",
            "PASS" if latest == session else "FAIL",
            f"latest bars session {latest}, expected {session}",
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


def check_chains(reader: StoreReader, session: date, s: SourcesSettings) -> list[Check]:
    status_frame = chain_status(reader, session)
    if status_frame is None or status_frame.empty:
        return [Check("chains_present", "WARN", f"no option chains for {session}")]
    ok = status_frame["status"].isin(["OK", "NO_STANDARD_SERIES"]).mean()
    verdict = "FAIL" if ok < s.min_chain_coverage else "PASS"
    return [
        Check(
            "chains_coverage",
            verdict,
            f"{ok:.1%} of {len(status_frame)} underlyings returned a chain",
        )
    ]


def check_earnings(reader: StoreReader, session: date, s: SourcesSettings) -> list[Check]:
    rows = _rows(reader, "events/earnings", _latest(reader, "events/earnings", session))
    if not rows:
        return [Check("earnings_present", "WARN", "no earnings calendar stored")]
    return [Check("earnings_present", "PASS", f"{rows} upcoming earnings rows")]


CHECKS: tuple[Callable[[StoreReader, date, SourcesSettings], list[Check]], ...] = (
    check_universe,
    check_bars,
    check_chains,
    check_earnings,
)


def run_quality(
    reader: StoreReader,
    writer: StoreWriter,
    session: date,
    settings: SourcesSettings,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> RunRecord:
    now = clock()
    checks = [c for fn in CHECKS for c in fn(reader, session, settings)]
    failed = [c.name for c in checks if c.status == "FAIL"]
    record = RunRecord(
        new_run_id(JOB, session, now),
        JOB,
        session,
        now,
        RunStatus.PARTIAL if failed else RunStatus.COMPLETE,
        now,
        stats={"checks": [asdict(c) for c in checks], "failed": failed},
    )
    writer.save_run(record)
    return record
