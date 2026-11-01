"""The position-level fields of an open trade, computed at each close (ADR 0088, design 2.4a;
``POSITION_FIELDS`` declares them): from that close's spot and marks and the trade's entry facts,
never from a later session. ``walk_fields`` gives one row per close (``position.<name>`` -> value,
None where it cannot be computed or does not apply) and the running ``max_adverse``. Pure and
independent of how a mark was priced: a share position passes its own value as the mark."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from algotrade.core.model.fields import position_field
from algotrade.core.model.predicates import FieldValue


@dataclass(frozen=True)
class Short:
    """A short option leg's strike and right (``C`` / ``P``), for the distance to the strike."""

    strike: float
    right: str


@dataclass(frozen=True)
class EntryFacts:
    """What the trade fixed at entry: the session ``day`` and underlying ``spot``, the position's
    signed ``value`` (long +, short -, so a credit is negative), the ``collateral`` its loss is
    measured against (None: none), its ``shorts`` and the nearest ``expiry`` (None: shares)."""

    day: date
    spot: float
    value: float
    collateral: float | None = None
    shorts: tuple[Short, ...] = ()
    expiry: date | None = None


@dataclass(frozen=True)
class CloseFacts:
    """One close: the session ``day`` (a session counter ``index`` from entry, 1 the first close
    after it), the underlying's ``spot``, the position's signed mark ``value`` and net ``delta``
    (None where either cannot be computed)."""

    day: date
    index: int
    spot: float
    value: float | None
    delta: float | None = None


def _ratio(num: float | None, den: float | None) -> float | None:
    return None if num is None or not den or den <= 0 else num / den


def _toward_itm(spot: float, shorts: tuple[Short, ...]) -> float | None:
    """(spot - nearest short strike) / spot, signed toward in the money: positive when the nearest
    short leg is in the money."""
    if not shorts or spot <= 0:
        return None
    near = min(shorts, key=lambda s: (abs(spot - s.strike), s.strike))
    return ((spot - near.strike) if near.right == "C" else (near.strike - spot)) / spot


def fields_at(
    entry: EntryFacts, close: CloseFacts, worst_loss: float | None
) -> dict[str, FieldValue]:
    """``position.*`` at ``close``. ``worst_loss`` is the largest mark loss (>= 0) to date."""
    known = close.value is not None and math.isfinite(close.value)
    pnl = close.value - entry.value if known else None  # type: ignore[operator]
    credit = -entry.value if entry.value < 0 else None
    option = entry.expiry is not None
    row: dict[str, FieldValue] = {
        "days_held": close.index,
        "move_since_entry_pct": (close.spot - entry.spot) / entry.spot if entry.spot else None,
        "profit_share_of_credit": _ratio(pnl, credit),
        "mark_loss_share_of_collateral": _ratio(worst_loss, entry.collateral),
        "position_delta": close.delta if option else None,
        "distance_to_strike_pct": _toward_itm(close.spot, entry.shorts) if option else None,
        "dte": (entry.expiry - close.day).days if entry.expiry else None,
    }
    return {position_field(k): v for k, v in row.items()}


def walk_fields(entry: EntryFacts, closes: Sequence[CloseFacts]) -> list[dict[str, FieldValue]]:
    """One row of ``position.*`` per close, in order; the running worst mark loss carries over
    closes whose mark is missing."""
    rows: list[dict[str, FieldValue]] = []
    worst: float | None = None
    for close in closes:
        if close.value is not None and math.isfinite(close.value):
            loss = max(0.0, entry.value - close.value)
            worst = loss if worst is None else max(worst, loss)
        rows.append(fields_at(entry, close, worst))
    return rows


def max_adverse(entry: EntryFacts, closes: Sequence[CloseFacts]) -> float | None:
    """The worst mark loss over the trade as a share of collateral (``max_adverse``, always stored;
    the exit rule's input): None with no collateral or no marked close."""
    rows = walk_fields(entry, closes)
    return rows[-1][position_field("mark_loss_share_of_collateral")] if rows else None  # type: ignore[return-value]
