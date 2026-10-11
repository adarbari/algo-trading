"""The result an edge's verdict rests on, for the sections of its page (ADR 0064, 0065): the
OFFICIAL run (a site edge's canonical run; a user's own edge's latest run) and the basis
``(screen, holding period)`` the verdict rule fixed on it, fixed before the out-of-sample period
is read (``versions.basis_of``: declared, else the best in-sample). Every section of the page
reads this one choice, so the curve, the drawdown and the decay can never be about another
candidate than the verdict: a section never re-chooses.

A hidden copy's basis is chosen from the in-sample rows it is served (``runs.load_run_rows``), so
showing the result never moves it. No official run, or none that fixes a basis, is ``NOT_RUN``
with the reason; the cause is the admin's."""

from dataclasses import dataclass
from datetime import date

from algotrade.config.edges.document import job_name
from algotrade.services.read.availability.cause import run_cause
from algotrade.services.read.context import Stores
from algotrade.services.read.evaluation import runs, versions
from algotrade.services.read.evaluation.edges import Edge
from algotrade.services.read.evaluation.runs import EdgeRun
from algotrade.services.read.values import Unknown, UnknownCode


@dataclass(frozen=True)
class OfficialBasis:
    """The official ``run`` of ``edge`` and its basis ``key`` (screen, holding period);
    ``split_from`` the run's split (the edge's frozen period for a run that recorded none);
    ``hidden``: the run's out-of-sample result is withheld. ``unknown`` says why there is no run
    or no basis (``key`` is then None)."""

    edge: Edge
    run: EdgeRun | None
    key: tuple[str, int] | None
    split_from: date | None
    hidden: bool
    unknown: Unknown | None = None


@dataclass(frozen=True)
class BasisSummary:
    """What a page is told of the basis: the ``run_id`` it reads, the ``variant`` (screen) and
    ``horizon_sessions`` it rests on (None with no basis: ``unknown`` says why), the run's
    ``split_from`` and whether its out-of-sample result is withheld (``oos_hidden``)."""

    run_id: str | None
    variant: str | None
    horizon_sessions: int | None
    split_from: date | None
    oos_hidden: bool
    unknown: Unknown | None


def summary_of(basis: OfficialBasis) -> BasisSummary:
    """``basis`` as served."""
    key = basis.key
    return BasisSummary(
        run_id=basis.run.run_id if basis.run is not None else None,
        variant=key[0] if key is not None else None,
        horizon_sessions=key[1] if key is not None else None,
        split_from=basis.split_from,
        oos_hidden=basis.hidden,
        unknown=basis.unknown,
    )


def official_basis(ctx: Stores, edge: Edge) -> OfficialBasis:
    """The official run of ``edge`` and the basis of its verdict, from the rows the user is
    served; the same run and basis ``versions.load_verdict`` judges."""
    absent: Unknown | None
    if edge.mine:
        run = versions.own_run(ctx, edge)
        absent = Unknown(
            UnknownCode.NOT_RUN,
            run_cause(job_name(edge.id, ctx.user.user_id), "You have not run this edge yet"),
        )
    else:
        canonical = runs.load_canonical_run(ctx, edge)
        run, absent = canonical.run, canonical.not_run
    if run is None:
        return OfficialBasis(edge, None, None, edge.frozen_from, edge.oos_hidden, absent)
    choice = versions.basis_of(ctx, edge, runs.load_run_rows(ctx, run))
    split = run.split_from or edge.frozen_from
    if choice.key is None:
        why = Unknown(
            UnknownCode.NOT_RUN,
            run_cause(job_name(edge.id, run.owner), f"{run.run_id}: {choice.reason}"),
        )
        return OfficialBasis(edge, run, None, split, run.oos_hidden, why)
    return OfficialBasis(edge, run, choice.key, split, run.oos_hidden)
