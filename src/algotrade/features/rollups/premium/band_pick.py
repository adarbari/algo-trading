"""The one pick of a short option at a delta band and an expiry bucket, shared by the option
grid (``services/read/options/grid.py``) and ``short_premium@v1`` (ownership
``option-band-pick``): a cell of the grid and the group's summary are the same contract, the
same figures.

- **Expiry** (``pick_expiry``): the listed expiry nearest ``target`` calendar days within
  ``EXPIRY_TOLERANCE`` of it (ties: the earlier). ``bucket_expiries`` gives each of the
  ``TARGET_DAYS`` its expiry, distinct: a bucket whose expiry an earlier bucket took has none
  (``DUPLICATE_EXPIRY``), one with no listed expiry in its window none (``NO_EXPIRY``).
- **Strike** (``pick_band``): ``wing_search.select_legs`` over the one expiry and right with
  our own delta (``our_delta_fn``: ``wing_search.priced`` at the Treasury curve's rate for
  ``t = days / 365`` and the dividend yield ``q``): the two-sided contract whose |delta| is
  nearest the band, ties to the higher open interest, then the lower strike. Outside
  ``BAND_TOLERANCE`` of the band there is no cell (``NO_STRIKE``); a pool with no two-sided
  contract, or none whose vol inverts, is ``ILLIQUID``. No second picker.
- **Figures** (``BandCell``): mid from ``two_sided_mid``, the spread as a share of that mid
  (``relative_spread``) and open interest from the contract's row; return on collateral,
  yield a year, breakeven and the chance below the strike from ``quant.options.premium``.
  The vol is ours (inverted from the mid with the session's rate and ``q``); the chance
  below uses r = q = 0 (ADR 0053): the two differ by about 0.01 at 30 days.

Inputs are one underlying's quotes (``instrument_id``, ``expiry``, ``right`` C / P, ``strike``,
``bid``, ``ask``, ``open_interest``) and its positive spot; a bid, ask, last or size never
leaves this module.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.rollups.options.wing_search import priced, select_legs
from algotrade.features.rollups.positioning.chain_inputs import relative_spread, two_sided_mid
from algotrade.quant.options import premium
from algotrade.quant.rates import DAYS_PER_YEAR, YieldCurve

BANDS = (0.10, 0.15, 0.20, 0.25, 0.30)  # |delta| of a column of the grid
BAND_TOLERANCE = 0.025  # a strike counts for a band within this much |delta| of it
TARGET_DAYS = (7, 14, 30, 45, 60, 90)  # calendar days of a row of the grid
EXPIRY_TOLERANCE = 0.30  # an expiry counts for a target within 30% of its days
PUT, CALL = "put", "call"
NO_EXPIRY, DUPLICATE_EXPIRY = "NO_EXPIRY", "DUPLICATE_EXPIRY"
ILLIQUID, NO_STRIKE = "ILLIQUID", "NO_STRIKE"
_RIGHT = {PUT: "P", CALL: "C"}  # the chain's ``right`` values


@dataclass(frozen=True)
class ExpiryBucket:
    """One target of ``TARGET_DAYS``: its expiry, or ``reason`` (NO_EXPIRY, DUPLICATE_EXPIRY)."""

    target: int
    expiry: date | None
    reason: str | None = None


@dataclass(frozen=True)
class BandCell:
    """A short option picked at a band: the contract's strike and our delta (signed as its
    right), vol and mid, and the figures of a sold one. NaN where a figure is undefined."""

    strike: float
    delta: float
    iv: float
    mid: float
    roc: float
    yield_ann: float
    breakeven: float
    p_below: float
    spread_pct: float
    open_interest: int


@dataclass(frozen=True)
class BandMiss:
    """No cell: ``reason`` is ILLIQUID (no two-sided quote with a vol of ours) or NO_STRIKE
    (the nearest strike is farther than ``BAND_TOLERANCE`` from the band)."""

    reason: str


@dataclass(frozen=True)
class BandLeg:
    """The leg ``select_legs`` is asked for (satisfies its ``LegRule``): a short option of the
    chain's ``right`` at our |delta| ``delta``, the expiry fixed by the caller."""

    right: str
    delta: float
    kind: str = "option"
    qty: int = -1
    strike: str = "delta"
    otm_pct: float | None = None
    tenor_days: int | None = None


