"""The forward-outcome arithmetic of the ``outcomes`` task (ADR 0053 decision 3): for one window
(start session S, end session T, horizon h) and the names eligible at S, each name's return and
path fields from daily bars split-adjusted as of T (``data.prices.SessionBars.window``).

A name is eligible when it was in the universe at S and has a bar at S. Its row is
- COMPLETE when it has a bar at T: ``fwd_return`` = close(T) / close(S) - 1;
- DELISTED when it has no bar at T and the reference records it delisted after S (the weekly
  reference build stamps ``delisted_on`` when it notices, after the last bar; the task passes
  only the stamps within the ``RECHECK`` sessions after T, the listing history's last trading
  days on or before T): measured to its
  last bar in the window (a name whose last bar is S: a zero return, no volatility); the
  delisting return itself (a cash-out, a final print) is not measured;
- UNMEASURED, with the reason ``BAD_BAR`` and no return, when a bar of the window S..T (S
  included) was flagged by ``bar-quality`` (ADR 0061) and dropped at read time: a return over a
  bad price is not a measurement. A flagged S counts as eligible (a name with a flagged bar at S
  is not silently dropped); the harness reads the row as "unmeasured, not a miss";
- otherwise absent, with a reason (a gap at T, or a name not yet recorded as delisted: the
  task recomputes recent windows each night, so a later reference build turns it into a row).

The path fields run over the bars after S up to the measured end: ``fwd_max_return`` from the
highs (favourable excursion), ``fwd_max_drawdown`` from the lows (adverse excursion, a positive
fraction, 0 when no low is below close(S)), ``fwd_realised_vol`` the annualised standard
deviation of the daily log close returns (null under two returns). ``fwd_excess_return`` is
``fwd_return`` minus the benchmark's over the same sessions (null without its bars). Max
return, drawdown and volatility always stop at the last bar.

Delistings (ADR 0087 decision 5): with ``events`` (id -> ``(last_session, delisting_return,
basis)`` of the delisting snapshot, read at write time) the rows also carry the
delisting step beside the v2 figures: a DELISTED name whose last bar is the event's
``last_session``, inside (S, T], gets its ``delisting_return`` and ``delisting_basis``; a DELISTED
name with no such event is ``NO_EVENT`` (no return, never a silent zero); a COMPLETE name (a bar
at T) has neither, whatever an event says (``unapplied_delistings`` counts them). The rows are
the v2 figures; ``v2_view`` and ``v3_view`` give the two tables' columns, ``v3_view`` folding the
step in: ``fwd_return`` = (1 + last-bar return) x (1 + delisting_return) - 1, the excess moving
with it, so the zero figure of a row is (1 + fwd) / (1 + delisting_return) - 1. Pure: no storage,
no clock.
"""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from algotrade.storage.tables.schemas import NO_EVENT, UNMEASURED

TRADING_DAYS = 252  # annualises the realised volatility
BAD_BAR = "BAD_BAR"  # the outcome_reason of an UNMEASURED row (ADR 0061)
NO_END_BAR = "no bar at the window end (a gap, or left the universe without a delisting date)"
_COLUMNS = (
    "instrument_id", "fwd_return", "fwd_excess_return", "fwd_max_return", "fwd_max_drawdown",
    "fwd_realised_vol", "outcome_status", "outcome_reason",
)  # fmt: skip
DELISTING_COLUMNS = ("delisting_return", "delisting_basis")  # the v3 columns, beside the v2 ones
Events = Mapping[str, Sequence[tuple[date, float, str]]]  # id -> (last_session, return, basis)


@dataclass(frozen=True)
class Window:
    """``sessions`` are the exchange sessions S..T (h + 1 of them)."""

    sessions: tuple[date, ...]

    @property
    def start(self) -> date:
        return self.sessions[0]

    @property
    def end(self) -> date:
        return self.sessions[-1]

    @property
    def horizon(self) -> int:
        return len(self.sessions) - 1


