"""Random-pick backtests (ADR 0053 amendment, ED8 step 2): what a draw of names chosen with no
information would have scored, the yardstick an edge's out-of-sample result is placed against.

At each decision session of the out-of-sample slice ``draws`` times ``top_k`` names are taken
uniformly from the pickable names that have a counted outcome, from the outcomes the harness
already holds (no new read). The generator of a session is seeded by (leg key, edge variant,
holding period, session), the names sorted by id first: the leg key (``legs/key.py``) names what
the leg is a function of and not the range or the ``as_of``, so a run draws the same names for a
session whatever the order the sessions or the names arrive in, and a session's draws do not
change when another session is added or the run's start, end or ``as_of`` move (ADR 0063).
A second set of draws is **sector-stratified** (ADR 0053 amendment 2026-10-18): the screener's
counted picks at the session are counted per sector (``instrument.sector`` at D, "UNKNOWN" for
a name with none) and each sector's count is drawn uniformly from that sector's pickable
counted names (every name when the sector has fewer), so the draws hold the picks' sector mix
and an edge that is only a sector tilt does not beat them. It has its own generator (the
session's, labelled ``sector``) and the same ``draws``; ``RandomStat.sector``. A draw's row is the
pooled picks of its sessions: ``hit_rate`` against
the session's own ``base_rate`` (every counted name), ``lift`` and ``mean_excess_picks``, the same
measures as a screener's, so the read model can place the screener's lift among them
(``quant.edges.statistics.percentile_of``). A draw does not read a screen, so a session a screener
could not be run on still has draws; the figures are over the sessions whose window closed.
"""

import hashlib
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np
import numpy.typing as npt
import pandas as pd

from algotrade.quant.edges.statistics import lift, random_pick_sums
from algotrade.services.evaluation.cross_section.measures import SliceMeasure

RANDOM = "random"  # the role and the variant of a random-pick row
SECTOR_RANDOM = "random_sector"  # the variant prefix of the sector-stratified draws (role RANDOM)
UNKNOWN_SECTOR = "UNKNOWN"  # the stratum of a name with no sector at D
DRAW = "draw"  # its slice kind; the slice value is the draw's number
DEFAULT_DRAWS = 1000
SEED_VERSION = 3  # the seed scheme: in the run hash and the leg key, so a change is a new run


@dataclass(frozen=True)
class SectorDraws:
    """The sector-stratified draws of one session: the names per draw (below the screener's own
    count when a sector has fewer names than it had picks) and the sums, as ``RandomStat``."""

    picks: int
    value_sums: npt.NDArray[np.float64]  # (draws,)
    hit_sums: npt.NDArray[np.float64]  # (draws,)


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
    sector: SectorDraws | None = None  # the sector-stratified draws (None: not drawn)

    def stratified(self) -> "RandomStat | None":
        """The sector-stratified draws as a ``RandomStat`` of their own (same base)."""
        if self.sector is None:
            return None
        return RandomStat(
            self.session, self.sector.picks, self.sector.value_sums, self.sector.hit_sums,
            self.eligible, self.base_hits,
        )  # fmt: skip


def generator(leg_key: str, edge_variant: str, horizon: int, session: date) -> np.random.Generator:
    """The session's generator, a function of its four arguments only."""
    digest = hashlib.sha256(f"{leg_key}|{edge_variant}".encode()).digest()
    entropy = [int.from_bytes(digest[:8], "big"), int.from_bytes(digest[8:16], "big")]
    return np.random.default_rng(np.random.SeedSequence([*entropy, horizon, session.toordinal()]))


def sector_mix(pick_ids: Sequence[str], sectors: Mapping[str, str | None]) -> dict[str, int]:
    """The picks per sector (``UNKNOWN_SECTOR`` for a name with none), by sector name."""
    mix: dict[str, int] = {}
    for i in pick_ids:
        sector = sectors.get(i) or UNKNOWN_SECTOR
        mix[sector] = mix.get(sector, 0) + 1
    return dict(sorted(mix.items()))


