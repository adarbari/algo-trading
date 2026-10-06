"""The regime label's history as bands (ADR 0047): for the sessions of ``start..end`` (explicit
dates, never after ``ctx.session``: a window past it would show what the session did not know),
each session's label read from its own partition of the market's ``regime@v2`` table, and runs
of consecutive sessions with the same label merged server-side into ``RegimeBand`` (the browser
only draws them, ADR 0038). A session with no stored label (no partition, no row, a null or an
unknown value, or the field not in the catalogue yet) is an ``UNKNOWN`` band: never carried
forward from an earlier session. Range grain (docs/api/read-model.md "Session resolution")."""

from dataclasses import dataclass
from datetime import date

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.instruments import market_id
from algotrade.core.time.calendar import sessions_between
from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments.series import load_series
from algotrade.services.read.market.features import US
from algotrade.services.read.regime.fields import LABEL
from algotrade.services.read.regime.regime import KNOWN, RegimeLabel


@dataclass(frozen=True)
class RegimeBand:
    """Consecutive sessions ``start..end`` (inclusive, the first and last of the run) with the
    same ``label``."""

    start: date
    end: date
    label: RegimeLabel


def _labels(ctx: ReadContext, start: date, end: date) -> dict[date, RegimeLabel]:
    """The stored label of each session of ``start..end`` that has one."""
    if LABEL not in ctx.features.field_types("market"):
        return {}
    mid = market_id(US)
    series = load_series(ctx, [mid], [LABEL], start, end, entity="market")[mid]
    known = {label.value: label for label in KNOWN}
    found = ((p.session, known.get(str(p.values[0]))) for p in series.points)
    return {day: label for day, label in found if label is not None}


def load_regime_bands(ctx: ReadContext, start: date, end: date) -> tuple[RegimeBand, ...]:
    """The regime of every session in ``start..end`` (``end`` on or before the session's date),
    as bands, oldest first. ``ConfigurationError`` for a window that ends after the session or
    ends before it starts."""
    if end > ctx.session.date:
        raise ConfigurationError(f"end {end} is after the session {ctx.session.date}")
    if end < start:
        raise ConfigurationError(f"end {end} is before start {start}")
    labels = _labels(ctx, start, end)
    bands: list[RegimeBand] = []
    for day in sessions_between(start, end):
        label = labels.get(day, RegimeLabel.UNKNOWN)
        if bands and bands[-1].label is label:
            bands[-1] = RegimeBand(bands[-1].start, day, label)
        else:
            bands.append(RegimeBand(day, day, label))
    return tuple(bands)
