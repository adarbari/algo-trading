"""``EdgeRegimes`` (ADR 0064, "where it worked"): the verdict's basis in each market regime, one
row per regime label with the win rate, base rate, lift and trades the harness stored for it and
whether it is thin. The harness stores a regime over the whole run only, so a regime's
in-sample and out-of-sample figures are ``not_stored`` (said, never derived or zero). A hidden
copy's regime rows contain out-of-sample sessions and are withheld (``oos_hidden``). Read at the
verdict's own basis (``edge_evidence.basis``), never re-chosen."""

from dataclasses import dataclass

from algotrade.config.site.settings import load_verdict
from algotrade.features.rollups.market.regime import LABELS
from algotrade.services.read.context import Stores
from algotrade.services.read.edge_evidence.basis import OfficialBasis
from algotrade.services.read.edge_evidence.costs import (
    ALL,
    IN_SAMPLE,
    MEASURED,
    NOT_STORED,
    OOS_HIDDEN,
    OUT_OF_SAMPLE,
)
from algotrade.services.read.edge_evidence.slices.figures import SliceFigure, figure_of
from algotrade.services.read.evaluation import runs
from algotrade.services.read.evaluation.runs import EdgeRow

REGIME = "regime"


@dataclass(frozen=True)
class RegimeRow:
    """One ``regime`` label and its figures by period."""

    regime: str
    figures: tuple[SliceFigure, ...]


@dataclass(frozen=True)
class EdgeRegimes:
    """The regime rows of the basis (``variant`` at ``horizon`` sessions): ``state`` measured
    (rows), not_stored (a run from before them, or none) or oos_hidden."""

    state: str
    variant: str | None
    horizon: int | None
    rows: tuple[RegimeRow, ...]


def _order(label: str) -> tuple[int, str]:
    """Least to most severe, a label outside the scale after it."""
    return (LABELS.index(label) if label in LABELS else len(LABELS), label)


def _figures(found: EdgeRow, min_trades: int) -> tuple[SliceFigure, ...]:
    """The whole run's figure of a regime; the split's two sides are not stored."""
    return (
        figure_of(ALL, found, False, min_trades),
        figure_of(IN_SAMPLE, None, False, min_trades),
        figure_of(OUT_OF_SAMPLE, None, False, min_trades),
    )


def regimes_of(basis: OfficialBasis, served: tuple[EdgeRow, ...], min_trades: int) -> EdgeRegimes:
    """The regime rows among ``served`` (the official run's rows) at ``basis``."""
    if basis.key is None:
        return EdgeRegimes(NOT_STORED, None, None, ())
    variant, horizon = basis.key
    if basis.hidden:
        return EdgeRegimes(OOS_HIDDEN, variant, horizon, ())
    found = [
        r
        for r in served
        if r.edge_variant == runs.MAIN
        and r.role != runs.BASELINE
        and (r.variant, r.horizon_sessions, r.slice_kind) == (variant, horizon, REGIME)
    ]
    rows = tuple(
        RegimeRow(r.slice_value, _figures(r, min_trades))
        for r in sorted(found, key=lambda r: _order(r.slice_value))
    )
    return EdgeRegimes(MEASURED if rows else NOT_STORED, variant, horizon, rows)


def load_regimes(ctx: Stores, basis: OfficialBasis) -> EdgeRegimes:
    """The regime rows of ``basis``'s official run."""
    served = runs.load_run_rows(ctx, basis.run) if basis.run is not None else ()
    return regimes_of(basis, served, load_verdict(ctx.configs).min_oos_trades)