def sector_draws(
    names: pd.DataFrame,
    sectors: Mapping[str, str | None],
    mix: Mapping[str, int],
    draws: int,
    rng: np.random.Generator,
) -> SectorDraws | None:
    """``draws`` sector-stratified draws: for each sector of ``mix`` (in name order) its count of
    names drawn uniformly without replacement from ``names`` (indexed by instrument, with the
    oriented value and the ``hit``) of that sector, every one when it has fewer. The strata
    draw in sector order from ``rng`` and the names in id order, so the draws are a function of
    the generator and the inputs only. None when no stratum has a name."""
    ordered = names.sort_index()
    labels = np.array([sectors.get(i) or UNKNOWN_SECTOR for i in ordered.index], dtype=object)
    value_sums, hit_sums, picks = np.zeros(draws), np.zeros(draws), 0
    for sector, count in mix.items():
        stratum = ordered[labels == sector]
        found = random_pick_sums(
            stratum["oriented"].to_numpy(dtype=float),
            stratum["hit"].to_numpy(dtype=float),
            count,
            draws,
            rng,
        )
        if found is not None:
            value_sums, hit_sums = value_sums + found[0], hit_sums + found[1]
            picks += min(count, len(stratum))
    return SectorDraws(picks, value_sums, hit_sums) if picks else None


def random_stat(
    session: date,
    counted: pd.DataFrame,
    pickable: Collection[str],
    top_k: int,
    draws: int,
    rng: np.random.Generator,
    sectors: Mapping[str, str | None] | None = None,
    pick_ids: Sequence[str] = (),
    sector_rng: np.random.Generator | None = None,
) -> RandomStat | None:
    """``draws`` draws of ``top_k`` names at ``session``. ``counted``: the names with a counted
    outcome, indexed by instrument with the oriented value and the ``hit``; the names drawn from
    are those of them in ``pickable``. ``top_k`` is the screener's own count at the session; at 0
    nothing is drawn but the base (every counted name) is kept. None when nothing is counted.
    ``sectors`` (name -> sector at D, with ``pick_ids`` the screener's counted picks and
    ``sector_rng``): also the sector-stratified draws."""
    if counted.empty:
        return None
    base = {"eligible": len(counted), "base_hits": int(counted["hit"].sum())}
    if top_k < 1:
        zeros = np.zeros(draws)
        held = None if sectors is None else SectorDraws(0, zeros, zeros)
        return RandomStat(session, 0, zeros, zeros, **base, sector=held)
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
    held = None
    if sectors is not None:
        assert sector_rng is not None  # drawn with the sectors
        held = sector_draws(names, sectors, sector_mix(pick_ids, sectors), draws, sector_rng)
        held = held or SectorDraws(0, np.zeros(draws), np.zeros(draws))
    return RandomStat(
        session=session,
        picks=min(top_k, len(names)),
        value_sums=sums[0],
        hit_sums=sums[1],
        **base,
        sector=held,
    )


def pool_random(legs: Sequence[RandomStat]) -> RandomStat:
    """The block of event days as one session at its first day: the picks, sums and base added
    (the screener's own pooling, ``measures.pool_stats``)."""
    first = legs[0]
    if len(legs) == 1:
        return first
    held = [leg.sector for leg in legs]
    pooled = (
        None
        if any(h is None for h in held)
        else SectorDraws(
            sum(h.picks for h in held if h),
            np.sum([h.value_sums for h in held if h], axis=0),
            np.sum([h.hit_sums for h in held if h], axis=0),
        )
    )
    return RandomStat(
        session=first.session,
        picks=sum(leg.picks for leg in legs),
        value_sums=np.sum([leg.value_sums for leg in legs], axis=0),
        hit_sums=np.sum([leg.hit_sums for leg in legs], axis=0),
        eligible=sum(leg.eligible for leg in legs),
        base_hits=sum(leg.base_hits for leg in legs),
        sector=pooled,
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
