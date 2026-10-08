"""A screener's track record (``TrackRecord``): what the frozen period says about it, from the
canonical run of an edge that lists it, and nothing else.

Only the ``frozen`` slice of a canonical run (its split is the edge's ``frozen_from``) feeds it:
an exploratory run, whatever its split, never reaches it. A screener no edge lists, an edge with
no canonical run, or a run without rows for it is ``NOT_RUN`` / ``NO_ROW`` with the reason,
never an older value. Outcomes are not read here: the numbers are the stored rows of
``results/edge_eval``."""

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
    """A screener's frozen-period record from one canonical run: ``run_label`` names it (the
    edge and the frozen period it covers)."""

    screener_id: str
    edge_id: str
    run_id: str
    run_label: str
    range_from: date | None
    range_to: date
    split_from: date | None
    knowledge_ts: datetime
    horizons: tuple[TrackHorizon, ...]


@dataclass(frozen=True)
class LatestTrackRecord:
    """A screener's track record, or why it has none (``not_run``)."""

    record: TrackRecord | None
    not_run: Unknown | None


def _horizon(row: runs.EdgeRow) -> TrackHorizon:
    return TrackHorizon(
        horizon_sessions=row.horizon_sessions,
        hit_rate=row.hit_rate,
        base_rate=row.base_rate,
        lift=row.lift,
        sessions=row.sessions,
        picks=row.picks,
    )


def _unknown(code: UnknownCode, job: str, why: str) -> LatestTrackRecord:
    return LatestTrackRecord(None, Unknown(code, run_cause(job, why)))


def _from(ctx: Stores, edge: Edge, screener_id: str) -> LatestTrackRecord:
    found = runs.load_canonical_run(ctx, edge)
    if found.run is None:
        return LatestTrackRecord(None, found.not_run)
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
        return _unknown(UnknownCode.NOT_RUN, screener_id, why)
    label = f"{edge.id} from {run.split_from} to {run.range_to}"
    return LatestTrackRecord(
        TrackRecord(
            screener_id=screener_id,
            edge_id=edge.id,
            run_id=run.run_id,
            run_label=label,
            range_from=run.range_from,
            range_to=run.range_to,
            split_from=run.split_from,
            knowledge_ts=run.knowledge_ts,
            horizons=tuple(sorted((_horizon(r) for r in rows), key=lambda h: h.horizon_sessions)),
        ),
        None,
    )


def load_track_record(ctx: Stores, screener_id: str) -> LatestTrackRecord:
    """The track record of ``screener_id``: from the first edge (by id) that lists it as a
    screener and has frozen rows for it; else ``NOT_RUN`` with the first reason."""
    listing = [e for e in load_edges(ctx) if screener_id in e.screeners]
    if not listing:
        return _unknown(UnknownCode.NOT_RUN, screener_id, f"no edge lists {screener_id}")
    first: LatestTrackRecord | None = None
    for edge in listing:
        found = _from(ctx, edge, screener_id)
        if found.record is not None:
            return found
        first = first or found
    assert first is not None
    return first
