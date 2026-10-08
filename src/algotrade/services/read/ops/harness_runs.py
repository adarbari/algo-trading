"""The edge evaluation runs for the Admin "Harness runs" tab (``HarnessRun``): every run record
``edge-eval:<edge>:<user>`` of every edge the admin sees and every declared user (and the site),
of any status, newest first, with what each run measured and what it left out, and one run's rows.

Run records, not session data: the loaders take the session-free ``Stores`` context. Everything
listed is what the run recorded in its own stats (the trial log the harness wrote with it); a
figure the record does not hold is ``None``, never 0. The run's rows are the ones the Edges page
reads (``read/evaluation/runs.py``): the run's own partition, by run id."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from algotrade.config.edges.document import job_name
from algotrade.config.site.settings import load_users
from algotrade.config.user import SITE_USER
from algotrade.services.read.context import Stores
from algotrade.services.read.evaluation.edges import load_edges
from algotrade.services.read.evaluation.runs import EdgeRow, rows_of_record
from algotrade.storage.runs import RunRecord

PREFIX = "edge-eval:"


@dataclass(frozen=True)
class LostInput:
    """An input table a variant had no data in at ``horizon``: ``sessions`` decision sessions
    lost to it (counted as unmeasured, never a miss). ``variant``: ``<edge variant>/<screener>``."""

    variant: str
    horizon: int
    table: str
    sessions: int


@dataclass(frozen=True)
class HarnessRun:
    """One evaluation run. ``user``: whose run (``site`` for the shared one); ``split_from``:
    the split its frozen slice was measured at; ``exploratory``: the run says so; ``variants``
    and ``horizons``: what it measured; ``sessions``: the most sessions any variant measured;
    ``unclosed``: decision blocks with no closed window (summed over horizons);
    ``excluded_coverage``: sessions left out for lack of a screen run or its input tables;
    ``score_coverage``: the lowest share of eligible names a variant could score;
    ``no_entry_bar``: the most names without an entry bar in one variant; ``lost_inputs``: the
    input tables each variant lacked and the sessions lost to each (empty: none recorded or
    none lost); ``trials``: the
    trials counted; ``knowledge_ts``: when it committed (its start while it has not)."""

    run_id: str
    edge_id: str
    user: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    range_from: date | None
    range_to: date
    split_from: date | None
    exploratory: bool
    variants: tuple[str, ...]
    horizons: tuple[int, ...]
    sessions: int | None
    unclosed: int | None
    excluded_coverage: int | None
    score_coverage: float | None
    no_entry_bar: int | None
    lost_inputs: tuple[LostInput, ...]
    trials: int | None
    knowledge_ts: datetime
    as_of: str | None


def _day(value: Any) -> date | None:
    return date.fromisoformat(value) if value else None


def _numbers(trials: list[dict[str, Any]], key: str) -> list[float]:
    return [t[key] for t in trials if isinstance(t.get(key), int | float)]


def _most(values: list[float]) -> int | None:
    return int(max(values)) if values else None


def _lost_inputs(trials: list[dict[str, Any]]) -> tuple[LostInput, ...]:
    """The tables the trial log records as lost (``lost_sessions``: table -> sessions)."""
    return tuple(
        LostInput(
            f"{t.get('edge_variant', 'main')}/{t['variant']}",
            int(t.get("horizon", 0)),
            str(table),
            int(n),
        )
        for t in trials
        if "variant" in t and isinstance(t.get("lost_sessions"), dict)
        for table, n in sorted(t["lost_sessions"].items())
    )


def _run(record: RunRecord, edge_id: str, user: str) -> HarnessRun:
    stats = record.stats
    trials = [t for t in stats.get("trials") or [] if isinstance(t, dict)]
    unclosed = stats.get("unclosed_sessions")
    shares = _numbers(trials, "ranked_share")
    return HarnessRun(
        run_id=record.run_id,
        edge_id=edge_id,
        user=user,
        status=record.status.value,
        started_at=record.started_at,
        finished_at=record.finished_at,
        range_from=_day((stats.get("range") or [None])[0]),
        range_to=record.session_date,
        split_from=_day(stats.get("split_from")),
        exploratory=bool(stats.get("exploratory")),
        variants=tuple(sorted({str(t["variant"]) for t in trials if "variant" in t})),
        horizons=tuple(sorted({int(t["horizon"]) for t in trials if "horizon" in t})),
        sessions=_most(_numbers(trials, "sessions")),
        unclosed=int(sum(unclosed.values())) if isinstance(unclosed, dict) else None,
        excluded_coverage=_most(_numbers(trials, "excluded_coverage")),
        score_coverage=min(shares) if shares else None,
        no_entry_bar=_most(_numbers(trials, "no_entry_bar")),
        lost_inputs=_lost_inputs(trials),
        trials=stats.get("trials_counted"),
        knowledge_ts=record.finished_at or record.started_at,
        as_of=stats.get("as_of"),
    )


def load_harness_runs(ctx: Stores, limit: int = 50) -> tuple[HarnessRun, ...]:
    """The ``limit`` most recent evaluation runs of any status, newest first: every edge the
    user sees, for the site and every declared user."""
    users = dict.fromkeys([SITE_USER, *(u.user_id for u in load_users(ctx.configs).users)])
    found = [
        _run(r, e.id, u)
        for e in load_edges(ctx)
        for u in users
        for r in ctx.reader.runs(job_name(e.id, u))
    ]
    found.sort(key=lambda r: r.started_at, reverse=True)
    return tuple(found[: max(limit, 1)])


def load_harness_run(ctx: Stores, run_id: str) -> HarnessRun | None:
    """The evaluation run ``run_id``; ``None`` when there is none (or it is another job's)."""
    try:
        record = ctx.reader.run(run_id)
    except ValueError:  # not a valid storage key
        return None
    if record is None or not record.job.startswith(PREFIX):
        return None
    edge_id, _, user = record.job.removeprefix(PREFIX).rpartition(":")
    return _run(record, edge_id, user)


def load_harness_run_rows(ctx: Stores, run_id: str) -> tuple[EdgeRow, ...] | None:
    """The rows the evaluation run ``run_id`` wrote; ``None`` when there is no such run."""
    run = load_harness_run(ctx, run_id)
    record = ctx.reader.run(run_id) if run is not None else None
    return rows_of_record(ctx, record) if record is not None else None
