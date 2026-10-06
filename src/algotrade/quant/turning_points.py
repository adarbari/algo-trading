"""Bull and bear market dating from a level series: turning points, phases and drawdowns.

A rule, not a judgement call, so the regime track's episodes are reproducible. Each function
takes one positive, finite level series (an index or a price, one value per observation,
oldest first; the caller drops missing sessions) and works on array indices: the caller maps
indices back to sessions. A ``Phase`` runs from one confirmed turning point to the next.

    pagan_sossounov   Pagan and Sossounov (2003), "A Simple Framework for Analysing Bull and
                      Bear Markets", J. Applied Econometrics 18(1), after Bry and Boschan
                      (1971): local extrema over +/- ``window`` observations, alternation,
                      minimum cycle and phase lengths, a large move may break the phase rule
    lunde_timmermann  Lunde and Timmermann (2004), "Duration Dependence in Stock Prices",
                      JBES 22(3): a threshold filter, a bull ends after a fall of ``down``
                      from its peak, a bear after a rise of ``up`` from its trough
    drawdowns         the running drawdown from the running peak (``level / peak - 1``)

Both dating rules are EX POST: Pagan-Sossounov confirms a turn only with ``window``
observations after it (and its cycle and censoring rules can remove a turn later still);
Lunde-Timmermann confirms one when the threshold is crossed. They date history (the episode
scorecard's ground truth), they are not point-in-time signals. ``drawdowns`` is point in
time. Ties are broken towards the earlier observation, so the same input gives the same
phases; scaling the levels leaves the phases unchanged.
"""

from dataclasses import dataclass
from itertools import pairwise
from typing import Literal, NamedTuple

import numpy as np
import numpy.typing as npt

type Array = npt.NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class Phase:
    """One bull or bear phase between two turning points (array indices, inclusive at both
    ends: adjacent phases share the turn index, ``phases[i].end == phases[i + 1].start``)."""

    start: int
    end: int
    kind: Literal["bull", "bear"]
    change: float  # levels[end] / levels[start] - 1


class _Turn(NamedTuple):
    at: int
    peak: bool


def _levels(levels: npt.ArrayLike) -> Array:
    series = np.asarray(levels, dtype=np.float64)
    if series.ndim != 1:
        raise ValueError("levels must be a 1-d array")
    if not np.all(np.isfinite(series) & (series > 0)):
        raise ValueError("levels must be finite and positive (drop missing sessions first)")
    return series


def _phases(lv: Array, turns: list[_Turn]) -> list[Phase]:
    return [
        Phase(a.at, b.at, "bear" if a.peak else "bull", float(lv[b.at] / lv[a.at] - 1))
        for a, b in pairwise(turns)
    ]


def drawdowns(levels: npt.ArrayLike) -> Array:
    """Running drawdown ``level / running peak - 1`` (0 at a new high, -0.25 25% below it)."""
    lv = _levels(levels)
    return lv / np.maximum.accumulate(lv) - 1.0


# ----------------------------------------------------------------------------- Pagan-Sossounov


def _beats(lv: Array, a: _Turn, b: _Turn) -> bool:
    """Whether ``a`` is strictly more extreme than ``b`` (same kind): higher peak, lower trough."""
    return bool(lv[a.at] > lv[b.at] if a.peak else lv[a.at] < lv[b.at])


def _alternate(lv: Array, turns: list[_Turn]) -> list[_Turn]:
    """Of two adjacent turns of one kind keep the more extreme (the earlier on a tie)."""
    out: list[_Turn] = []
    for turn in turns:
        if out and out[-1].peak == turn.peak:
            if _beats(lv, turn, out[-1]):
                out[-1] = turn
        else:
            out.append(turn)
    return out


def _censor_ends(lv: Array, turns: list[_Turn]) -> list[_Turn]:
    """Drop a first (last) peak lower than a level before (after) it; troughs likewise."""

    def beaten(turn: _Turn, rest: Array) -> bool:  # ``rest`` holds >= ``window`` levels
        return bool(rest.max() > lv[turn.at] if turn.peak else rest.min() < lv[turn.at])

    while turns and beaten(turns[0], lv[: turns[0].at]):
        turns = turns[1:]
    while turns and beaten(turns[-1], lv[turns[-1].at + 1 :]):
        turns = turns[:-1]
    return turns


def _fix_short_cycle(lv: Array, turns: list[_Turn], min_cycle: int) -> list[_Turn] | None:
    """Remove the first cycle (peak to peak or trough to trough) shorter than ``min_cycle``.

    The less extreme end goes, with the less extreme of the two opposite turns beside it
    (the turn between and the end's outer neighbour; the turn between on a tie or when there
    is no neighbour), so the most extreme turns survive. None when every cycle is long enough.
    """
    for k in range(len(turns) - 2):
        first, middle, last = turns[k], turns[k + 1], turns[k + 2]
        if last.at - first.at < min_cycle:
            if _beats(lv, last, first):
                loser, outer = first, turns[k - 1] if k > 0 else None
            else:
                loser, outer = last, turns[k + 3] if k + 3 < len(turns) else None
            partner = outer if outer is not None and _beats(lv, middle, outer) else middle
            return [t for t in turns if t not in (loser, partner)]
    return None


