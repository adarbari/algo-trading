"""The rows of one chain P&L window (ADR 0053 amendment, EB H13), pure over the stored chains of
its sessions: for a start session S, a structure, a tenor rule and a horizon, what each underlying
with a usable chain at S earned from S's close to the close of the h-th session after it.

The contracts are chosen at S from S's chain alone: the first listed expiry at least ``tenor_days``
calendar days after S and not before the window's end T (an expiry before T could not be held
to it), then the at-the-money strike (the listed strike nearest the underlying's quote with both a
call and a put quoted two-sided; the lower on a tie) or, for ``put_delta_NN``, the put whose own
delta (``quant/edges/chain_pnl.leg_delta``) is nearest ``-NN/100``. Entry is the mid and the ask of
S's snapshot; exit the mid and the bid of T's, or the intrinsic value at expiry (an expiry on T).

A name is UNMEASURED, with a reason and no P&L, when any session from S to T lacks what the row
needs: a chain that is missing (``NO_CHAIN:<day>``) or ``STALE_DATA`` (``STALE_CHAIN:<day>``, ADR
0054), never filled from an earlier session; a contract not quoted two-sided at the exit
(``NO_EXIT_QUOTE``) or whose delta cannot be computed on a hedge session (``NO_DELTA:<day>``); no
listed expiry to hold (``NO_EXPIRY``) or no two-sided strike to enter (``NO_ENTRY_QUOTE``).
"""

import re
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from datetime import date, datetime

import numpy as np
import pandas as pd

from algotrade.data.chains import OK_LABEL, STALE
from algotrade.engines.structures.chain import DayChain, Labels
from algotrade.engines.structures.marking import DAYS_PER_YEAR, LegColumn, Window, mark_window
from algotrade.features.rollups.positioning.chain_inputs import two_sided_mid
from algotrade.quant.edges.chain_pnl import hedged_pnl, leg_delta, long_pnl

OK = OK_LABEL
ATM_STRADDLE = "atm_straddle"
_PUT_DELTA = re.compile(r"put_delta_(\d{2})")
# The marking, expiry value, exit fallback and hedge are ``engines/structures`` (ADR 0088, E3a);
# this module chooses a v1 structure's contracts and shapes the stored row.
ROW_COLUMNS = (
    "instrument_id", "structure", "tenor_days", "horizon_sessions", "window_end", "call_id",
    "put_id", "expiry", "strike", "entry_spot", "entry_mid", "entry_ask", "exit_spot", "exit_mid",
    "exit_bid", "exit_kind", "pnl_per_premium", "pnl_exec_per_premium", "pnl_per_underlying",
    "hedged_pnl_per_premium", "hedged_pnl_per_underlying", "outcome_status", "outcome_reason",
    "hedge_reason",
)  # fmt: skip


@dataclass(frozen=True)
class Structure:
    """A position held long: a call weight and a put weight, and for a put the target delta."""

    key: str
    call: float
    put: float
    delta: float | None = None


def structure_of(key: str) -> Structure:
    """The grain structure ``key``: ``atm_straddle`` or ``put_delta_NN`` (a ``ValueError`` else)."""
    if key == ATM_STRADDLE:
        return Structure(key, 1.0, 1.0)
    found = _PUT_DELTA.fullmatch(key)
    if found is None or not 0 < int(found.group(1)) < 100:
        raise ValueError(f"unknown chain structure {key!r}")
    return Structure(key, 0.0, 1.0, int(found.group(1)) / 100.0)