def window_rows(
    bars: pd.DataFrame,
    window: Window,
    eligible: Collection[str],
    benchmark: str | None,
    delisted: Mapping[str, date],
    flagged: Collection[tuple[str, date]] = (),
    events: Events | None = None,
) -> tuple[pd.DataFrame, dict[str, str]]:
    """``bars`` (``instrument_id``, ``session_date``, ``high``, ``low``, ``close``; S..T, adjusted
    as of T) -> (one row per measured name, ``_COLUMNS``; reason per eligible name without one).
    ``eligible``: the universe at S (names without a bar at S are dropped, not reasons);
    ``benchmark``: its instrument id, or None; ``delisted``: id -> delisting date, as the
    latest reference snapshot records it; ``flagged``: the (instrument, session) of the bars
    dropped as flagged (``SessionBars.flagged``); ``events``: the delisting events (None: the rows
    have no ``DELISTING_COLUMNS``)."""
    close, high, low = (wide_closes(bars, window, field) for field in ("close", "high", "low"))
    bad = {i for i, d in flagged if window.start <= d <= window.end and i in eligible}
    unmeasured = sorted(
        i
        for i in bad
        if (i, window.start) in flagged
        or (i in close.columns and pd.notna(close.at[window.start, i]))
    )
    ids = np.array(
        [
            i
            for i in close.columns
            if i in eligible and i not in bad and pd.notna(close.at[window.start, i])
        ]
    )
    if not len(ids):
        return _unmeasured_rows(unmeasured, events is not None), {}
    c = close[ids].to_numpy(dtype=float)
    complete = ~np.isnan(c[-1])
    gone = np.array([_gone(delisted.get(i), window) for i in ids])
    kept = complete | gone
    reasons = {str(i): NO_END_BAR for i in ids[~kept]}
    ids, c, complete = ids[kept], c[:, kept], complete[kept]
    last = last_bar(c)
    start = c[0]
    fwd = c[last, np.arange(len(ids))] / start - 1
    rows = pd.DataFrame(
        {
            "instrument_id": ids,
            "fwd_return": fwd,
            "fwd_excess_return": fwd - _benchmark_return(close, benchmark, last),
            "fwd_max_return": _excursion(high[ids], last, start, np.fmax) / start - 1,
            "fwd_max_drawdown": np.maximum(
                0.0, 1 - _excursion(low[ids], last, start, np.fmin) / start
            ),
            "fwd_realised_vol": _realised_vol(c, last),
            "outcome_status": np.where(complete, "COMPLETE", "DELISTED"),
            "outcome_reason": None,
        }
    )
    if events is not None:
        step, basis = _delisting_step(ids, window, last, complete, events)
        rows = rows.assign(delisting_return=step, delisting_basis=basis)
    if unmeasured:
        rows = pd.concat([rows, _unmeasured_rows(unmeasured, events is not None)],
                         ignore_index=True)  # fmt: skip
    return rows, reasons


def _unmeasured_rows(ids: Sequence[str], delistings: bool = False) -> pd.DataFrame:
    """The UNMEASURED rows of ``ids``: a reason, no return and no path fields."""
    frame = pd.DataFrame(
        {
            "instrument_id": list(ids),
            **dict.fromkeys(_COLUMNS[1:6], np.nan),
            "outcome_status": UNMEASURED,
            "outcome_reason": BAD_BAR,
        },
        columns=list(_COLUMNS),
    )
    if delistings:
        frame = frame.assign(delisting_return=np.nan, delisting_basis=None)
    return frame


def _delisting_step(
    ids: np.ndarray, window: Window, last: np.ndarray, complete: np.ndarray, events: Events
) -> tuple[np.ndarray, np.ndarray]:
    """Per measured name, its (``delisting_return``, ``delisting_basis``): an event applies only to
    a DELISTED name whose last bar is the event's ``last_session``, inside (S, T]."""
    step = np.full(len(ids), np.nan)
    basis = np.full(len(ids), None, dtype=object)
    for j, i in enumerate(ids):
        if complete[j]:
            continue
        basis[j] = NO_EVENT
        ended = window.sessions[last[j]]
        for day, value, kind in events.get(str(i), ()):
            if window.start < day <= window.end and day == ended:
                step[j], basis[j] = value, kind
    return step, basis


