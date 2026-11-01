"""The option grid of an underlying for the session (``OptionGrid``, ownership
``option-grid-read``; ADR 0083's amendment of 2026-11-01, plan docs/ui/evening-desk-plan.md V6):
puts and calls at our delta bands (``band_pick.BANDS``) and expiry buckets
(``band_pick.TARGET_DAYS``), each cell the figures of the short option picked there.

Derived figures only (decision B): our mid premium, our delta and IV, return on collateral,
yield a year, breakeven, the chance of ending below the strike, the spread as a share of the
mid and open interest. There is no bid, ask, last or size field anywhere (a fitness test holds
it); the vendor quotes are read here and never leave. The pick and every figure are
``features/rollups/premium/band_pick.py`` (``short_premium@v1`` is its (0.20, 30-day) cell).

Session grain (ADR 0036): the chain is the session's ``chains/option_quotes`` partition, the
spot ``chains/underlying_quotes``, the rate the Treasury curve the session sees (the one
snapshot rule of ``data.rates``: the bond market's holidays are not the exchange's, and the
feature groups price with the same curve); never an older chain. ``t = days / 365``, r from the
curve at t, q from ``div_yield@v1`` (0 when none is stored, flagged ``q_known = False``: the
same pricing as ``put_wing@v1``). Per-instrument facts come by catalogue name (ADR 0038): the
next report date (``report_inside``: the session is before it and it is on or before the
expiry; UNKNOWN, never False, when the date is not known; not applicable for an ETF). The IV rank
is not here: a page reads it by name (``feature.iv_rank``, ADR 0038), UNKNOWN with its reason
until its history is long enough.

Gaps are ``Unknown`` (``values.py``): no chain or rate partition NO_PARTITION (never r = 0), no
chain rows or no usable spot NO_ROW (a name that is not optionable NOT_APPLICABLE), no expiry
near a bucket, an expiry an earlier bucket took, or no strike near a band NOT_APPLICABLE (the
cause says which), a one-sided quote or a failed vol inversion ILLIQUID. A missing open interest
is None, never 0.

The grid is cached for the session (``ResultCache``, keyed on the published state, ADR 0022).
"""

from dataclasses import asdict, dataclass
from datetime import date

import pandas as pd

from algotrade.core.model.errors import MissingDataError
from algotrade.data import rates
from algotrade.data.chains import OPTION_QUOTES, UNDERLYING_QUOTES
from algotrade.features.rollups.options.iv30 import positive_spots
from algotrade.features.rollups.premium import band_pick
from algotrade.features.rollups.premium.band_pick import BANDS, CALL, PUT
from algotrade.quant.rates import YieldCurve
from algotrade.services.read.availability.cause import feature_cause, table_cause
from algotrade.services.read.context import ReadContext, partition
from algotrade.services.read.instruments.features import FeatureValue, load_feature_values
from algotrade.services.read.values import Unknown, UnknownCode

__all__ = ["GridCell", "GridExpiry", "OptionGrid", "load_option_grid"]

NEXT_REPORT = "rollup.earnings@v1.next_earnings_date"
DIV_YIELD = "feature.div_yield"
OPTIONABLE = "instrument.optionable"
_COLUMNS = ["underlying_id", "expiry", "right", "strike", "bid", "ask", "open_interest"]
_GAPS = {
    band_pick.NO_EXPIRY: "no listed expiry within 30% of {days} days",
    band_pick.DUPLICATE_EXPIRY: "the expiry nearest {days} days is the one a nearer bucket took",
}


@dataclass(frozen=True)
class GridCell(band_pick.BandCell):
    """The short option at one band of one expiry (``band_pick.BandCell``: strike, our delta
    (signed as its right) and IV, the mid premium per share, return on collateral, yield a year,
    breakeven, chance below the strike, the stored quote's spread as a share of the mid and open
    interest) and the |delta| ``band`` it was picked for."""

    band: float


@dataclass(frozen=True)
class GridExpiry:
    """A column of the grid: the expiry that stands for ``bucket`` calendar days and its days,
    or the ``gap`` (no expiry, a duplicate). ``report_inside``: the underlying's next report
    falls after the session and on or before the expiry (UNKNOWN when its date is not known)."""

    bucket: int
    expiry: date | None
    days: int | None
    report_inside: bool | None
    report_inside_unknown: Unknown | None
    gap: Unknown | None


@dataclass(frozen=True)
class OptionGrid:
    """``puts[i][j]`` and ``calls[i][j]`` are the cell of ``columns[i]`` at ``bands[j]``
    (|delta|), or why there is none. ``priced_at``: the underlying's price the cells are priced
    at. ``q_known``: the dividend yield was stored (else priced with 0, like the wings)."""

    underlying_id: str
    session: date
    priced_at: float
    q_known: bool
    bands: tuple[float, ...]
    columns: tuple[GridExpiry, ...]
    puts: tuple[tuple[GridCell | Unknown, ...], ...]
    calls: tuple[tuple[GridCell | Unknown, ...], ...]


def _gap(ctx: ReadContext, code: UnknownCode, status: str, why: str, table: str) -> Unknown:
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
        return _gap(ctx, UnknownCode.NO_PARTITION, "NO_PARTITION", why, rates.TABLE)
    if seen.pre_snapshot:  # the earliest stored curve is after the session: a later one
        why = f"{rates.TABLE} has no curve on or before {day} (the earliest is later)"
        return _gap(ctx, UnknownCode.NO_PARTITION, "PRE_SNAPSHOT", why, rates.TABLE)
    return seen.yield_curve()


