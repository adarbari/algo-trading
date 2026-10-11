"""The variant grid of an edge: the trial log of its official run as rows (ADR 0064, ADR 0065).

One row per screen (and edge variant) and holding period the run tried, with its win rate, lift,
decile spread and independent sessions in-sample, out-of-sample and over the whole history, read
from the stored rows (never recomputed). Exactly one row is ``official``: the verdict's basis
(``basis.official_basis``, fixed before the frozen period was read). Every other row's
out-of-sample figures are shown as ``not_pre_chosen``: a result among several tried, not the test
the verdict rests on, so they cannot be read as the fair one. A hidden copy's grid carries no
out-of-sample figure (``oos_hidden``; the run reader withholds the rows)."""

from dataclasses import dataclass

from algotrade.services.read.context import Stores
from algotrade.services.read.edge_evidence.basis import official_basis
from algotrade.services.read.evaluation import runs
from algotrade.services.read.evaluation.edges import Edge, load_edge
from algotrade.services.read.evaluation.versions import OUT_OF_SAMPLE, Figures, figures_of
from algotrade.services.read.values import Unknown


@dataclass(frozen=True)
class EdgeTrial:
    """One variant (``edge_variant``: ``main`` for the edge itself) of a screen at a holding
    period; ``official``: the verdict's basis; ``not_pre_chosen``: it has out-of-sample figures
    and is not the basis; ``model_fit``: its in-sample figure is a model's training fit."""

    edge_variant: str
    variant: str
    horizon_sessions: int
    in_sample: Figures | None
    out_of_sample: Figures | None
    all: Figures | None
    official: bool
    not_pre_chosen: bool
    model_fit: bool


@dataclass(frozen=True)
class EdgeTrials:
    """The grid of ``edge`` (empty with ``unknown`` when there is no official run);
    ``basis``: the official row's screen and holding period; ``trials``: the run's trial count
    (the haircut's M); ``oos_hidden``: no out-of-sample figure is served."""

    unknown: Unknown | None
    basis: str | None = None
    trials: int | None = None
    oos_hidden: bool = False
    rows: tuple[EdgeTrial, ...] = ()


def _first(rows: list[runs.EdgeRow], kinds: tuple[str, ...]) -> runs.EdgeRow | None:
    return next((r for kind in kinds for r in rows if r.slice_kind == kind), None)


def load_edge_trials(ctx: Stores, edge: Edge) -> EdgeTrials:
    """The grid of ``edge``'s official run (ADR 0065: the basis is the verdict's, never chosen
    here)."""
    found = official_basis(ctx, edge)
    if found.run is None:
        return EdgeTrials(found.unknown)
    groups: dict[tuple[str, str, int], list[runs.EdgeRow]] = {}
    for r in runs.load_run_rows(ctx, found.run):
        if r.role != "baseline":
            groups.setdefault((r.edge_variant, r.variant, r.horizon_sessions), []).append(r)
    hidden = found.run.oos_hidden
    out: list[EdgeTrial] = []
    for (edge_variant, variant, horizon), rows in sorted(groups.items()):
        before = _first(rows, (runs.IN_SAMPLE,))
        after = None if hidden else _first(rows, OUT_OF_SAMPLE)
        whole = _first(rows, ("all",))
        official = edge_variant == runs.MAIN and found.key == (variant, horizon)
        out.append(
            EdgeTrial(
                edge_variant, variant, horizon,
                figures_of(before) if before else None,
                figures_of(after) if after else None,
                figures_of(whole) if whole else None,
                official, after is not None and not official, bool(before and before.in_sample),
            )
        )  # fmt: skip
    words = None if found.key is None else f"{found.key[0]}, {found.key[1]} trading days"
    return EdgeTrials(found.unknown, words, found.run.trials_counted, hidden, tuple(out))


def load_trials_of(ctx: Stores, edge_id: str) -> EdgeTrials | None:
    """``load_edge_trials`` for the edge ``edge_id`` the user sees (None: they see no such edge)."""
    edge = load_edge(ctx, edge_id)
    return None if edge is None else load_edge_trials(ctx, edge)
