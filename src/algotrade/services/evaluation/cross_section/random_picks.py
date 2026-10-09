"""Random-pick backtests (ADR 0053 amendment, ED8 step 2): what a draw of names chosen with no
information would have scored, the yardstick an edge's out-of-sample result is placed against.

At each decision session of the out-of-sample slice ``draws`` times ``top_k`` names are taken
uniformly from the pickable names that have a counted outcome, from the outcomes the harness
already holds (no new read). The generator of a session is seeded by (run hash, edge variant,
holding period, session), the names sorted by id first: the same run draws the same names
whatever the order the sessions or the names arrive in, and a session's draws do not change when
another session is added. A draw's row is the pooled picks of its sessions: ``hit_rate`` against
the session's own ``base_rate`` (every counted name), ``lift`` and ``mean_excess_picks``, the same
measures as a screener's, so the read model can place the screener's lift among them
(``quant.edge_statistics.percentile_of``). A draw does not read a screen, so a session a screener
could not be run on still has draws; the figures are over the sessions whose window closed.
"""

import hashlib
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np
import numpy.typing as npt
import pandas as pd

from algotrade.quant.edge_statistics import lift, random_pick_sums
from algotrade.services.evaluation.cross_section.measures import SliceMeasure

RANDOM = "random"  # the role and the variant of a random-pick row
DRAW = "draw"  # its slice kind; the slice value is the draw's number
DEFAULT_DRAWS = 1000
SEED_VERSION = 2  # the seed scheme: in the run hash, so a change of scheme is a new run


@dataclass(frozen=True)
class RandomStat:
    """The draws of one decision session (or of an event block, summed): per draw the sum of
    the oriented values and the hits of its ``picks`` names, and the base the rates are over."""

    session: date
    picks: int  # names per draw, the same for every draw
    value_sums: npt.NDArray[np.float64]  # (draws,)
    hit_sums: npt.NDArray[np.float64]  # (draws,)
    eligible: int  # names with a counted outcome
    base_hits: int  # of those, the hits


def generator(run_hash: str, edge_variant: str, horizon: int, session: date) -> np.random.Generator:
    """The session's generator, a function of its four arguments only."""
    digest = hashlib.sha256(f"{run_hash}|{edge_variant}".encode()).digest()
    entropy = [int.from_bytes(digest[:8], "big"), int.from_bytes(digest[8:16], "big")]
    return np.random.default_rng(np.random.SeedSequence([*entropy, horizon, session.toordinal()]))


def random_stat(
    session: date,
    counted: pd.DataFrame,
    pickable: Collection[str],
    top_k: int,
    draws: int,
    rng: np.random.Generator,
) -> RandomStat | None:
    """``draws`` draws of ``top_k`` names at ``session``. ``counted``: the names with a counted
    outcome, indexed by instrument with the oriented value and the ``hit``; the names drawn from
    are those of them in ``pickable``. ``top_k`` is the screener's own count at the session; at 0
    nothing is drawn but the base (every counted name) is kept. None when nothing is counted."""
    if counted.empty:
        return None
    base = {"eligible": len(counted), "base_hits": int(counted["hit"].sum())}
    if top_k < 1:
        zeros = np.zeros(draws)
        return RandomStat(session, 0, zeros, zeros, **base)
    names = counted.loc[sorted(counted.index.intersection(list(pickable)))]
    sums = random_pick_sums(
        names["oriented"].to_numpy(dtype=float),
        names["hit"].to_numpy(dtype=float),
        top_k,
        draws,
        rng,
    )
    if sums is None:
        return None
    return RandomStat(
        session=session,
        picks=min(top_k, len(names)),
        value_sums=sums[0],
        hit_sums=sums[1],
        **base,
    )


def pool_random(legs: Sequence[RandomStat]) -> RandomStat:
    """The block of event days as one session at its first day: the picks, sums and base added
    (the screener's own pooling, ``measures.pool_stats``)."""
    first = legs[0]
    if len(legs) == 1:
        return first
    return RandomStat(
        session=first.session,
        picks=sum(leg.picks for leg in legs),
        value_sums=np.sum([leg.value_sums for leg in legs], axis=0),
        hit_sums=np.sum([leg.hit_sums for leg in legs], axis=0),
        eligible=sum(leg.eligible for leg in legs),
        base_hits=sum(leg.base_hits for leg in legs),
    )


def random_measures(stats: Sequence[RandomStat]) -> tuple[SliceMeasure, ...]:
    """One measure per draw over the sessions ``stats`` (the out-of-sample slice), slice kind
    ``draw`` and the draw's number as value; empty without sessions."""
    if not stats:
        return ()
    picks = sum(s.picks for s in stats)
    eligible = sum(s.eligible for s in stats)
    base_hits = sum(s.base_hits for s in stats)
    base_rate = base_hits / eligible if eligible else None
    hits = np.sum([s.hit_sums for s in stats], axis=0)
    values = np.sum([s.value_sums for s in stats], axis=0)
    out = []
    for draw in range(len(hits)):
        hit_rate = float(hits[draw]) / picks if picks else None
        out.append(
            SliceMeasure(
                slice_kind=DRAW,
                slice_value=str(draw),
                sessions=len(stats),
                picks=picks,
                hits=int(hits[draw]),
                hit_rate=hit_rate,
                eligible=eligible,
                base_hits=base_hits,
                base_rate=base_rate,
                lift=lift(hit_rate, base_rate),
                mean_excess_picks=float(values[draw]) / picks if picks else None,
                bh_mean=None,
                top_decile_mean=None,
                decile_spread=None,
                decile_t=None,
                decile_sessions=0,
                effect_size=None,
                sharpe=None,
                unscored=0,
                excluded_score_coverage=0,
                excluded_unclosed=0,
                excluded_missing=0,
                excluded_coverage=0,
                delisted=0,
                pre_snapshot_sessions=0,
            )
        )
    return tuple(out)