def pick_expiry(
    listed: Sequence[date], session: date, target: int, tolerance: float = EXPIRY_TOLERANCE
) -> date | None:
    """The listed expiry nearest ``target`` calendar days from ``session`` within ``tolerance``
    of it (ties: the earlier); None when none is."""
    near = [
        (abs((e - session).days - target), e)
        for e in set(listed)
        if (e - session).days >= 1 and abs((e - session).days - target) <= tolerance * target
    ]
    return min(near)[1] if near else None


def bucket_expiries(
    listed: Sequence[date], session: date, targets: Sequence[int] = TARGET_DAYS
) -> tuple[ExpiryBucket, ...]:
    """Each target's expiry in order; an expiry an earlier target took is not offered twice."""
    taken: set[date] = set()
    out = []
    for target in targets:
        found = pick_expiry(listed, session, target)
        if found is None:
            out.append(ExpiryBucket(target, None, NO_EXPIRY))
        elif found in taken:
            out.append(ExpiryBucket(target, None, DUPLICATE_EXPIRY))
        else:
            taken.add(found)
            out.append(ExpiryBucket(target, found))
    return tuple(out)


class OurDeltas:
    """The delta convention of the wings, as the ``delta_fn`` of ``select_legs``: our BSM delta
    of each mid with the curve's rate at ``t`` and the dividend yield ``q`` (NaN where no vol
    inverts), solved once per pool (the bands of one expiry and right share it) and with the
    vol of each strike solved remembered (``iv_of``). One instance serves one underlying."""

    def __init__(self, curve: YieldCurve, q: float) -> None:
        self._curve, self._q = curve, q
        self._solved: dict[tuple[bool, float, float, bytes, bytes], np.ndarray] = {}
        self._iv: dict[tuple[bool, float, float], float] = {}

    def __call__(
        self, mid: np.ndarray, spot: float, strike: np.ndarray, t: float, is_call: bool
    ) -> np.ndarray:
        key = (is_call, t, spot, mid.tobytes(), strike.tobytes())
        if key not in self._solved:
            iv, delta = priced(mid, spot, strike, t, float(self._curve.rate(t)), self._q, is_call)
            self._solved[key] = delta
            for k, v in zip(strike, iv, strict=True):
                self._iv[(is_call, t, float(k))] = float(v)
        return self._solved[key]

    def iv_of(self, is_call: bool, t: float, strike: float) -> float:
        """The vol of ours of a strike this instance solved for (NaN: it was not)."""
        return self._iv.get((is_call, t, strike), float("nan"))


def pick_band(
    chain: pd.DataFrame,
    session: date,
    expiry: date,
    spot: float,
    band: float,
    right: str,
    deltas: OurDeltas,
) -> BandCell | BandMiss:
    """The short ``right`` (PUT or CALL) at ``expiry`` nearest |delta| ``band`` from one
    underlying's ``chain`` (``spot`` > 0), with its figures; or why there is none."""
    code = _RIGHT[right]
    pool = chain[(chain["right"] == code) & (pd.to_datetime(chain["expiry"]).dt.date == expiry)]
    if not np.isfinite(two_sided_mid(pool["bid"], pool["ask"])).any():
        return BandMiss(ILLIQUID)
    days = (expiry - session).days
    found = select_legs(
        pool, [BandLeg(code, band)], spot, session, days, "any",
        not_before=None, delta_fn=deltas,
    )  # fmt: skip
    if not found.legs:
        return BandMiss(ILLIQUID)
    leg = found.legs[0]
    if abs(abs(leg.delta) - band) > BAND_TOLERANCE + 1e-9:
        return BandMiss(NO_STRIKE)
    row = pool[pool["instrument_id"].astype(str) == leg.instrument_id].iloc[0]
    t = days / DAYS_PER_YEAR
    sigma = deltas.iv_of(code == "C", t, leg.strike)
    roc = float(premium.return_on_collateral(leg.mid, leg.strike, spot, right))
    open_interest = row["open_interest"]
    return BandCell(
        strike=leg.strike,
        delta=leg.delta,
        iv=sigma,
        mid=leg.mid,
        roc=roc,
        yield_ann=float(premium.yield_annualised(roc, days)),
        breakeven=float(premium.breakeven(leg.mid, leg.strike, spot, right)),
        p_below=float(premium.p_below(spot, leg.strike, sigma, t, right)),
        spread_pct=float(
            relative_spread(pd.Series([row["bid"]]), pd.Series([row["ask"]]), np.array([leg.mid]))[
                0
            ]
        ),
        open_interest=int(open_interest) if pd.notna(open_interest) else 0,
    )