def _entry_contracts(entry: DayChain, s: Structure, tenor: int, end: date) -> pd.DataFrame:
    """One row per usable underlying at the entry: its contracts (``call_id`` / ``put_id``), the
    expiry and strike, or ``reason`` (``NO_EXPIRY`` / ``NO_ENTRY_QUOTE``)."""
    quotes = entry.options
    ids = sorted(i for i, label in entry.labels.items() if label == OK)
    rows: list[dict[str, object]] = []
    if quotes is None or quotes.empty:
        return pd.DataFrame({"instrument_id": ids, "reason": "NO_EXPIRY"})
    quotes = quotes[quotes["underlying_id"].isin(ids)].copy()
    quotes["expiry"] = pd.to_datetime(quotes["expiry"]).dt.date
    target = max(entry.day.toordinal() + tenor, end.toordinal())
    by_name = dict(iter(quotes.groupby("underlying_id")))
    for name in ids:
        row: dict[str, object] = {"instrument_id": name, "reason": None}
        rows.append(row)
        chain = by_name.get(name)
        if not np.isfinite(entry.spots.get(name, np.nan)):
            row["reason"] = "NO_ENTRY_QUOTE"  # a chain with no underlying quote prices no strike
            continue
        later = None if chain is None else chain[chain["expiry"].map(date.toordinal) >= target]
        if later is None or later.empty:
            row["reason"] = "NO_EXPIRY"
            continue
        expiry = later["expiry"].min()
        pick = _pick_strike(
            later[later["expiry"] == expiry], s, float(entry.spots[name]), expiry, entry.day
        )
        if pick is None:
            row["reason"] = "NO_ENTRY_QUOTE"
            continue
        row.update(expiry=expiry, **pick)
    return pd.DataFrame(rows)


def _pick_strike(
    chain: pd.DataFrame, s: Structure, spot: float, expiry: date, day: date
) -> dict[str, object] | None:
    """``strike`` and the contract ids at one expiry's quotes, or None without a two-sided pick."""
    two = chain.assign(mid=two_sided_mid(chain["bid"], chain["ask"]))
    two = two[two["mid"].notna()]
    calls = two[two["right"] == "C"].drop_duplicates("strike").set_index("strike")
    puts = two[two["right"] == "P"].drop_duplicates("strike").set_index("strike")
    if s.delta is None:
        strikes = calls.index.intersection(puts.index)
        if len(strikes) == 0:
            return None
        gap = np.abs(strikes.to_numpy(float) - spot)
        strike = float(strikes.to_numpy(float)[np.lexsort((strikes.to_numpy(float), gap))[0]])
        return {
            "strike": strike,
            "call_id": str(calls.at[strike, "instrument_id"]),
            "put_id": str(puts.at[strike, "instrument_id"]),
        }
    if puts.empty:
        return None
    put_strikes = puts.index.to_numpy(float)
    t = max((expiry - day).days, 0) / DAYS_PER_YEAR
    delta = leg_delta(puts["mid"].to_numpy(float), spot, put_strikes, t, False)
    gap = np.abs(np.abs(delta) - s.delta)
    if not np.isfinite(gap).any():
        return None
    best = int(np.lexsort((put_strikes, np.where(np.isfinite(gap), gap, np.inf)))[0])
    return {
        "strike": float(put_strikes[best]),
        "call_id": None,
        "put_id": str(puts.iloc[best]["instrument_id"]),
    }


type Loader = Callable[[date, Collection[str] | None], DayChain]


