"""The decoy report of an edge evaluation (ADR 0053 amendment 2026-10-18, quality bar 9): per
screener of the edge and per baseline (decoy) it was run against, how much the two hold the same
names and how much better the edge's decile spread is.

``overlap`` is the mean over the decision sessions both measured of the Jaccard index of their
pick sets at D (shared names over names in either; a session where either holds none is not
counted): near 1 the edge is the decoy under another name, near 0 it is something else. The
spreads are the top-minus-bottom decile spreads of the whole history (``spread_gap``: the edge's
less the decoy's) and of the out-of-sample slice when the run has a split (``spread_gap_oos``);
a positive gap is the part of the edge's spread the decoy does not have. Pure: it reads the
results the harness already holds."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from algotrade.services.evaluation.cross_section.measures import (
    BASELINE,
    SCREENER,
    SessionStat,
    SliceMeasure,
)

OUT_OF_SAMPLE = ("frozen", "split")  # the slice kinds of the test side of the split


class Result(Protocol):
    """What the report reads of the harness's ``VariantResult``."""

    @property
    def edge_variant(self) -> str: ...
    @property
    def horizon(self) -> int: ...
    @property
    def role(self) -> str: ...
    @property
    def variant(self) -> str: ...
    @property
    def stats(self) -> Sequence[SessionStat]: ...
    @property
    def measures(self) -> Sequence[SliceMeasure]: ...


@dataclass(frozen=True)
class DecoyOverlap:
    edge_variant: str
    horizon: int
    screener: str
    decoy: str
    sessions: int  # decision sessions with picks on both sides: what ``overlap`` averages
    overlap: float | None  # mean Jaccard of the pick sets at D; None without such a session
    spread_gap: float | None  # the screener's decile spread less the decoy's, whole history
    spread_gap_oos: float | None  # the same on the out-of-sample slice (None: no split)


def jaccard(a: Iterable[str], b: Iterable[str]) -> float | None:
    """Shared names over names in either; None when both are empty."""
    left, right = set(a), set(b)
    union = left | right
    return len(left & right) / len(union) if union else None


def mean_overlap(
    edge: Sequence[SessionStat], decoy: Sequence[SessionStat]
) -> tuple[int, float | None]:
    """``(sessions, mean Jaccard)`` over the decision sessions with picks on both sides."""
    held = {s.session: {p.instrument_id for p in s.picks} for s in decoy if s.picks}
    found = [
        jaccard({p.instrument_id for p in s.picks}, held[s.session])
        for s in edge
        if s.picks and s.session in held
    ]
    values = [v for v in found if v is not None]
    return len(values), (sum(values) / len(values) if values else None)


def _spread(measures: Sequence[SliceMeasure], kinds: tuple[str, ...]) -> float | None:
    for m in measures:
        if m.slice_kind in kinds:
            return m.decile_spread
    return None


def _gap(edge: float | None, decoy: float | None) -> float | None:
    return None if edge is None or decoy is None else edge - decoy


def decoy_overlaps(results: Sequence[Result]) -> tuple[DecoyOverlap, ...]:
    """The report rows of an evaluation's ``results`` (``VariantResult``s): every screener
    against every baseline of the same edge variant and horizon, in result order."""
    out = []
    for edge in (r for r in results if r.role == SCREENER):
        for decoy in (
            r
            for r in results
            if r.role == BASELINE
            and (r.edge_variant, r.horizon) == (edge.edge_variant, edge.horizon)
        ):
            sessions, overlap = mean_overlap(edge.stats, decoy.stats)
            out.append(
                DecoyOverlap(
                    edge.edge_variant,
                    edge.horizon,
                    edge.variant,
                    decoy.variant,
                    sessions,
                    overlap,
                    _gap(_spread(edge.measures, ("all",)), _spread(decoy.measures, ("all",))),
                    _gap(
                        _spread(edge.measures, OUT_OF_SAMPLE),
                        _spread(decoy.measures, OUT_OF_SAMPLE),
                    ),
                )
            )
    return tuple(out)
