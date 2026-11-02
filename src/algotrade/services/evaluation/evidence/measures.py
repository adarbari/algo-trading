"""The evidence measures of a setup over its return on capital (ADR 0088, design 2.6): the mean
with a block-bootstrap interval, the paired excess against the base and its bootstrap t, CVaR 5%
and 1% with the windows in the tail, the worst window and the probabilistic Sharpe ratio. Pure over
plain arrays (one value per decision session), so ``cross_section/measures.py`` calls it without a
cycle.

A figure not measured is None, never 0: no series (a hit-rate outcome with no money, a
bought-and-held band, a session with no return on capital), fewer than two sessions, or no base
gives None.

The bootstrap is seeded by the trial's identity (config, not code version) and a frozen constant, so
a ``LEG_VERSION`` bump or a new run id never re-seeds it and flips a verdict on unchanged data."""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np
import numpy.typing as npt

from algotrade.config.edges.verdict import TailsVerdict
from algotrade.quant.edges.statistics import independent_sessions
from algotrade.quant.edges.tails import cvar, psr, stationary_bootstrap, worst

BOOTSTRAP_SEED_VERSION = 1  # FROZEN: changing it re-seeds every bootstrap (and so every interval)
ROC, EXCESS = "roc", "excess"  # the two series, the last word of a seed label


@dataclass(frozen=True)
class TailMeasures:
    """The ``edge_eval`` evidence columns of one slice; every one None when not measured.
    ``roc_sessions``: the sessions with a return on capital (the series' length)."""

    roc_sessions: int | None = None
    mean_roc: float | None = None
    mean_roc_lo: float | None = None
    mean_roc_hi: float | None = None
    excess_roc: float | None = None
    excess_roc_t: float | None = None
    cvar_5: float | None = None
    cvar_5_n: int | None = None
    cvar_1: float | None = None
    cvar_1_n: int | None = None
    base_cvar_5: float | None = None
    worst_window: float | None = None
    psr: float | None = None


def bootstrap_seed(seed_key: str, label: str) -> int:
    """The seed of one bootstrap: the trial identity, the series label and the frozen constant;
    never a run id, an as-of or a ``LEG_VERSION`` (they move without the data moving)."""
    text = f"{seed_key}|{label}|{BOOTSTRAP_SEED_VERSION}"
    return int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")


def mean_block(days: Sequence[date], horizon: int, tails: TailsVerdict) -> float:
    """The bootstrap's mean block: the settings' (3 sessions), raised to the sessions one window
    spans when windows of ``horizon`` started every session overlap (a block of 3 would understate
    the variance: the correction the t-ratios use, ``statistics.overlap_t``)."""
    independent = max(1, independent_sessions(days, horizon))
    return max(tails.bootstrap_mean_block, len(days) / independent)


def _series(days: Sequence[date], values: npt.ArrayLike) -> tuple[list[date], np.ndarray]:
    """The finite entries of ``values`` with their days, in date order."""
    arr = np.asarray(values, dtype=np.float64)
    order = sorted((d, i) for i, d in enumerate(days) if np.isfinite(arr[i]))
    return [d for d, _ in order], np.array([arr[i] for _, i in order], dtype=np.float64)


def tail_measures(
    days: Sequence[date],
    roc: npt.ArrayLike,
    base_roc: npt.ArrayLike,
    horizon: int,
    seed_key: str,
    label: str,
    tails: TailsVerdict,
    bootstrap: bool,
) -> TailMeasures:
    """The measures over one slice's sessions: ``roc[i]`` the session's mean return on capital of
    its counted picks, ``base_roc[i]`` the base's on the same session (NaN: unknown), ``days[i]``
    its decision session. ``label`` names the slice (``<kind>:<value>:<horizon>``, seeds the
    bootstrap); ``bootstrap`` False leaves the interval and t None (CVaR, worst, PSR and the means
    always run)."""
    got, r = _series(days, roc)
    if r.size == 0:
        return TailMeasures()
    n = int(r.size)
    if n < 2:
        return TailMeasures(roc_sessions=n)
    c5, n5 = cvar(r, 0.05)
    c1, n1 = cvar(r, 0.01)
    base = np.asarray(base_roc, dtype=np.float64)
    _, b = _series(days, base)
    base_c5 = cvar(b, 0.05)[0] if b.size >= 2 else None
    lo = hi = None
    if bootstrap:
        block = mean_block(got, horizon, tails)
        boot = stationary_bootstrap(
            r, block, tails.bootstrap_draws, bootstrap_seed(seed_key, f"{label}:{ROC}")
        )
        lo, hi = boot.lo, boot.hi
    excess, excess_t = _excess(days, roc, base, horizon, seed_key, label, tails, bootstrap)
    return TailMeasures(
        roc_sessions=n,
        mean_roc=float(r.mean()),
        mean_roc_lo=lo,
        mean_roc_hi=hi,
        excess_roc=excess,
        excess_roc_t=excess_t,
        cvar_5=c5,
        cvar_5_n=n5,
        cvar_1=c1,
        cvar_1_n=n1,
        base_cvar_5=base_c5,
        worst_window=worst(r),
        psr=psr(r),
    )


def _excess(
    days: Sequence[date],
    roc: npt.ArrayLike,
    base: np.ndarray,
    horizon: int,
    seed_key: str,
    label: str,
    tails: TailsVerdict,
    bootstrap: bool,
) -> tuple[float | None, float | None]:
    """The mean paired excess ``roc - base`` over the sessions where both are known, and its
    bootstrap t; None below two pairs."""
    diff = np.asarray(roc, dtype=np.float64) - base  # NaN where either is NaN
    got, d = _series(days, diff)
    if d.size < 2:
        return None, None
    if not bootstrap:
        return float(d.mean()), None
    boot = stationary_bootstrap(
        d,
        mean_block(got, horizon, tails),
        tails.bootstrap_draws,
        bootstrap_seed(seed_key, f"{label}:{EXCESS}"),
    )
    return boot.mean, boot.t