def structure_rows(
    sessions: Sequence[date], load: Loader, structure: str, tenor_days: int, horizon: int
) -> tuple[pd.DataFrame, datetime | None]:
    """The ``ROW_COLUMNS`` rows of the window ``sessions`` (S..T in order, T the ``horizon``-th
    after S) and the latest ``knowledge_ts`` among the chain partitions read. ``load(day, ids)``
    is the chain of ``day``: all of it for the entry (``ids`` None), then only the contracts the
    entry chose."""
    s = structure_of(structure)
    entry = load(sessions[0], None)
    picks = _entry_contracts(entry, s, tenor_days, sessions[-1])
    held_ids = {
        str(c) for col in ("call_id", "put_id") if col in picks for c in picks[col].dropna()
    }
    days = [entry, *(load(d, held_ids) for d in sessions[1:])]
    known = max((d.known for d in days if d.known is not None), default=None)
    n = len(picks)
    out = pd.DataFrame(index=range(n), columns=list(ROW_COLUMNS), dtype=object)
    if n == 0:
        return out, known
    out["instrument_id"] = picks["instrument_id"].to_numpy()
    out["structure"], out["tenor_days"], out["horizon_sessions"] = structure, tenor_days, horizon
    out["window_end"] = days[-1].day
    reason = picks["reason"].astype(object).to_numpy().copy()
    ok = pd.isna(picks["reason"]).to_numpy()  # the names with contracts at the entry
    if not ok.any():
        return _finish(out, reason, np.full(n, None, object)), known
    expiry = pd.Series(picks["expiry"]).reset_index(drop=True)
    strike = picks["strike"].astype(float).to_numpy()
    legs = [
        LegColumn(right, weight, picks[col].fillna(""), strike, expiry)
        for right, weight, col in (("C", s.call, "call_id"), ("P", s.put, "put_id"))
        if weight
    ]
    window = Window(picks["instrument_id"], legs, ok, reason, np.full(n, None, dtype=object))
    out["call_id"], out["put_id"] = picks["call_id"].to_numpy(), picks["put_id"].to_numpy()
    out["expiry"], out["strike"] = expiry.to_numpy(), strike
    marks = mark_window(days, window, Labels(OK, STALE))
    entry_mid, entry_ask = marks.entry_mid, marks.entry_exec
    spots, deltas = marks.spots, marks.deltas
    exit_mid, exit_bid, at_expiry = marks.exit_mid, marks.exit_exec, marks.at_expiry
    held = window
    spot0 = spots[0]
    mid, executable, per_underlying = long_pnl(entry_mid, entry_ask, exit_mid, exit_bid, spot0)
    with np.errstate(invalid="ignore", divide="ignore"):
        hedge = hedged_pnl(entry_mid, exit_mid, np.vstack(spots).T, np.vstack(deltas).T)
        h_premium = np.where(entry_mid > 0, hedge / entry_mid, np.nan)
        h_underlying = np.where(spot0 > 0, hedge / spot0, np.nan)
    out["entry_spot"], out["entry_mid"], out["entry_ask"] = spot0, entry_mid, entry_ask
    out["exit_spot"], out["exit_mid"], out["exit_bid"] = spots[-1], exit_mid, exit_bid
    out["exit_kind"] = np.where(at_expiry, "INTRINSIC", "QUOTE")
    for column, values in (
        ("pnl_per_premium", mid), ("pnl_exec_per_premium", executable),
        ("pnl_per_underlying", per_underlying), ("hedged_pnl_per_premium", h_premium),
        ("hedged_pnl_per_underlying", h_underlying),
    ):  # fmt: skip
        out[column] = values
    complete = np.isfinite(mid) & np.isfinite(executable) & np.isfinite(per_underlying)
    held.fail(~complete, "NO_PNL")
    held.fail_hedge(~(np.isfinite(h_premium) & np.isfinite(h_underlying)), "NO_PNL")
    return _finish(out, held.reason, held.hedge), known


RESULT_NULLS = (
    "exit_spot", "exit_mid", "exit_bid", "exit_kind", "pnl_per_premium", "pnl_exec_per_premium",
    "pnl_per_underlying", "hedged_pnl_per_premium", "hedged_pnl_per_underlying",
)  # fmt: skip
HEDGE_NULLS = ("hedged_pnl_per_premium", "hedged_pnl_per_underlying")


def _finish(out: pd.DataFrame, reason: np.ndarray, hedge: np.ndarray) -> pd.DataFrame:
    """Set the status and reasons. An UNMEASURED row has its exit and every P&L nulled; a
    COMPLETE row with a ``hedge_reason`` has only its hedged P&L nulled."""
    bad = pd.notna(reason)
    shown = pd.Series(hedge, index=out.index, dtype=object).mask(bad, None)
    out["hedge_reason"] = shown
    out.loc[shown.notna(), list(HEDGE_NULLS)] = None
    out["outcome_status"] = np.where(bad, "UNMEASURED", "COMPLETE")
    out["outcome_reason"] = pd.Series(reason, index=out.index).where(bad, None)
    out.loc[bad, list(RESULT_NULLS)] = None
    return out
