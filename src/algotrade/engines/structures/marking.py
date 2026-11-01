"""Marking a position of option legs through its window (ADR 0088, design 2.4; moved from the
option-outcomes task's ``option_paths``): per name, from the entry session S to the exit session T,
the underlying's close at each session, the position's value at S (mid, and executable: a long leg
bought at the ask, a short one sold at the bid), at T (the quoted mid and executable value, or the
intrinsic value of a leg that expires on T), and its net delta at each close but the last for the
daily hedge, each leg valued by our own Black-Scholes at the vol its mid implies.

A name is UNMEASURED, with a reason and no value, when a session from S to T lacks what the row
needs: a missing chain (``NO_CHAIN:<day>``) or a stale one (``STALE_CHAIN:<day>``), never filled
from an earlier session; a leg not quoted two-sided at T (``NO_EXIT_QUOTE``). A hedge session that
lacks a chain, or a leg whose delta cannot be computed (``NO_DELTA:<day>``), costs only the hedge
(``hedge_reason``). A quote with a zero bid and an ask is read, at T and on hedge sessions, as bid 0
and mid ask / 2 (a far out-of-the-money leg after a large move: the exit fallback), but never at
the entry."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from algotrade.engines.structures.chain import DayChain, Labels, usable, why_not
from algotrade.features.rollups.positioning.chain_inputs import two_sided_mid
from algotrade.quant.edges.chain_pnl import intrinsic, leg_delta, position_sum

DAYS_PER_YEAR = 365  # ADR 0021: time to expiry in calendar days


@dataclass(frozen=True)
class LegColumn:
    """One leg of the position for every name of the window: its contract per name (``""``: none),
    right (C / P), signed quantity (long +, short -), strike per name and expiry per name."""

    right: str
    qty: float
    ids: pd.Series
    strike: np.ndarray
    expiry: pd.Series


@dataclass
class Window:
    """The position of a window, vectorised over its names. ``ok`` marks the names whose legs
    were chosen at the entry; ``reason`` (per name) and ``hedge`` hold why a name is UNMEASURED
    or only its hedge is missing; both are filled in by ``mark_window``."""

    names: pd.Series
    legs: list[LegColumn]
    ok: np.ndarray
    reason: np.ndarray
    hedge: np.ndarray

    def __post_init__(self) -> None:
        if not self.legs or any(leg.right not in ("C", "P") for leg in self.legs):
            raise ValueError("a window holds at least one option leg, each a call or a put")

    def fail(self, who: np.ndarray, why: str) -> None:
        """Record ``why`` for the names in ``who`` that have no reason yet."""
        for i in np.flatnonzero(self.ok & who & pd.isna(self.reason)):
            self.reason[i] = why

    def fail_hedge(self, who: np.ndarray, why: str) -> None:
        """Record ``why`` for the names in ``who`` whose hedge has no reason yet."""
        for i in np.flatnonzero(self.ok & who & pd.isna(self.hedge)):
            self.hedge[i] = why


@dataclass(frozen=True)
class Marks:
    """The marks of a window, per name: ``spots`` the underlying's close at each session,
    ``entry_mid`` / ``entry_exec`` the position at S, ``exit_mid`` / ``exit_exec`` at T,
    ``at_expiry`` whether every held leg expired on T (valued at intrinsic), ``deltas`` the net
    delta at each close but the last (NaN where a leg's delta cannot be computed), ``mids`` the net
    quoted mid at every close from S (index 0) to T, NaN where a leg is unquoted or the chain is
    stale: the exit rules' ``position`` marks (a caller feeding them drops ``mids[0]``)."""

    spots: list[np.ndarray]
    entry_mid: np.ndarray
    entry_exec: np.ndarray
    exit_mid: np.ndarray
    exit_exec: np.ndarray
    at_expiry: np.ndarray
    deltas: list[np.ndarray]
    mids: list[np.ndarray] = field(default_factory=list)  # the position's mid at each close


def years(expiry: pd.Series, day: date) -> np.ndarray:
    return np.asarray((pd.to_datetime(expiry).dt.date.map(lambda e: (e - day).days)), float) / (
        DAYS_PER_YEAR
    )


def leg_quotes(chain: DayChain, ids: pd.Series, lenient: bool = False) -> pd.DataFrame:
    """The bid, ask and two-sided mid of contracts ``ids`` on one session (NaN where not quoted).
    ``lenient`` (the exit and the hedge sessions): a quote with a zero bid and an ask is read as
    bid 0 and mid ask / 2; the entry needs a bid above zero."""
    blank = pd.DataFrame(np.nan, index=range(len(ids)), columns=["bid", "ask", "mid"])
    if chain.options is None or chain.options.empty:
        return blank
    indexed = chain.options.drop_duplicates("instrument_id").set_index("instrument_id")
    found = indexed.reindex(ids.to_numpy())[["bid", "ask"]].astype(float)
    found.index = blank.index
    found["mid"] = two_sided_mid(found["bid"], found["ask"])
    if lenient:
        bid, ask = found["bid"].to_numpy(), found["ask"].to_numpy()
        with np.errstate(invalid="ignore"):
            zero_bid = (bid == 0) & (ask > 0)
        found["mid"] = np.where(zero_bid, ask / 2, found["mid"])
    return found


def _executable(qty: float, bid: np.ndarray, ask: np.ndarray, opening: bool) -> np.ndarray:
    """A leg's executable price on the way in (``opening``) or out: a long leg is bought at the
    ask and sold at the bid, a short one sold at the bid and bought back at the ask."""
    buy = (qty > 0) == opening
    return ask if buy else bid


def _hedge_path(
    days: Sequence[DayChain], w: Window, labels: Labels
) -> tuple[list[np.ndarray], list[np.ndarray], list[np.ndarray]]:
    """The underlying's close on each session and, on each but the last, the position's net
    delta. The exit session's missing or stale chain is a reason of the name; one between the entry
    and the exit, or a delta that cannot be computed, is only a reason its hedge is missing."""
    spots = [np.array([days[0].spots.get(i, np.nan) for i in w.names], float)]
    deltas: list[np.ndarray] = []
    mids: list[np.ndarray] = []
    every = np.arange(len(w.ok))
    for k, day in enumerate(days):
        ok_today = usable(day, w.names, labels)
        last = k == len(days) - 1
        for i in map(int, np.flatnonzero(w.ok & ~ok_today)):
            why = why_not(day, w.names.iloc[i : i + 1], labels)[0]
            (w.fail if last else w.fail_hedge)(every == i, why)
        if k:
            spots.append(np.array([day.spots.get(i, np.nan) for i in w.names], float))
        net_mid = position_sum(
            [leg.qty for leg in w.legs],
            np.vstack([leg_quotes(day, leg.ids, lenient=True)["mid"].to_numpy() for leg in w.legs]),
        )
        mids.append(np.where(ok_today, net_mid, np.nan))  # a stale or missing chain is no mark
        if last:
            break
        per_leg = []
        for leg in w.legs:
            quotes = leg_quotes(day, leg.ids, lenient=True)
            t = years(leg.expiry.where(leg.expiry.notna(), day.day), day.day)
            call = leg.right == "C"
            per_leg.append(np.asarray(leg_delta(quotes["mid"], spots[-1], leg.strike, t, call)))
        priced = np.isfinite(np.vstack(per_leg)).all(axis=0)
        net = position_sum([leg.qty for leg in w.legs], np.nan_to_num(np.vstack(per_leg)))
        w.fail_hedge(ok_today & ~priced, f"NO_DELTA:{day.day}")
        deltas.append(np.where(priced & ok_today, net, np.nan))
    return spots, deltas, mids


def _exit_values(
    exit_: DayChain, w: Window, exit_spot: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``(exit_mid, exit_exec, at_expiry)``: the position at the exit session from the quotes, a
    leg that expires on it at its intrinsic value (mid and executable alike)."""
    mids, execs, expired = [], [], []
    for leg in w.legs:
        quotes = leg_quotes(exit_, leg.ids, lenient=True)
        gone = np.array([isinstance(e, date) and e == exit_.day for e in leg.expiry])
        value = intrinsic(exit_spot, leg.strike, leg.right == "C")
        bid, ask = quotes["bid"].to_numpy(), quotes["ask"].to_numpy()
        mids.append(np.where(gone, value, quotes["mid"].to_numpy()))
        execs.append(np.where(gone, value, _executable(leg.qty, bid, ask, opening=False)))
        expired.append(gone)
    qty = [leg.qty for leg in w.legs]
    return (
        position_sum(qty, np.vstack(mids)),
        position_sum(qty, np.vstack(execs)),
        np.vstack(expired).all(axis=0),
    )


def mark_window(days: Sequence[DayChain], w: Window, labels: Labels | None = None) -> Marks:
    """The ``Marks`` of ``w`` over ``days`` (S..T in order); sets ``w.reason`` / ``w.hedge`` for
    the names that could not be marked (``NO_EXIT_QUOTE`` when T's position cannot be valued)."""
    labels = labels or Labels()
    qty = [leg.qty for leg in w.legs]
    entry = [leg_quotes(days[0], leg.ids) for leg in w.legs]
    entry_mid = position_sum(qty, np.vstack([e["mid"].to_numpy() for e in entry]))
    entry_exec = position_sum(
        qty,
        np.vstack(
            [
                _executable(leg.qty, e["bid"].to_numpy(), e["ask"].to_numpy(), opening=True)
                for leg, e in zip(w.legs, entry, strict=True)
            ]
        ),
    )
    spots, deltas, mids = _hedge_path(days, w, labels)
    exit_mid, exit_exec, at_expiry = _exit_values(days[-1], w, spots[-1])
    w.fail(~np.isfinite(entry_mid), "NO_ENTRY_QUOTE")
    w.fail(~np.isfinite(exit_mid), "NO_EXIT_QUOTE")
    return Marks(spots, entry_mid, entry_exec, exit_mid, exit_exec, at_expiry, deltas, mids)
