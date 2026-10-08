"""The evaluation runs of an edge (``EdgeRun``) and their rows (``EdgeRow``).

``results/edge_eval`` is partitioned by the range end, so it is read by run, as ``Backtest``
is: the run records ``edge-eval:<edge>:<user>`` (committed: COMPLETE) and each run's own rows
in its partition (``context.run_partition``: only that run's rows, never another run of the
same range end). Every run discloses its ``run_id``, range, ``split_from``, ``knowledge_ts`` and
``as_of``; a run whose split is not the edge's ``frozen_from`` is ``exploratory``. The
canonical run of an edge is the latest committed run of the site user whose split is its
``frozen_from``: none is ``NOT_RUN`` with the reason, never an older or exploratory run."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from algotrade.config.edges.document import job_name
from algotrade.config.user import SITE_USER
from algotrade.services.read.availability.cause import run_cause
from algotrade.services.read.context import ReadContext, Stores, run_partition
from algotrade.services.read.evaluation.edges import Edge, load_edges
from algotrade.services.read.values import Unknown, UnknownCode, to_scalar
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade.storage.tables.schemas import result_table

EDGE_EVAL = "edge_eval"
MAIN = "main"


@dataclass(frozen=True)
class EdgeRun:
    """One committed evaluation run. ``owner``: whose run (the user's id, or ``site``);
    ``range_from`` / ``range_to``: the sessions it covered; ``split_from``: the split the
    frozen slice was measured at (None: a run from before splits were recorded);
    ``exploratory``: its split is not the edge's ``frozen_from``; ``knowledge_ts``: when it
    committed; ``as_of``: the data version it read (ISO); ``after_session``: it committed
    after the request's session (a session-bound read only; always False without one): its
    numbers were not knowable on that session."""

    run_id: str
    edge_id: str
    owner: str
    status: str
    range_from: date | None
    range_to: date
    split_from: date | None
    exploratory: bool
    knowledge_ts: datetime
    as_of: str | None
    trials_counted: int | None
    after_session: bool = False


@dataclass(frozen=True)
class EdgeRow:
    """One stored row of a run: a screener or baseline (``variant``, its ``role``) of an edge
    variant (``main`` for the edge itself) over a horizon, for one slice (``all``, ``year``,
    ``regime``, ``frozen`` or ``split``). A number not stored is None."""

    edge_variant: str
    variant: str
    role: str
    horizon_sessions: int
    slice_kind: str
    slice_value: str
    sessions: int | None
    picks: int | None
    hits: int | None
    trials: int | None
    pre_snapshot_sessions: int | None
    hit_rate: float | None
    base_rate: float | None
    lift: float | None
    mean_excess_picks: float | None
    decile_spread: float | None
    decile_t: float | None
    effect_size: float | None
    sharpe: float | None
    deflated_sharpe: float | None
    pbo: float | None
    exploratory: bool = False
    decile_sessions: int | None = None
    in_sample: bool = False  # a model screener's score was fitted on sessions of this slice


@dataclass(frozen=True)
class CanonicalRun:
    """The canonical run of an edge, or why it has none (``not_run``: ``NOT_RUN``)."""

    run: EdgeRun | None
    not_run: Unknown | None


def _day(value: Any) -> date | None:
    return date.fromisoformat(value) if value else None


def _run(ctx: Stores, record: RunRecord, edge: Edge, owner: str) -> EdgeRun:
    stats = record.stats
    frozen_from = edge.frozen_from
    committed = record.finished_at or record.started_at
    session = ctx.session.date if isinstance(ctx, ReadContext) else None
    split = _day(stats.get("split_from"))
    start = (stats.get("range") or [None])[0]
    return EdgeRun(
        run_id=record.run_id,
        edge_id=edge.id,
        owner=owner,
        status=record.status.value,
        range_from=_day(start),
        range_to=record.session_date,
        split_from=split,
        exploratory=split != frozen_from or bool(stats.get("exploratory")),
        knowledge_ts=committed,
        as_of=stats.get("as_of"),
        trials_counted=stats.get("trials_counted"),
        after_session=session is not None and committed.date() > session,
    )


def _committed(ctx: Stores, edge: Edge, owner: str) -> list[EdgeRun]:
    records = ctx.reader.runs(job_name(edge.id, owner))
    done = [r for r in records if r.status is RunStatus.COMPLETE]
    ordered = sorted(done, key=lambda r: r.finished_at or r.started_at, reverse=True)
    return [_run(ctx, r, edge, owner) for r in ordered]


def load_edge_runs(ctx: Stores, edge: Edge) -> tuple[EdgeRun, ...]:
    """Every committed run of ``edge`` the user sees (theirs, then the site's), newest first."""
    owners = dict.fromkeys([ctx.user.user_id, SITE_USER])
    runs = [r for o in owners for r in _committed(ctx, edge, o)]
    return tuple(sorted(runs, key=lambda r: r.knowledge_ts, reverse=True))


def load_runs_of(ctx: Stores, edge_id: str) -> tuple[EdgeRun, ...]:
    """``load_edge_runs`` by edge id; none for an edge the user does not have."""
    edge = next((e for e in load_edges(ctx) if e.id == edge_id), None)
    return load_edge_runs(ctx, edge) if edge is not None else ()


def load_canonical_run(ctx: Stores, edge: Edge) -> CanonicalRun:
    """The latest committed run of the site user whose split is ``edge.frozen_from``; else
    ``NOT_RUN`` (no frozen period, or no run at it): never an exploratory or older split."""
    job = job_name(edge.id, SITE_USER)
    if edge.frozen_from is None:
        why = f"{edge.id} has no frozen period, so no run is canonical"
    else:
        found = [r for r in _committed(ctx, edge, SITE_USER) if not r.exploratory]
        if found:
            return CanonicalRun(found[0], None)
        why = f"{edge.id} has no committed run at its frozen period from {edge.frozen_from}"
    return CanonicalRun(None, Unknown(UnknownCode.NOT_RUN, run_cause(job, why)))


def _int(value: Any) -> int | None:
    stored = to_scalar(value)
    return int(stored) if stored is not None else None


def _float(value: Any) -> float | None:
    stored = to_scalar(value)
    return float(stored) if stored is not None else None


def _row(row: Mapping[str, Any]) -> EdgeRow:
    return EdgeRow(
        edge_variant=str(to_scalar(row.get("edge_variant")) or MAIN),  # a null is NaN in a frame
        variant=str(row["variant"]),
        role=str(row["role"]),
        horizon_sessions=int(row["horizon_sessions"]),
        slice_kind=str(row["slice_kind"]),
        slice_value=str(row["slice_value"]),
        sessions=_int(row.get("sessions")),
        picks=_int(row.get("picks")),
        hits=_int(row.get("hits")),
        trials=_int(row.get("trials")),
        pre_snapshot_sessions=_int(row.get("pre_snapshot_sessions")),
        hit_rate=_float(row.get("hit_rate")),
        base_rate=_float(row.get("base_rate")),
        lift=_float(row.get("lift")),
        mean_excess_picks=_float(row.get("mean_excess_picks")),
        decile_spread=_float(row.get("decile_spread")),
        decile_t=_float(row.get("decile_t")),
        effect_size=_float(row.get("effect_size")),
        sharpe=_float(row.get("sharpe")),
        deflated_sharpe=_float(row.get("deflated_sharpe")),
        pbo=_float(row.get("pbo")),
        exploratory=to_scalar(row.get("exploratory")) is True,
        decile_sessions=_int(row.get("decile_sessions")),
        in_sample=to_scalar(row.get("in_sample")) is True,
    )


def load_run_rows(ctx: Stores, run: EdgeRun) -> tuple[EdgeRow, ...]:
    """The rows ``run`` wrote, as it left them; none when its partition holds none of its own."""
    record = ctx.reader.run(run.run_id)
    if record is None:
        return ()
    frame = run_partition(ctx, result_table(EDGE_EVAL), record)
    if frame is None:
        return ()
    return tuple(_row({str(k): v for k, v in r.items()}) for r in frame.to_dict("records"))
