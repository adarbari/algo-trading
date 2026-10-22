"""``screen-runs-backfill``: frame ``results/screen_runs`` (ScreenRun) and ``results/screen_picks``
(ScreenPick) for the rule-screen runs stored before those tables existed (ADR 0077 amendment (c);
data architecture v2 phase 5), from each run's own ``results/rule_screen`` rows and its run record,
so a reader can use the frozen rows for an old session instead of recomputing them.

One run is one atomic publish through the live path's ``ResultWriter.publishing`` and the same
framer (``services/screening/rule_results.stored_run_frames``), under the original run id and
with the original ``knowledge_ts`` (point in time: the rows were knowable when the run ended,
never "now"; the commit is stamped with it, as the live publish is). The previous run a run's
changes are counted against is the live one (``services/screening/previous.previous_lineage``).

- Idempotent and resumable by the store itself: a run that has its ``screen_runs`` row is
  skipped (its counts are only checked against ``rule_screen``'s: a difference is reported as a
  ``MISMATCH`` item, never overwritten), so a run cut short, or one limited by ``--limit``, is
  finished by running it again.
- A run whose own rows disagree with its run record's summary, or whose rows carry two versions
  or the record's version disagrees, is reported as a ``MISMATCH`` and framed from nothing.
- A version neither the rows nor the record give is stored null and listed
  (``version_unknown``), never guessed.
- Runs under the ingest run lock and the lowered priority every ingest command takes
  (``cli/main.py``), so it never overlaps the nightly; progress is saved to the run record after
  each session. Acceptance check: per session, each (user, config)'s latest run has a row whose
  rows and picked counts equal ``rule_screen``'s; a session that fails it is listed.
"""

from collections import Counter
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd

from algotrade.data import StoreReader
from algotrade.services.screening.previous import previous_lineage
from algotrade.services.screening.rule_results import (
    RULE_SCREEN,
    SCREEN_PICKS,
    SCREEN_RUNS,
    Stamp,
    counts_of,
    is_picked,
    stored_run_frames,
)
from algotrade.services.screening.run import run_job_name
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.schemas import result_table
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext

TASK = "screen_runs_backfill"
SHOWN = 20  # mismatches and unframed sessions listed in the run's stats
SCREEN_TABLE = result_table(RULE_SCREEN)
RUNS_TABLE = result_table(SCREEN_RUNS)
PICKS_TABLE = result_table(SCREEN_PICKS)
GROUP = ("user_id", "config_id")


class MismatchError(Exception):
    """A run whose stored rows, run record and frozen row do not agree (reported, not fixed)."""


def _unique(screen: pd.DataFrame, column: str) -> Any:
    values = screen[column].dropna().unique()
    if len(values) > 1:
        raise MismatchError(
            f"{column} has {len(values)} values in one run: {sorted(map(str, values))}"
        )
    return values[0] if len(values) else None


def _version(screen: pd.DataFrame, record: RunRecord | None) -> tuple[int | None, str | None]:
    """The run's config version and, when unknown, why: the rows' (every row of a run carries
    its stamp's) checked against the run record's; the record's alone when the rows have none."""
    found = _unique(screen, "config_version")
    from_record = record.stats.get("config_version") if record is not None else None
    if found is not None and from_record is not None and int(found) != int(from_record):
        raise MismatchError(f"config_version {found} in the rows, {from_record} in the run record")
    if found is not None:
        return int(found), None
    if from_record is not None:
        return int(from_record), None
    return None, "no version in the rows and " + (
        "none in the run record" if record is not None else "no run record"
    )


def _check_summary(screen: pd.DataFrame, record: RunRecord | None) -> None:
    """The run record's summary (``stats["summary"]``) must equal what the rows count."""
    summary = record.stats.get("summary") if record is not None else None
    if not summary:
        return
    rows, passed, decisions = counts_of(screen)
    if (summary.get("rows"), summary.get("passed"), summary.get("decisions")) != (
        rows,
        passed,
        decisions,
    ):
        raise MismatchError(
            f"run record summary {summary.get('rows')} rows / {summary.get('passed')} passed / "
            f"{summary.get('decisions')} differs from rule_screen's {rows} / {passed} / {decisions}"
        )


