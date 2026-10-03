"""Grade our values against IBKR's, one ``Row`` per instrument and check (pure, no I/O).

A check is PASS within its tolerance, WARN over it but within ``warn_multiple`` times it,
FAIL beyond, and NA when either side has no value (the note says which). Tolerances come
from ``config/site/verification.toml`` (the reconciliation suite's values, docs/testing.md).

    close, high, low     split-adjusted daily bars: the worst session in the window (relative)
    bars_missing         IBKR sessions in the window we have no bar for (count)
    hv20                 price_stats.hv20 vs close-to-close HV20 on IBKR's closes (relative)
    high_52w             vs the highest IBKR high of the last 252 sessions (relative)
    low_52w              the dividend-gap rule: ours >= IBKR's and above it by at most div_ttm
                         (a dividend-adjusted low sits lower by up to the dividends since)
    div_yield            div_yield (materialised) vs IB's trailing 12 months / close (absolute)
    iv30, iv30_cboe      our iv30 and the Cboe feed's vs IB's implied vol (absolute)
    option_listed        our chain's contract is listed at IBKR (expiry and strike)
    option_mid           IB's mid within ``spread_band`` half-spreads of ours (absolute)
"""

import math
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from algotrade.config.site.settings import VerificationSettings
from algotrade.quant import realized_vol

STATUSES = ("PASS", "WARN", "FAIL", "NA")
YEAR_SESSIONS = 252
MIN_YEAR_SESSIONS = 240  # as price_stats@v2: fewer bars and the 52-week range is unknown
HV_WINDOW = 20


@dataclass(frozen=True)
class Row:
    instrument_id: str
    symbol: str
    check: str
    ours: float | None
    theirs: float | None
    diff: float | None
    tolerance: float | None
    status: str
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def grade(diff: float, tolerance: float, warn_multiple: float) -> str:
    if diff <= tolerance:
        return "PASS"
    return "WARN" if diff <= tolerance * warn_multiple else "FAIL"


def relative(ours: float, theirs: float) -> float:
    return abs(ours - theirs) / abs(theirs) if theirs else math.inf


@dataclass
class Grader:
    """Collects the rows of one instrument."""

    instrument_id: str
    symbol: str
    settings: VerificationSettings
    rows: list[Row] = field(default_factory=list)

    def na(self, check: str, note: str, ours: Any = None, theirs: Any = None) -> None:
        self.rows.append(
            Row(self.instrument_id, self.symbol, check, _number(ours), _number(theirs),
                None, None, "NA", note)
        )  # fmt: skip

    def compare(
        self, check: str, ours: Any, theirs: Any, tolerance: float, mode: str, note: str = ""
    ) -> None:
        """``mode``: ``rel`` (relative to IBKR's value) or ``abs``."""
        o, t = _number(ours), _number(theirs)
        if o is None or t is None:
            missing = "ours" if o is None else "IBKR"
            self.na(check, f"no value ({missing})" + (f"; {note}" if note else ""), o, t)
            return
        diff = relative(o, t) if mode == "rel" else abs(o - t)
        status = grade(diff, tolerance, self.settings.warn_multiple)
        label = f"{mode} diff" + (f"; {note}" if note else "")
        self.rows.append(
            Row(self.instrument_id, self.symbol, check, o, t, diff, tolerance, status, label)
        )

    def graded(self, check: str, ours: float, theirs: float, diff: float, tol: float,
               status: str, note: str) -> None:  # fmt: skip
        self.rows.append(
            Row(self.instrument_id, self.symbol, check, ours, theirs, diff, tol, status, note)
        )


# ----------------------------------------------------------------------------- bars


def compare_bars(g: Grader, ours: pd.DataFrame, theirs: pd.DataFrame, session: date) -> None:
    """``ours`` / ``theirs``: ``date``, ``high``, ``low``, ``close`` (ours split-adjusted as of
    the session; IB's TRADES bars are split-adjusted by IB). Sessions up to ``session``."""
    theirs = theirs[theirs["date"] <= session]
    if theirs.empty:
        for check in ("close", "high", "low", "bars_missing"):
            g.na(check, "IBKR returned no daily bars")
        return
    joined = theirs.merge(ours, on="date", suffixes=("_ibkr", "_ours"))
    s = g.settings
    for check, tol in (("close", s.close_rel), ("high", s.range_rel), ("low", s.range_rel)):
        if joined.empty:
            g.na(check, "no session in common with IBKR")
            continue
        o, t = joined[f"{check}_ours"].to_numpy(), joined[f"{check}_ibkr"].to_numpy()
        with np.errstate(divide="ignore", invalid="ignore"):
            diffs = np.abs(o - t) / np.abs(t)
        worst = int(np.nanargmax(diffs)) if np.isfinite(diffs).any() else 0
        note = f"worst session {joined['date'].iloc[worst]} of {len(joined)} compared"
        g.compare(check, o[worst], t[worst], tol, "rel", note)
    missing = sorted(set(theirs["date"]) - set(ours["date"]))
    shown = ", ".join(map(str, missing[:5])) + (" ..." if len(missing) > 5 else "")
    status = grade(len(missing), s.max_missing_sessions, s.warn_multiple)
    if s.max_missing_sessions == 0 and len(missing) == 1:
        status = "WARN"  # one missing bar: a late or failed fetch, not a systematic gap
    note = f"{len(missing)} of {len(theirs)} IBKR sessions have no bar of ours" + (
        f": {shown}" if missing else ""
    )
    g.graded("bars_missing", float(len(theirs) - len(missing)), float(len(theirs)),
             float(len(missing)), float(s.max_missing_sessions), status, note)  # fmt: skip


