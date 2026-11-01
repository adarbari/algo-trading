"""The shapes of an edge's verdict and its candidates: the status words, the criterion, column,
year and verdict records, the formatting helpers and the candidate rows (ED8)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Final

from algotrade.services.read.evaluation import runs
from algotrade.services.read.evaluation.decay import EdgeDecay
from algotrade.services.read.evaluation.evidence import (
    EvidenceProgress,
)
from algotrade.services.read.evaluation.robustness import (
    EdgeHaircut,
    Robustness,
)
from algotrade.services.read.evaluation.runs import EdgeRow

WORKS: Final = "works"
PROMISING: Final = "promising"
NOT_WORKING: Final = "not_working"
NOT_ENOUGH: Final = "not_enough_data"
WAITING: Final = "waiting_on_data"
DIAGNOSTIC: Final = "diagnostic_only"  # a long-short result: a spread is never a verdict basis
ORDER: Final = (DIAGNOSTIC, WAITING, NOT_ENOUGH, NOT_WORKING, PROMISING, WORKS)  # worst to best
PASS, FAIL, NOT_MEASURED, NOT_APPLICABLE = "pass", "fail", "not_measured", "not_applicable"
CRITERION_STATUSES: Final = (
    PASS,
    FAIL,
    NOT_MEASURED,
    NOT_APPLICABLE,
)  # a criterion's status, each explained in the Guide
NOT_CANDIDATES: Final = ("baseline", runs.MEMBER)  # roles that are never a verdict's basis
IN_SAMPLE, OUT_OF_SAMPLE, BOTH, ALL = "in_sample", "out_of_sample", "both", "all"
NO_DECOYS = "no decoys declared"  # the value of a decoy criterion that does not apply
DIAGNOSTIC_SIDE = (
    "A long-short spread is a diagnostic: no verdict rests on it (a short leg alone can)"
)
EN_DASH = "\u2013"  # between the months of a partial year's label


@dataclass(frozen=True)
class VerdictCriterion:
    """One test of the verdict: what was measured, what it must reach and whether it did
    (``status``: ``pass``, ``fail``, ``not_measured`` or ``not_applicable``: the test has nothing to
    test, as a decoy comparison with no decoys declared; it counts neither for nor against the
    level); ``level``: the verdict it gates."""

    id: str
    label: str
    value: str
    threshold: str
    status: str
    level: str


@dataclass(frozen=True)
class VerdictColumn:
    """The basis's figures over one ``period`` (``in_sample``, ``out_of_sample`` or ``all``);
    ``thin``: the out-of-sample column has fewer trades than the verdict needs. A figure not
    stored (older runs) is None."""

    period: str
    win_rate: float | None
    base_rate: float | None
    lift_pts: float | None
    trades: int | None
    decile_spread: float | None
    decile_t: float | None
    sharpe: float | None
    deflated_sharpe: float | None
    pbo: float | None
    thin: bool
    picks_t: float | None = None  # the t-ratio of ``sharpe`` over the picks series
    reference_rate: float | None = None  # expires_otm only: the risk-neutral rate of the win
    touch_rate: float | None = None  # expires_otm only: picks whose strike was touched


@dataclass(frozen=True)
class YearRow:
    """One calendar year of the basis (screen, holding period), or the part of it on one side
    of the split (``partial``: a year the split falls in is two rows, in-sample then
    out-of-sample); ``period``: ``in_sample``, ``out_of_sample`` or ``both`` (a run from before
    the parts); ``label``: the row's name ("2026 Jan-Mar", en dash), from ``from_date``
    to ``to_date``."""

    year: str
    period: str
    label: str
    from_date: date
    to_date: date
    partial: bool
    win_rate: float | None
    base_rate: float | None
    lift_pts: float | None
    decile_spread: float | None
    trades: int | None


@dataclass(frozen=True)
class EdgeVerdict:
    """The verdict of one edge. ``basis``: the screen and holding period it rests on (None:
    none); the figures are the basis's out-of-sample ones (``trades``: the whole run's);
    ``result``: the one-line out-of-sample result for the list; ``headline``: the sentence for
    the page; ``rationale``: the first failing criterion in words."""

    edge_id: str
    verdict: str
    rationale: str
    headline: str
    result: str
    criteria: tuple[VerdictCriterion, ...] = ()
    basis: str | None = None
    trades: int | None = None
    oos_trades: int | None = None
    win_rate: float | None = None
    base_rate: float | None = None
    lift_pts: float | None = None
    lift: float | None = None
    decile_spread: float | None = None
    decile_t: float | None = None
    sharpe: float | None = None
    deflated_sharpe: float | None = None
    pbo: float | None = None
    years: tuple[YearRow, ...] = ()
    trials: int | None = None  # the variants tried on the edge (the whole result's count)
    deciles: tuple[float | None, ...] = ()  # in-sample mean outcome per tenth, best-ranked first
    robustness: Robustness | None = None  # the lift among the random-pick backtests
    columns: tuple[VerdictColumn, ...] = ()  # in-sample, out-of-sample, all (empty: waiting)
    evidence: EvidenceProgress | None = None  # the trades against what the verdict needs
    haircut: EdgeHaircut | None = None  # the basis's Sharpe ratio after the variants tried
    decay: EdgeDecay | None = None  # the paper's figure against the in- and out-of-sample ones
    basis_why: str = ""  # a basis chosen among several: the in-sample lifts it was chosen on
    side: str = "long"  # the basis's outcome side: long | short | long_short (ADR 0053 amendment)
    basis_screener: str | None = None  # the basis's screener (``basis`` in words), None: no basis
    basis_horizon: int | None = None  # the basis's holding period in trading days


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.0f}%"


def _ret(x: float | None) -> str:
    """A mean return as a percentage with two decimals (a whole percent hides a book's edge)."""
    return "not stored" if x is None else f"{x * 100:.2f}%"


def _num(x: float | None, digits: int = 2) -> str:
    return "not stored" if x is None else f"{x:.{digits}f}"


def _crit(
    id: str, label: str, value: str, threshold: str, ok: bool | None, level: str
) -> VerdictCriterion:
    status = NOT_MEASURED if ok is None else PASS if ok else FAIL
    return VerdictCriterion(id, label, value, threshold, status, level)


def _not_applicable(
    id: str, label: str, value: str, threshold: str, level: str
) -> VerdictCriterion:
    return VerdictCriterion(id, label, value, threshold, NOT_APPLICABLE, level)


def _at_least(x: float | None, bound: float) -> bool | None:
    return None if x is None else x >= bound


def _at_most(x: float | None, bound: float) -> bool | None:
    return None if x is None else x <= bound


@dataclass(frozen=True)
class _Candidate:
    variant: str
    horizon: int
    oos: EdgeRow
    whole: EdgeRow
    insample: EdgeRow | None
    baselines: tuple[EdgeRow, ...]
    years: tuple[EdgeRow, ...]
    year_parts: tuple[EdgeRow, ...] = ()  # a year cut by the split, as ``<year>:<side>`` rows
    lone: bool = False  # the only screener of the run at its holding period: no PBO peers
    chain: bool = False  # a chain P&L edge: no in-sample history exists (ADR 0065 amendment)
    timed: bool = False  # a time-series edge (ADR 0073): its t is the Welch t, in against out


def _by_year(row: EdgeRow) -> str:
    return row.slice_value


def _candidates(rows: Sequence[EdgeRow]) -> list[_Candidate]:
    main = [r for r in rows if r.edge_variant == runs.MAIN and not r.exploratory]
    found = []
    for variant, horizon in sorted(
        {(r.variant, r.horizon_sessions) for r in main if r.role not in NOT_CANDIDATES}
    ):
        mine = [r for r in main if r.variant == variant and r.horizon_sessions == horizon]
        oos = [r for r in mine if r.slice_kind == "frozen"]
        whole = [r for r in mine if r.slice_kind == "all"]
        before = [r for r in mine if r.slice_kind == "in_sample"]  # absent in older runs
        if len(oos) != 1 or len(whole) != 1:
            continue
        base = tuple(
            r
            for r in main
            if r.role == "baseline" and r.horizon_sessions == horizon and r.slice_kind == "frozen"
        )
        years = tuple(sorted((r for r in mine if r.slice_kind == "year"), key=_by_year))
        parts = tuple(sorted((r for r in mine if r.slice_kind == "year_part"), key=_by_year))
        trials = {
            (r.edge_variant, r.variant)
            for r in rows
            if r.role not in (runs.BASELINE, runs.RANDOM, runs.MEMBER)
            and r.slice_kind == "all"
            and r.horizon_sessions == horizon
            and not r.exploratory
        }
        found.append(
            _Candidate(
                variant,
                horizon,
                oos[0],
                whole[0],
                before[0] if len(before) == 1 else None,
                base,
                years,
                parts,
                len(trials) == 1,
            )
        )
    return found


@dataclass(frozen=True)
class EdgeSummary:
    """The headline of an edge's verdict, what the edges list renders: the label, the one-line
    ``result``, the screen and holding period it rests on, the trades and the lift. Always a
    projection of the full verdict's own fields (``summary_of``), never a second rule."""

    edge_id: str
    verdict: str
    result: str
    basis: str | None
    trades: int | None
    oos_trades: int | None
    lift: float | None
    lift_pts: float | None
    basis_screener: str | None = None  # the screener the verdict was judged on (ADR 0083 d2)
    basis_horizon: int | None = None  # and its holding period in trading days


def summary_of(v: EdgeVerdict) -> EdgeSummary:
    """The headline fields of ``v``."""
    return EdgeSummary(
        v.edge_id, v.verdict, v.result, v.basis, v.trades, v.oos_trades, v.lift, v.lift_pts,
        v.basis_screener, v.basis_horizon,
    )  # fmt: skip
