"""Read what the nightly report needs from stored run records (read-only).

``stored_summary`` rebuilds a nightly summary for a past session from its latest ``nightly``
run record (and the ``purge-raw`` run after it), so ``algotrade-ingest report --date D``
renders the same report the nightly mailed. ``task_records`` finds, for each step of a
summary, the registry task's run record that step produced (the latest one of that task for
the session that finished inside the nightly's window); its per-item statuses feed the
failure deep dive. ``labels`` maps instrument ids in the examples to tickers.
"""

from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime, timedelta
from typing import Any

from algotrade.data import StoreReader
from algotrade.data.reference import instruments
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade_ingestion.tasks.framework.registry import TASKS
from algotrade_ingestion.workflows.nightly.report import Report, build_report
from algotrade_ingestion.workflows.nightly.sessions import NIGHTLY_RUN

PURGE_STEP = "purge-raw"
SLACK = timedelta(minutes=1)  # clock jitter between a task's record and the nightly's
# A nightly record's status as the summary shows it (ADR 0039: a session that SUCCEEDED is
# stored COMPLETE; PARTIAL only in records written before it, shown as stored).
SHOWN_STATUS = {
    RunStatus.COMPLETE: "SUCCEEDED",
    RunStatus.WAITING: "WAITING",
    RunStatus.FAILED: "FAILED",
}


def job_name(step: str) -> str | None:
    """The run-record job name of a registry task step (``chains`` -> ``option_chains``)."""
    spec = TASKS.get(step)
    name = getattr(spec.module, "TASK", None) if spec is not None else None
    return name if isinstance(name, str) else None


def latest_nightly(reader: StoreReader, session: date) -> RunRecord | None:
    """The session's most recent ``nightly`` run record (by start time)."""
    found = reader.runs(NIGHTLY_RUN, session)
    return max(found, key=lambda r: r.started_at) if found else None


def _within(record: RunRecord, start: datetime, end: datetime | None) -> bool:
    done = record.finished_at
    return done is not None and done >= start - SLACK and (end is None or done <= end + SLACK)


def _latest(
    reader: StoreReader, step: str, session: date, start: datetime, end: datetime | None
) -> RunRecord | None:
    job = job_name(step)
    if job is None:
        return None
    found = [r for r in reader.runs(job, session) if _within(r, start, end)]
    return max(found, key=lambda r: r.finished_at or r.started_at) if found else None


def stored_summary(
    reader: StoreReader, session: date, order: Sequence[str] = ()
) -> dict[str, Any] | None:
    """A nightly summary for ``session`` rebuilt from its latest nightly run record, its
    steps in ``order`` (the workflow's step names; others after them)."""
    record = latest_nightly(reader, session)
    if record is None:
        return None
    stored = record.stats.get("steps", {})
    rank = {name: i for i, name in enumerate(order)}
    steps = {k: stored[k] for k in sorted(stored, key=lambda k: (rank.get(k, len(rank)), k))}
    finished = record.finished_at or record.started_at
    final: dict[str, Any] = {}
    purge = _latest(reader, PURGE_STEP, session, finished, finished + timedelta(hours=1))
    if purge is not None:
        took = ((purge.finished_at or purge.started_at) - purge.started_at).total_seconds()
        final[PURGE_STEP] = {
            "status": "SUCCEEDED" if purge.status is RunStatus.COMPLETE else "FAILED",
            "critical": False,
            "duration_s": round(took, 3),
            "result": purge.stats,
        }
    end = (purge.finished_at if purge else None) or finished
    status = SHOWN_STATUS.get(record.status, record.status.value.upper())
    return {
        "status": status,
        "sessions": [session.isoformat()],
        "runs": [{"session": session.isoformat(), "status": status, "steps": steps}],
        "steps": final,
        "started_at": record.started_at.isoformat(),
        "finished_at": end.isoformat(),
        "duration_s": round((end - record.started_at).total_seconds(), 3),
        "warnings": [],
        "run_ids": [record.run_id],
    }


def task_records(
    reader: StoreReader, summary: Mapping[str, Any]
) -> dict[tuple[str, str], RunRecord]:
    """(session, step) -> the step's task run record; ``""`` session for the final steps."""
    out: dict[tuple[str, str], RunRecord] = {}
    for run in summary.get("runs", []):
        session = date.fromisoformat(run["session"])
        nightly = latest_nightly(reader, session)
        if nightly is None:
            continue
        for step in run.get("steps", {}):
            found = _latest(reader, step, session, nightly.started_at, nightly.finished_at)
            if found is not None:
                out[(run["session"], step)] = found
    return out


def labels(reader: StoreReader, session: date, ids: Iterable[str]) -> dict[str, str]:
    """Instrument id -> ticker for the ids that are instrument ids (best effort)."""
    wanted = sorted({i for i in ids if ":" in i})  # instrument ids (not CIKs, dates, checks)
    if not wanted:
        return {}
    try:
        frame = instruments(reader, session, wanted)
    except Exception:  # a label is a nicety; the report never fails for it
        return {}
    return {str(r.instrument_id): str(r.symbol) for r in frame.itertuples(index=False)}


def history(reader: StoreReader, before: datetime | None) -> list[dict[str, float]]:
    """Step -> seconds of each earlier nightly (any session), newest first."""
    runs = [
        r
        for r in reader.runs(NIGHTLY_RUN)
        if r.stats.get("steps") and (before is None or r.started_at < before - SLACK)
    ]
    runs.sort(key=lambda r: r.started_at, reverse=True)
    return [
        {name: float(step.get("duration_s", 0.0)) for name, step in r.stats["steps"].items()}
        for r in runs
    ]


def load_report(
    reader: StoreReader,
    summary: Mapping[str, Any],
    max_examples: int,
    max_duration_s: float | None = None,
) -> Report:
    """The report for ``summary``: its steps' task run records, examples labelled by ticker,
    timing trend against the earlier nightlies."""
    records = task_records(reader, summary)
    started = summary.get("started_at")
    past = history(reader, datetime.fromisoformat(started) if started else None)
    report = build_report(summary, records, None, max_examples, past, max_duration_s)
    keys = [e.key for g in report.failures for e in g.examples]
    names = labels(reader, date.fromisoformat(report.sessions[-1]), keys) if report.sessions else {}
    if not names:
        return report
    return build_report(summary, records, names, max_examples, past, max_duration_s)