def _spot(ctx: ReadContext, underlying_id: str) -> float | Unknown:
    quotes = partition(ctx, UNDERLYING_QUOTES, instruments=[underlying_id])
    if isinstance(quotes, Unknown):
        return quotes
    spots = positive_spots(quotes)
    if underlying_id in spots.index:
        return float(spots[underlying_id])
    why = f"{UNDERLYING_QUOTES} has no positive price of {underlying_id} for {ctx.session.date}"
    return _gap(ctx, UnknownCode.NO_ROW, "NO_SPOT", why, UNDERLYING_QUOTES)


def _no_chain(ctx: ReadContext, underlying_id: str, optionable: FeatureValue) -> Unknown:
    if optionable.value is False:
        why = f"{underlying_id} is not optionable"
        return _gap(ctx, UnknownCode.NOT_APPLICABLE, "NOT_APPLICABLE", why, OPTION_QUOTES)
    why = f"{OPTION_QUOTES} has no quotes of {underlying_id} for {ctx.session.date}"
    return _gap(ctx, UnknownCode.NO_ROW, "NO_ROW", why, OPTION_QUOTES)


def _report_inside(session: date, expiry: date, report: FeatureValue) -> bool | Unknown:
    """The next report falls after the session and on or before the expiry; UNKNOWN (never
    False) when its date is not known."""
    if report.unknown is not None:
        return report.unknown
    if not isinstance(report.value, str):
        cause = feature_cause(NEXT_REPORT, "no next report date stored", "NULL", session)
        return Unknown(UnknownCode.NULL, cause)
    return session < date.fromisoformat(report.value) <= expiry


def _cell(
    ctx: ReadContext,
    chain: pd.DataFrame,
    spot: float,
    deltas: band_pick.OurDeltas,
    expiry: date,
    right: str,
    band: float,
) -> GridCell | Unknown:
    found = band_pick.pick_band(chain, ctx.session.date, expiry, spot, band, right, deltas)
    if isinstance(found, band_pick.BandMiss):
        illiquid = found.reason == band_pick.ILLIQUID
        code = UnknownCode.ILLIQUID if illiquid else UnknownCode.NOT_APPLICABLE
        why = f"{right}s expiring {expiry} at {band:.2f} delta: {found.reason}"
        return _gap(ctx, code, found.reason, why, OPTION_QUOTES)
    return GridCell(**asdict(found), band=band)


def _no_expiry(ctx: ReadContext, underlying_id: str, bucket: band_pick.ExpiryBucket) -> Unknown:
    reason = bucket.reason or band_pick.NO_EXPIRY
    why = f"{underlying_id}: " + _GAPS[reason].format(days=bucket.target)
    return _gap(ctx, UnknownCode.NOT_APPLICABLE, reason, why, OPTION_QUOTES)


def load_option_grid(ctx: ReadContext, underlying_id: str) -> OptionGrid | Unknown:
    """``underlying_id``'s option grid for ``ctx.session``, or why it has none; kept in the
    result cache for the published state (one grid per session and underlying)."""
    key = ("option-grid", ctx.session.date, underlying_id, ctx.reader.version())
    cached = ctx.cache.get(key)
    if cached is None:
        cached = _build(ctx, underlying_id)
        ctx.cache.put(key, cached)
    return cached


def _build(ctx: ReadContext, underlying_id: str) -> OptionGrid | Unknown:
    asked = [OPTIONABLE, NEXT_REPORT, DIV_YIELD]
    values = load_feature_values(ctx, [underlying_id], asked).get(underlying_id)
    if values is None:  # not in the session's reference snapshot
        why = f"{underlying_id} is not in the session's reference snapshot"
        return _gap(ctx, UnknownCode.NO_ROW, "NO_ROW", why, OPTION_QUOTES)
    optionable, report, dividend = values
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
    session = ctx.session.date
    deltas = band_pick.OurDeltas(curve, q)
    columns: list[GridExpiry] = []
    puts: list[tuple[GridCell | Unknown, ...]] = []
    calls: list[tuple[GridCell | Unknown, ...]] = []
    for bucket in band_pick.bucket_expiries(sorted(set(chain["expiry"])), session):
        if bucket.expiry is None:
            gap = _no_expiry(ctx, underlying_id, bucket)
            columns.append(GridExpiry(bucket.target, None, None, None, gap, gap))
            puts.append((gap,) * len(BANDS))
            calls.append((gap,) * len(BANDS))
            continue
        days = (bucket.expiry - session).days
        inside = _report_inside(session, bucket.expiry, report)
        columns.append(
            GridExpiry(
                bucket.target,
                bucket.expiry,
                days,
                None if isinstance(inside, Unknown) else inside,
                inside if isinstance(inside, Unknown) else None,
                None,
            )
        )
        for right, side in ((PUT, puts), (CALL, calls)):
            side.append(
                tuple(_cell(ctx, chain, spot, deltas, bucket.expiry, right, band) for band in BANDS)
            )
    return OptionGrid(
        underlying_id, session, spot, q_known, BANDS, tuple(columns), tuple(puts), tuple(calls),
    )  # fmt: skip
