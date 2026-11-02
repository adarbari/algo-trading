"""The basis choice (ADR 0065): which (screen, holding period) a verdict rests on, ranked on the
in-sample figures alone."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from algotrade.config.edges.verdict import VerdictSettings
from algotrade.services.read.evaluation import runs
from algotrade.services.read.evaluation.runs import EdgeRow
from algotrade.services.read.evaluation.verdict.criteria import (
    _criteria,
)
from algotrade.services.read.evaluation.verdict.level import (
    _level,
)
from algotrade.services.read.evaluation.verdict.model import (
    ALL,
    NOT_CANDIDATES,
    ORDER,
    _Candidate,
)


def _strength(row: EdgeRow) -> float | None:
    """What ranks two candidates in-sample: the lift in points; for a book (no base rate) its mean
    excess return in points."""
    pts = runs.lift_points(row.hit_rate, row.base_rate)
    if pts is None and row.base_rate is None and row.mean_excess_picks is not None:
        return row.mean_excess_picks * 100.0
    return pts


def _rank(lift_pts: float | None) -> float:
    return float("-inf") if lift_pts is None else lift_pts


@dataclass(frozen=True)
class Declared:
    """The basis an edge document fixes (ADR 0065): ``[implementation] promoted`` (the screen)
    and ``[implementation] horizon`` (the holding period); None: not declared."""

    screener: str | None = None
    horizon: int | None = None


UNDECLARED: Final = Declared()


@dataclass(frozen=True)
class BasisChoice:
    """The basis ``(screen, holding period)`` the verdict rests on, or None with the ``reason``
    no basis can be fixed (the verdict is then Waiting on data); ``why``: for a basis chosen
    among several, the in-sample lifts it was chosen on, in words (empty: it was the only
    candidate or the document declared it)."""

    key: tuple[str, int] | None
    reason: str = ""
    why: str = ""


def _why(ranked: Sequence[tuple[tuple[str, int], tuple[int, float]]]) -> str:
    """The candidates' in-sample lifts, best ranked first: "chosen on in-sample lift: 15 d +3.1
    pts, 31 d +2.7 pts" (a candidate with no lift is left out)."""
    parts = [
        f"{k[1]} d {lift:+.1f} pts"
        for k, (_, lift) in sorted(ranked, key=lambda p: p[1], reverse=True)
        if lift != float("-inf")
    ]
    return f"chosen on in-sample lift: {', '.join(parts)}" if parts else ""


def _in_sample_rank(
    key: tuple[str, int],
    ins: EdgeRow,
    main: Sequence[EdgeRow],
    t: VerdictSettings,
    decoys: bool,
    portfolio: bool = False,
    profile: str = "return",
) -> tuple[int, float]:
    """The verdict's ranking (level, then lift points) over the in-sample figures alone: the
    in-sample row stands for every period and the baselines are their in-sample rows; no
    random draws (they are out-of-sample), so the level is at most Promising for every one. The
    ``profile`` is the judge's, so a ``tails`` basis is ranked on the t it is judged on."""
    base = tuple(
        r
        for r in main
        if r.role == "baseline" and r.horizon_sessions == key[1] and r.slice_kind == runs.IN_SAMPLE
    )
    c = _Candidate(key[0], key[1], ins, ins, ins, base, ())
    level, _ = _level(c, _criteria(c, t, (), decoys, portfolio, profile), t, profile)
    return ORDER.index(level), _rank(_strength(ins))


def choose_basis(
    rows: Sequence[EdgeRow],
    t: VerdictSettings,
    declared: Declared = UNDECLARED,
    decoys: bool = True,
    portfolio: bool = False,
    profile: str = "return",
) -> BasisChoice:
    """The basis of a result's ``rows`` (ADR 0065), read from the in-sample rows only (the
    candidates are named by their ``in_sample`` and ``all`` rows, whose figures are not read):
    the declared screen and horizon narrow the candidates; one left is the basis; of several,
    the best in-sample (ties: the first by screen, then horizon). A run from before the
    in-sample slice cannot rank several: no basis, Waiting on data. A model screener's in-sample
    row is its training fit and is never ranked."""
    main = [r for r in rows if r.edge_variant == runs.MAIN and not r.exploratory]
    named = {
        (r.variant, r.horizon_sessions)
        for r in main
        if r.role not in NOT_CANDIDATES and r.slice_kind in (runs.IN_SAMPLE, ALL)
    }
    keys = sorted(
        k for k in named if declared.screener in (None, k[0]) and declared.horizon in (None, k[1])
    )
    if not keys:
        if declared.screener is None and declared.horizon is None:
            return BasisChoice(None, "The official result has no figures to rest a verdict on")
        wanted = f"{declared.screener or 'any screen'}, {declared.horizon or 'any'} trading days"
        return BasisChoice(
            None, f"The official result has no figures for the declared basis {wanted}"
        )
    if len(keys) == 1:
        return BasisChoice(keys[0])
    ins = {
        (r.variant, r.horizon_sessions): r
        for r in main
        if r.role not in NOT_CANDIDATES and r.slice_kind == runs.IN_SAMPLE
    }
    # a model screener's in-sample row is its training fit (``in_sample``): never ranked, so a
    # model is the basis only when it is the one candidate left (``promoted``)
    fair = {k: r for k, r in ins.items() if not r.in_sample}
    ranked = [
        (k, _in_sample_rank(k, fair[k], main, t, decoys, portfolio, profile))
        for k in keys
        if k in fair
    ]
    if not ranked:
        if any(k in ins for k in keys):
            return BasisChoice(
                None, "Only a model screener's training fit is in-sample; it needs promoting"
            )
        return BasisChoice(
            None,
            "The official result predates the in-sample figures its basis is chosen on; "
            "it needs a new run",
        )
    best = max(ranked, key=lambda p: p[1])  # max keeps the first of equals: keys are sorted
    return BasisChoice(best[0], why=_why(ranked))