def ibkr_hv20(closes: np.ndarray) -> float | None:
    if len(closes) < HV_WINDOW + 1:
        return None
    return _number(realized_vol.close_to_close(closes[-HV_WINDOW - 1 :], HV_WINDOW)[-1])


def compare_stats(
    g: Grader, stats: pd.Series | None, theirs: pd.DataFrame, session: date, div_ttm: Any
) -> None:
    """hv20, high_52w, low_52w from our ``price_stats@v2`` row vs IBKR's bars."""
    theirs = theirs[theirs["date"] <= session]
    ends_on_session = not theirs.empty and theirs["date"].iloc[-1] == session
    if stats is None:
        for check in ("hv20", "high_52w", "low_52w"):
            g.na(check, "no price_stats@v2 row of ours for the session")
        return
    if not ends_on_session:
        for check in ("hv20", "high_52w", "low_52w"):
            g.na(check, "IBKR has no bar for the session", stats.get(check))
        return
    s = g.settings
    g.compare("hv20", stats.get("hv20"), ibkr_hv20(theirs["close"].to_numpy(float)),
              s.hv_rel, "rel", "close-to-close on IBKR closes")  # fmt: skip
    year = theirs.tail(YEAR_SESSIONS)
    if len(year) < MIN_YEAR_SESSIONS:
        g.na("high_52w", f"IBKR has only {len(year)} sessions", stats.get("high_52w"))
        g.na("low_52w", f"IBKR has only {len(year)} sessions", stats.get("low_52w"))
        return
    g.compare("high_52w", stats.get("high_52w"), float(year["high"].max()), s.high_52w_rel,
              "rel", "split-only basis")  # fmt: skip
    _low_52w(g, _number(stats.get("low_52w")), float(year["low"].min()), _number(div_ttm))


def _low_52w(g: Grader, ours: float | None, theirs: float, div_ttm: float | None) -> None:
    s = g.settings
    if ours is None:
        g.na("low_52w", "no value (ours)", None, theirs)
        return
    diff = relative(ours, theirs)
    gap = div_ttm or 0.0
    within = ours >= theirs * (1 - s.extreme_rel) and ours - theirs <= gap + theirs * s.extreme_rel
    if diff <= s.extreme_rel or within:
        note = "rel diff" if diff <= s.extreme_rel else f"within the dividend gap (div_ttm {gap:g})"
        g.graded("low_52w", ours, theirs, diff, s.extreme_rel, "PASS", note)
        return
    status = grade(diff, s.extreme_rel, s.warn_multiple)
    g.graded("low_52w", ours, theirs, diff, s.extreme_rel, status,
             f"outside the dividend gap (div_ttm {gap:g})")  # fmt: skip


# ----------------------------------------------------------------------------- yield, IV


def compare_yield(g: Grader, ours: Any, dividends: pd.DataFrame | None) -> None:
    row = dividends.iloc[0] if dividends is not None and len(dividends) else None
    past = _number(row.get("past12Months")) if row is not None else None
    close = _number(row.get("close")) if row is not None else None
    theirs = past / close if past is not None and close else None
    if theirs is None and row is not None and past is None and _number(ours) == 0.0:
        theirs = 0.0  # IB reports no dividends for a non-payer
    g.compare("div_yield", ours, theirs, g.settings.yield_abs, "abs", "IB trailing 12 months")


def compare_iv(g: Grader, iv30: pd.Series | None, theirs: pd.DataFrame, session: date) -> None:
    on_session = theirs[theirs["date"] == session]
    ibkr = float(on_session["close"].iloc[-1]) if len(on_session) else None
    note = "" if ibkr is not None else "IBKR has no implied vol for the session"
    for check, column in (("iv30", "iv30"), ("iv30_cboe", "iv30_cboe")):
        ours = iv30.get(column) if iv30 is not None else None
        g.compare(check, ours, ibkr, g.settings.iv_abs, "abs", note)


# ----------------------------------------------------------------------------- options


def compare_option(
    g: Grader, ours: pd.Series, listed: bool | None, quote: pd.DataFrame | None
) -> None:
    """``ours``: one stored option quote (bid, ask, expiry, strike, right)."""
    label = f"{ours['right']} {ours['strike']:g} {ours['expiry']}"
    if listed is None:
        g.na("option_listed", f"{label}: IBKR chain parameters unavailable")
    else:
        status = "PASS" if listed else "FAIL"
        g.graded("option_listed", 1.0, float(listed), float(not listed), 0.0, status, label)
    row = quote.iloc[0] if quote is not None and len(quote) else None
    bid, ask = _number(ours.get("bid")), _number(ours.get("ask"))
    t_bid = _number(row.get("bid")) if row is not None else None
    t_ask = _number(row.get("ask")) if row is not None else None
    if None in (bid, ask, t_bid, t_ask) or not (bid and ask and t_ask):
        g.na("option_mid", f"{label}: no two-sided quote (ours {bid}/{ask}, IBKR {t_bid}/{t_ask})")
        return
    assert bid is not None and ask is not None and t_bid is not None and t_ask is not None
    half = max(ask - bid, t_ask - t_bid) / 2
    tol = g.settings.spread_band * half
    note = f"{label}: ours {bid:g}/{ask:g}, IBKR {t_bid:g}/{t_ask:g}"
    g.compare("option_mid", (bid + ask) / 2, (t_bid + t_ask) / 2, tol, "abs", note)


def counts(rows: list[Row]) -> dict[str, int]:
    return {status: sum(r.status == status for r in rows) for status in STATUSES}