def _stamp(screen: pd.DataFrame, day: date, record: RunRecord | None) -> tuple[Stamp, str | None]:
    knowledge = pd.Timestamp(_unique(screen, "knowledge_ts"))
    if knowledge.tzinfo is None:
        knowledge = knowledge.tz_localize("UTC")
    version, reason = _version(screen, record)
    size = _unique(screen, "size_multiplier")
    regime = _unique(screen, "regime")
    stamp = Stamp(
        day,
        str(_unique(screen, "run_id")),
        knowledge.to_pydatetime(),
        str(_unique(screen, "user_id")),
        str(_unique(screen, "config_id")),
        str(_unique(screen, "config_hash")),
        version,
        None if regime is None else str(regime),
        None if size is None else float(size),
    )
    return stamp, reason


def _verify_framed(screen: pd.DataFrame, framed: pd.DataFrame) -> None:
    """A run that already has its row: the row's counts must be rule_screen's."""
    rows, passed, decisions = counts_of(screen)
    picked = sum(n for d, n in decisions.items() if is_picked(d))
    (row,) = framed.to_dict("records")
    have = (row["rows"], row["passed"], row["picked"])
    if have != (rows, passed, picked):
        raise MismatchError(
            f"screen_runs has rows/passed/picked {have}, rule_screen's are {(rows, passed, picked)}"
        )


def _candidates(
    reader: StoreReader, day: date, latest: pd.DataFrame
) -> list[tuple[str, RunRecord | None]]:
    """Every run of the session with rows, oldest first: the newest of each (user, config) group
    of ``results/rule_screen`` and each run record of the group's screen job."""
    found: dict[str, RunRecord | None] = {}
    groups = latest[list(GROUP)].drop_duplicates().itertuples(index=False, name=None)
    for user, config in groups:
        for record in reader.runs(run_job_name(str(config), str(user)), day):
            found[record.run_id] = record
    for run_id in latest["run_id"].astype(str).unique():
        found.setdefault(run_id, None)
    floor = datetime.min.replace(tzinfo=UTC)
    return sorted(found.items(), key=lambda kv: (kv[1].started_at if kv[1] else floor, kv[0]))


def _acceptance(reader: StoreReader, day: date, latest: pd.DataFrame) -> str | None:
    """Per (user, config), the latest run's ``screen_runs`` row must count the rows and picks
    ``rule_screen`` has; -> what differs, or None."""
    framed = reader.read_latest_runs(RUNS_TABLE, day, GROUP)
    wanted: dict[tuple[Any, ...], tuple[int, int]] = {
        (*key,): (len(rows), int(rows["decision"].astype(str).map(is_picked).sum()))
        for key, rows in latest.groupby(list(GROUP))
    }
    have: dict[tuple[Any, ...], tuple[int, int]] = (
        {}
        if framed is None
        else {
            (r["user_id"], r["config_id"]): (int(r["rows"]), int(r["picked"]))
            for r in framed.to_dict("records")
        }
    )
    differ = sorted(k for k in wanted if have.get(k) != wanted[k])
    return None if not differ else f"{len(differ)} of {len(wanted)} runs, first {differ[0]}"