def _fix_short_phase(
    lv: Array, turns: list[_Turn], min_phase: int, min_move: float
) -> list[_Turn] | None:
    """Remove the first phase shorter than ``min_phase`` whose move is not above ``min_move``.

    Of each kind, the less extreme of the phase's turn and its outer neighbour goes (the
    earlier wins a tie); at an end, where one kind has no neighbour, only the other kind is
    compared and the turns left merge by alternation. A lone phase goes entirely. None when
    every phase is long enough or moved enough.
    """
    for k in range(len(turns) - 1):
        a, b = turns[k], turns[k + 1]
        move = abs(lv[b.at] / lv[a.at] - 1)
        if b.at - a.at >= min_phase or move > min_move:
            continue
        if len(turns) == 2:
            return []
        if k == 0:
            drop = {a} if _beats(lv, turns[2], a) else {b}
        elif k + 2 == len(turns):
            drop = {a} if _beats(lv, b, turns[k - 1]) else {b}
        else:
            x, y = turns[k - 1], turns[k + 2]
            drop = {x if _beats(lv, b, x) else b, a if _beats(lv, y, a) else y}
        return _alternate(lv, [t for t in turns if t not in drop])
    return None


def pagan_sossounov(
    levels: npt.ArrayLike,
    *,
    window: int = 8,
    min_phase: int = 4,
    min_cycle: int = 16,
    min_move: float = 0.20,
) -> list[Phase]:
    """Date bull and bear phases with the Pagan-Sossounov rules (arguments in observations).

    The defaults are the paper's, for monthly levels (8, 4 and 16 months). For daily
    sessions (about 21 a month) the equivalents are ``window=168, min_phase=84,
    min_cycle=336``; ``min_move`` is a fraction either way.

    1. A peak (trough) is the highest (lowest) level of the ``2 * window + 1`` observations
       centred on it; a turn needs ``window`` observations on both sides, which also
       censors the ends of the series (the paper censors 6 of its 8 months).
    2. Alternation: of adjacent peaks keep the higher, of adjacent troughs the lower.
    3. End censoring: a first (last) peak below a level before (after) it is dropped, a
       first (last) trough above one likewise.
    4. Cycles (peak to peak, trough to trough) shorter than ``min_cycle`` are removed.
    5. Phases shorter than ``min_phase`` are removed unless the move exceeds ``min_move``.

    Steps 2-5 repeat, fixing the first violation from the start each time, until none is
    left. The first and last phases end at confirmed turns: the run-up to the first turn and
    the move after the last one are not phases.
    """
    lv = _levels(levels)
    if window < 1 or min_phase < 1 or min_cycle < 1 or min_move < 0:
        raise ValueError("window, min_phase and min_cycle must be >= 1 and min_move >= 0")
    turns: list[_Turn] = []
    for t in range(window, lv.shape[0] - window):
        around = lv[t - window : t + window + 1]
        high, low = around.max(), around.min()
        if high > low and lv[t] in (high, low):
            turns.append(_Turn(t, bool(lv[t] == high)))
    while True:
        turns = _censor_ends(lv, _alternate(lv, turns))
        fixed = _fix_short_cycle(lv, turns, min_cycle)
        if fixed is None:
            fixed = _fix_short_phase(lv, turns, min_phase, min_move)
        if fixed is None:
            return _phases(lv, turns)
        turns = fixed


# ----------------------------------------------------------------------------- Lunde-Timmermann


def lunde_timmermann(levels: npt.ArrayLike, *, up: float = 0.20, down: float = 0.20) -> list[Phase]:
    """Date bull and bear phases with the Lunde-Timmermann threshold filter.

    Until the first threshold is crossed both the running high and low are tracked. A bear
    phase starts at the running high once a level is at least ``down`` below it, and ends at
    the lowest level since then once a level is at least ``up`` above that low; a bull phase
    the other way round. Only phases between two confirmed turns are returned (the last,
    still open phase is not). A first turn at the first observation is dropped: the series
    may start mid-phase, so it is not a turn (the counterpart of Pagan-Sossounov's end
    censoring; ties go to the earlier observation, so a running extreme that never moved off
    the start sits at index 0).
    """
    lv = _levels(levels)
    if up <= 0 or not 0 < down < 1:
        raise ValueError(f"need up > 0 and 0 < down < 1, got {up}, {down}")
    turns: list[_Turn] = []
    high = low = 0  # indices of the running high and low since the last turn
    for t in range(1, lv.shape[0]):
        level = lv[t]
        looking_for_peak = not turns or not turns[-1].peak
        looking_for_trough = not turns or turns[-1].peak
        if looking_for_peak and level > lv[high]:
            high = t
        if looking_for_trough and level < lv[low]:
            low = t
        if looking_for_peak and level <= lv[high] * (1 - down):
            turns.append(_Turn(high, True))
            low = t
        elif looking_for_trough and level >= lv[low] * (1 + up):
            turns.append(_Turn(low, False))
            high = t
    if turns and turns[0].at == 0:
        turns = turns[1:]
    return _phases(lv, turns)
