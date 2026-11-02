"""What an underlying's option figures are priced from for exactly the session (ownership
``option-grid-read``): its chain (``chains/option_quotes``, the vendor quotes, which never leave
the server), its spot (``chains/underlying_quotes``), the Treasury curve the session sees and the
dividend yield by catalogue name, read once and shared by the option grid (``grid.py``) and the
option calculators (``services/preview/options/``), so the two price from the same inputs.

Session grain (ADR 0036): never an older chain; a missing chain or curve partition is
NO_PARTITION (never r = 0), a name with no rows NO_ROW (NOT_APPLICABLE when it is not
optionable), no usable spot NO_ROW. ``report_inside`` is the next report falling after the
session and on or before an expiry, UNKNOWN (never False) when its date is not known.
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade.core.model.errors import MissingDataError
from algotrade.data import rates
from algotrade.data.chains import OPTION_QUOTES, UNDERLYING_QUOTES
from algotrade.features.rollups.options.iv30 import positive_spots
from algotrade.quant.rates import YieldCurve
from algotrade.services.read.availability.cause import feature_cause, table_cause
from algotrade.services.read.context import ReadContext, partition
from algotrade.services.read.instruments.features import FeatureValue, load_feature_values
from algotrade.services.read.values import Unknown, UnknownCode

__all__ = [
    "DIV_YIELD",
    "NEXT_REPORT",
    "OPTIONABLE",
    "PricingInputs",
    "gap",
    "load_session_inputs",
    "report_inside",
]

NEXT_REPORT = "rollup.earnings@v1.next_earnings_date"
DIV_YIELD = "feature.div_yield"
OPTIONABLE = "instrument.optionable"
_COLUMNS = [
    "underlying_id", "expiry", "right", "strike", "bid", "ask", "open_interest", "volume",
]  # fmt: skip


@dataclass(frozen=True)
class PricingInputs:
    """One underlying's chain (``expiry`` as a date, one row per contract), positive spot,
    the session's curve and dividend yield ``q`` (0 when none is stored: ``q_known`` False),
    and its stored next report date (``report``, by catalogue name)."""

    chain: pd.DataFrame
    spot: float
    curve: YieldCurve
    q: float
    q_known: bool
    report: FeatureValue


def gap(ctx: ReadContext, code: UnknownCode, status: str, why: str, table: str) -> Unknown:
    """``code`` with the admin-only cause naming ``table``, ``status`` and ``why``."""
    cause = table_cause(table, why, status, ctx.session.date)
    return Unknown(code, cause, None, ctx.kind_of(code, table))


def _chain(ctx: ReadContext, underlying_id: str) -> pd.DataFrame | Unknown:
    """The session's quotes of ``underlying_id`` (expiry as a date). The partition is read once
    per published state with its columns pruned; the underlying's chain stays in the cache."""
    key = ("option-grid-chain", ctx.session.date, underlying_id, ctx.reader.version())
    found = ctx.cache.get(key)
    if found is None:
        whole = partition(ctx, OPTION_QUOTES, columns=_COLUMNS)
        if isinstance(whole, Unknown):
            return whole
        chain = whole[whole["underlying_id"].astype(str) == underlying_id]
        chain = chain.assign(expiry=pd.to_datetime(chain["expiry"]).dt.date)
        found = chain.drop_duplicates(["instrument_id"]).reset_index(drop=True)
        ctx.cache.put(key, found)
    return found


def _curve(ctx: ReadContext) -> YieldCurve | Unknown:
    """The Treasury curve the session sees; a missing one is NO_PARTITION, never r = 0."""
    day = ctx.session.date.isoformat()
    try:
        seen = rates.curve(ctx.reader, ctx.session.date)
    except MissingDataError:
        why = f"{rates.TABLE} has no curve on or before {day}"
        return gap(ctx, UnknownCode.NO_PARTITION, "NO_PARTITION", why, rates.TABLE)
    if seen.pre_snapshot:  # the earliest stored curve is after the session: a later one
        why = f"{rates.TABLE} has no curve on or before {day} (the earliest is later)"
        return gap(ctx, UnknownCode.NO_PARTITION, "PRE_SNAPSHOT", why, rates.TABLE)
    return seen.yield_curve()


def _spot(ctx: ReadContext, underlying_id: str) -> float | Unknown:
    quotes = partition(ctx, UNDERLYING_QUOTES, instruments=[underlying_id])
    if isinstance(quotes, Unknown):
        return quotes
    spots = positive_spots(quotes)
    if underlying_id in spots.index:
        return float(spots[underlying_id])
    why = f"{UNDERLYING_QUOTES} has no positive price of {underlying_id} for {ctx.session.date}"
    return gap(ctx, UnknownCode.NO_ROW, "NO_SPOT", why, UNDERLYING_QUOTES)


def _no_chain(ctx: ReadContext, underlying_id: str, optionable: FeatureValue) -> Unknown:
    if optionable.value is False:
        why = f"{underlying_id} is not optionable"
        return gap(ctx, UnknownCode.NOT_APPLICABLE, "NOT_APPLICABLE", why, OPTION_QUOTES)
    why = f"{OPTION_QUOTES} has no quotes of {underlying_id} for {ctx.session.date}"
    return gap(ctx, UnknownCode.NO_ROW, "NO_ROW", why, OPTION_QUOTES)


def report_inside(session: date, expiry: date, report: FeatureValue) -> bool | Unknown:
    """The next report falls after the session and on or before the expiry; UNKNOWN (never
    False) when its date is not known."""
    if report.unknown is not None:
        return report.unknown
    if not isinstance(report.value, str):
        cause = feature_cause(NEXT_REPORT, "no next report date stored", "NULL", session)
        return Unknown(UnknownCode.NULL, cause)
    return session < date.fromisoformat(report.value) <= expiry


def load_session_inputs(
    ctx: ReadContext, underlying_id: str, extra: tuple[str, ...] = ()
) -> tuple[PricingInputs, tuple[FeatureValue, ...]] | Unknown:
    """``underlying_id``'s inputs for ``ctx.session`` and the values of the catalogue names
    ``extra`` (in order), or why the name cannot be priced."""
    asked = [OPTIONABLE, NEXT_REPORT, DIV_YIELD, *extra]
    values = load_feature_values(ctx, [underlying_id], asked).get(underlying_id)
    if values is None:  # not in the session's reference snapshot
        why = f"{underlying_id} is not in the session's reference snapshot"
        return gap(ctx, UnknownCode.NO_ROW, "NO_ROW", why, OPTION_QUOTES)
    optionable, report, dividend, *more = values
    chain = _chain(ctx, underlying_id)
    curve = _curve(ctx)
    if isinstance(chain, Unknown):
        return chain
    if isinstance(curve, Unknown):
        return curve
    if chain.empty:
        return _no_chain(ctx, underlying_id, optionable)
    spot = _spot(ctx, underlying_id)
    if isinstance(spot, Unknown):
        return spot
    q_known = dividend.unknown is None and isinstance(dividend.value, int | float)
    q = float(dividend.value) if q_known and dividend.value is not None else 0.0
    return PricingInputs(chain, spot, curve, q, q_known, report), tuple(more)
