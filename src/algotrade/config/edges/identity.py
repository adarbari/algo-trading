"""The side of an outcome and the identity of an edge document: what a short, long-short, banded
or pair outcome may combine with (``check_side``, ``hold_rank_of``, ``pair_field_of``) and
``identity_dict``, which drops the keys an outcome that never named them would not have had, so a
hash is stable across the arrival of a key."""

from collections.abc import Sequence
from typing import Any

from algotrade.config.site.fields import Table
from algotrade.core.model.errors import ConfigurationError

LONG, SHORT, LONG_SHORT = "long", "short", "long_short"
SIDES = (LONG, SHORT, LONG_SHORT)  # which names an outcome holds and in which direction


def identity_dict(value: Any) -> Any:
    """``value`` (an ``asdict`` of an edge or outcome) without the side keys of a long outcome,
    an unset ``hold_rank`` or ``tenor_days`` and the default weighting: a document that named
    none of them hashes as it did before them, so no stored leg or run is recomputed by their
    arrival (ADR 0053 amendments, ADR 0074)."""
    if isinstance(value, dict):
        long = value.get("side") == LONG and value.get("borrow_bps_annual") is None
        plain = value.get("weighting") == "equal" and value.get("vol_field") is None
        return {
            k: identity_dict(v)
            for k, v in value.items()
            if not (long and k in ("side", "borrow_bps_annual"))
            and not (k in ("tenor_days", "hold_rank", "pair_field") and v is None)
            and not (plain and k in ("weighting", "vol_field"))
        }
    if isinstance(value, (list, tuple)):
        return [identity_dict(v) for v in value]
    return value


def check_side(
    o: Table, side: str, borrow: float | None, kind: str, drawdown: float | None
) -> None:
    """A short or long-short outcome is an excess return with no drawdown limit (the dip of a
    short is the rally, which the store keeps apart); the borrow cost belongs to a short leg."""
    if side == LONG:
        if borrow is not None and kind != "pair_spread":  # a pair's rich leg pays borrow
            raise ConfigurationError(f"{o.where} borrow_bps_annual: only a short leg pays borrow")
        return
    if kind != "excess_return" or drawdown is not None:
        raise ConfigurationError(
            f"{o.where} side: {side!r} needs an excess_return outcome with no max_drawdown"
        )


def hold_rank_of(
    o: Table,
    side: str,
    kind: str,
    schedule: str,
    schedules: Sequence[str],
    horizons: tuple[int, ...],
) -> int | None:
    """The outcome's buy/hold band rank (None: no band). Refused for a spread (``long_short`` has
    no cost rows), a return that is not an excess return and an event or calendar schedule. The
    schedule limit (``month_end``, or ``every_session`` at one session) is stricter than needed:
    windows never overlap on a plain schedule (``sessions.py``), so loosening it is a later PR."""
    if "hold_rank" not in o.names():
        return None
    rank = o.integer("hold_rank", 1, 1)
    if side == LONG_SHORT or kind != "excess_return":
        raise ConfigurationError(
            f"{o.where} hold_rank: a band is for a long or short excess_return (a long_short "
            f"spread has no cost rows to turn over)"
        )
    if schedule not in schedules or (schedule == "every_session" and horizons != (1,)):
        raise ConfigurationError(
            f"{o.where} hold_rank: for now the schedule is month_end, or every_session at "
            f"horizon_sessions = [1] (kept stricter than needed), got {schedule!r} with "
            f"{list(horizons)}"
        )
    return rank


def pair_field_of(
    o: Table, is_pair: bool, benchmark: str, side: str, drawdown: float | None
) -> str | None:
    """The ``pair_field`` of an outcome table: the picks of a pair spread are the cheap legs (side
    ``long``), both legs are raw returns and a spread's dip is not stored."""
    named = " ".join(o.text("pair_field", "").split()) if o.raw("pair_field") is not None else ""
    if not is_pair:
        if named:
            raise ConfigurationError(f"{o.where} pair_field: only a pair_spread outcome has one")
        return None
    if not named:
        raise ConfigurationError(f"{o.where} pair_field: required")
    if benchmark != "none" or side != "long" or drawdown is not None:
        raise ConfigurationError(
            f"{o.where}: a pair_spread needs benchmark = 'none', side long (the picks are the "
            f"cheap legs; the sibling is the short leg) and no max_drawdown"
        )
    return named
