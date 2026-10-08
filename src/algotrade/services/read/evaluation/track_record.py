"""A screener's track records (``TrackRecord``), one per edge that lists it: what the frozen
period says about it, from that edge's canonical run, and nothing else.

Only the ``frozen`` slice of a canonical run (its split is the edge's ``frozen_from``) feeds it:
an exploratory run, whatever its split, never reaches it. An edge with no canonical run, or a run
without rows for the screener, yields a ``NOT_RUN`` entry with the reason, never an older value.
Outcomes are not read here: the numbers are the stored rows of ``results/edge_eval``."""

from dataclasses import dataclass
from datetime import date, datetime

from algotrade.services.read.availability.cause import run_cause
from algotrade.services.read.context import Stores
from algotrade.services.read.evaluation import runs
from algotrade.services.read.evaluation.edges import Edge, load_edges
from algotrade.services.read.values import Unknown, UnknownCode

FROZEN = "frozen"


@dataclass(frozen=True)
class TrackHorizon:
    """The frozen slice at one horizon: hit rate against the base rate, the lift, the
    independent sessions behind them and the picks counted."""

    horizon_sessions: int
    hit_rate: float | None
    base_rate: float | None
    lift: float | None
    sessions: int | None
    picks: int | None


@dataclass(frozen=True)
class TrackRecord:
    """A screener's frozen-period record under one edge that lists it. With a canonical run
    and frozen rows: ``run_id`` .. ``horizons`` are set and ``not_run`` is None (``run_label``
    names the run). Otherwise ``not_run`` says why (``NOT_RUN``) and the rest is empty."""

    screener_id: str
    edge_id: str
    edge_name: str
    not_run: Unknown | None = None
    run_id: str | None = None
    run_label: str | None = None
    range_from: date | None = None
    range_to: date | None = None
    split_from: date | None = None
    knowledge_ts: datetime | None = None
    horizons: tuple[TrackHorizon, ...] = ()


def _horizon(row: runs.EdgeRow) -> TrackHorizon:
    return TrackHorizon(
        horizon_sessions=row.horizon_sessions,
        hit_rate=row.hit_rate,
        base_rate=row.base_rate,
        lift=row.lift,
        sessions=row.sessions,
        picks=row.picks,
    )


def _from(ctx: Stores, edge: Edge, screener_id: str) -> TrackRecord:
    found = runs.load_canonical_run(ctx, edge)
    if found.run is None:
        return TrackRecord(screener_id, edge.id, edge.name, not_run=found.not_run)
    run = found.run
    rows = [
        r
        for r in runs.load_run_rows(ctx, run)
        if r.variant == screener_id
        and r.role == "screener"
        and r.edge_variant == runs.MAIN
        and r.slice_kind == FROZEN
        and not r.exploratory
    ]
    if not rows:
        why = f"run {run.run_id} of {edge.id} has no frozen rows for {screener_id}"
        cause = run_cause(screener_id, why)
        return TrackRecord(
            screener_id, edge.id, edge.name, not_run=Unknown(UnknownCode.NOT_RUN, cause)
        )
    return TrackRecord(
        screener_id=screener_id,
        edge_id=edge.id,
        edge_name=edge.name,
        run_id=run.run_id,
        run_label=f"{edge.id} from {run.split_from} to {run.range_to}",
        range_from=run.range_from,
        range_to=run.range_to,
        split_from=run.split_from,
        knowledge_ts=run.knowledge_ts,
        horizons=tuple(sorted((_horizon(r) for r in rows), key=lambda h: h.horizon_sessions)),
    )


def load_track_records(ctx: Stores, screener_id: str) -> tuple[TrackRecord, ...]:
    """One entry per edge (by id) that lists ``screener_id``; none when no edge does."""
    return tuple(_from(ctx, e, screener_id) for e in load_edges(ctx) if screener_id in e.screeners)