class _Pass:
    """One backfill run's state: what each run did, and what to report."""

    def __init__(self, run: IngestRun, limit: int | None) -> None:
        self.run, self.limit = run, limit
        self.counts: Counter[str] = Counter()
        self.mismatches: list[str] = []
        self.unknown_version: list[str] = []
        self.unframed: list[str] = []

    def frame(self, day: date, run_id: str, record: RunRecord | None) -> None:
        """Frame one run (or note why not): its own rows and record in, one publish out."""
        run, reader, writer = self.run, self.run.ctx.reader, self.run.writer
        key = f"{day.isoformat()}/{run_id}"
        screen = reader.read_run(SCREEN_TABLE, day, run_id)
        if screen is None or screen.empty:  # superseded in its group: its file is gone
            return self._note(key, "NO_ROWS", "no_rows")
        try:
            framed = reader.read_run(RUNS_TABLE, day, run_id)
            if framed is not None:
                _verify_framed(screen, framed)
                return self._note(key, "ALREADY_FRAMED", "already_framed")
            if self.limit is not None and self.counts["framed"] >= self.limit:
                return self._note(key, "NOT_REACHED", "not_reached")
            _check_summary(screen, record)
            stamp, why = _stamp(screen, day, record)
            job = run_job_name(stamp.config_id, stamp.user_id)
            frames = stored_run_frames(screen, stamp, previous_lineage(reader, job, day))
            with writer.publishing(run_id, stamp.knowledge_ts):  # both tables or none
                for name in (SCREEN_RUNS, SCREEN_PICKS):
                    writer.write_result(name, day, run_id, frames[name], pending=True)
        except MismatchError as exc:
            self.mismatches.append(f"{key}: {exc}")
            return self._note(key, f"MISMATCH: {exc}", "mismatch")
        except Exception as exc:  # one run's failure never stops the others
            return run.fail(key, f"{type(exc).__name__}: {exc}", kind="FAILED")
        if why is not None:
            self.unknown_version.append(f"{key}: {why}")
        return self._note(key, "OK" if why is None else "OK: version unknown", "framed")

    def _note(self, key: str, status: str, count: str) -> None:
        self.run.record_item(key, status)
        self.counts[count] += 1

    def finish(self, days: list[date], start: date | None, end: date | None) -> None:
        run, counts = self.run, self.counts
        run.stats.update(counts)
        run.stats.update(
            window=[start and start.isoformat(), end and end.isoformat()],
            first=days[0].isoformat() if days else None,
            last=days[-1].isoformat() if days else None,
            sessions=len(days),
            limit=self.limit,
            mismatches=self.mismatches[:SHOWN],
            version_unknown=self.unknown_version[:SHOWN],
            version_unknown_count=len(self.unknown_version),
            unframed=self.unframed[:SHOWN],
            unframed_count=len(self.unframed),
        )
        if self.mismatches:
            run.partial(f"{len(self.mismatches)} runs disagree with rule_screen (not written)")
        if counts["not_reached"]:
            run.partial(f"{counts['not_reached']} runs left by --limit: run it again to continue")
        if self.unframed:
            run.partial(f"{len(self.unframed)} sessions fail the counts check against rule_screen")


def backfill_screen_runs(
    ctx: TaskContext, start: date | None, end: date | None, limit: int | None
) -> RunRecord:
    """Frame every stored rule-screen run of the sessions in [``start``, ``end``] (default: all)
    that has no ``screen_runs`` row, at most ``limit`` runs this run, oldest session first."""
    reader = ctx.reader
    days = [d for d in reader.dates(SCREEN_TABLE) if (start or d) <= d <= (end or d)]
    with IngestRun(ctx, TASK, days[-1] if days else (end or ctx.clock().date())) as run:
        work = _Pass(run, limit)
        for index, day in enumerate(days):
            latest = reader.read_latest_runs(SCREEN_TABLE, day, GROUP, ("decision",))
            if latest is None or latest.empty:
                continue
            left = work.counts["not_reached"]
            for run_id, record in _candidates(reader, day, latest):
                work.frame(day, run_id, record)
            if work.counts["not_reached"] == left:  # a session --limit cut short is not checked yet
                problem = _acceptance(reader, day, latest)
                if problem:
                    work.unframed.append(f"{day.isoformat()}: {problem}")
            run.stats["progress"] = {
                "sessions_done": index + 1,
                "sessions": len(days),
                "last": day.isoformat(),
            }
            run.stats.update(work.counts)
            run.checkpoint()
        work.finish(days, start, end)
    return run.record