def unapplied_delistings(rows: pd.DataFrame, window: Window, events: Events) -> int:
    """The names whose delisting event disagrees with their bars, counted in the run's stats: a bar
    at T while the event's last session is before T (a name that came back, or a wrong date), and
    a DELISTED row whose last bar is not the event's last session in (S, T] (``NO_EVENT``). A
    window ending on the event's own last session is COMPLETE and right: not counted."""
    count = 0
    for iid, status, basis in zip(
        rows["instrument_id"].astype(str), rows["outcome_status"], rows["delisting_basis"],
        strict=True,
    ):  # fmt: skip
        days = [d for d, _, _ in events.get(iid, ()) if window.start < d <= window.end]
        if status == "COMPLETE":
            count += any(d < window.end for d in days)
        elif status == "DELISTED" and basis == NO_EVENT:
            count += bool(days)
    return count


def v2_view(rows: pd.DataFrame) -> pd.DataFrame:
    """``forward_returns@v2``'s columns: the last-bar figures, no delisting step."""
    return rows.drop(columns=list(DELISTING_COLUMNS), errors="ignore")


def v3_view(rows: pd.DataFrame) -> pd.DataFrame:
    """``forward_returns@v3``'s rows: the delisting return folded into ``fwd_return`` and
    ``fwd_excess_return`` where an event applied, every other figure as in v2."""
    step = rows["delisting_return"]
    hit = (step.notna() & (step != 0)).to_numpy()
    fwd = np.where(hit, (1 + rows["fwd_return"]) * (1 + step) - 1, rows["fwd_return"])
    excess = np.where(hit, rows["fwd_excess_return"] + (fwd - rows["fwd_return"]),
                      rows["fwd_excess_return"])  # fmt: skip
    return rows.assign(fwd_return=fwd, fwd_excess_return=excess)


def wide_closes(bars: pd.DataFrame, window: Window, field: str) -> pd.DataFrame:
    """``field`` as sessions x instruments over exactly S..T (a session with no bars: NaN)."""
    frame = bars.assign(instrument_id=bars["instrument_id"].astype(str))
    table = frame.pivot(index="session_date", columns="instrument_id", values=field)
    return table.reindex(list(window.sessions))


def _gone(delisted_on: date | None, window: Window) -> bool:
    return delisted_on is not None and pd.notna(delisted_on) and delisted_on > window.start


def last_bar(c: np.ndarray) -> np.ndarray:
    """Per column, the row of its last bar (row 0, S, always has one)."""
    present = ~np.isnan(c)
    return len(c) - 1 - np.argmax(present[::-1], axis=0)


def _through(values: np.ndarray, last: np.ndarray) -> np.ndarray:
    """``values`` after S up to each column's ``last`` row; NaN elsewhere."""
    rows = np.arange(len(values))[:, None]
    return np.where((rows >= 1) & (rows <= last[None, :]), values, np.nan)


def _excursion(
    values: pd.DataFrame, last: np.ndarray, start: np.ndarray, pick: np.ufunc
) -> np.ndarray:
    """The extreme (``np.fmax`` / ``np.fmin``) of ``values`` after S; close(S) when none."""
    out = pick.reduce(_through(values.to_numpy(dtype=float), last), axis=0)  # NaN ignored
    return np.where(np.isnan(out), start, out)


def _realised_vol(c: np.ndarray, last: np.ndarray) -> np.ndarray:
    """Annualised stdev of the log returns between consecutive bars from S to ``last``."""
    logs = pd.DataFrame(np.log(np.where(np.arange(len(c))[:, None] <= last[None, :], c, np.nan)))
    returns = logs - logs.ffill().shift(1)
    vol: np.ndarray = (returns.std(ddof=1) * np.sqrt(TRADING_DAYS)).to_numpy(dtype=float)
    return vol


def _benchmark_return(close: pd.DataFrame, benchmark: str | None, last: np.ndarray) -> np.ndarray:
    """The benchmark's return from S to each name's measured end (NaN without both bars)."""
    if benchmark is None or benchmark not in close.columns:
        return np.full(len(last), np.nan)
    b = close[benchmark].to_numpy(dtype=float)
    out: np.ndarray = b[last] / b[0] - 1
    return out
