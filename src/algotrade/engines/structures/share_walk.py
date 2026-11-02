"""The share path walker (ADR 0088, E3c): one share position over the closes of ``bars/1d``, ended
by the first exit of the one ordered rule list (``scan_exits``) or by its horizon. It is the option
engine's evaluator fed from bars: ``position.*`` fields come from ``walk_fields`` with the close
as the mark, catalogue fields of a close are passed in by the caller (None where not stored: the
rule is UNKNOWN there and never fires).

Its rules are ``share_exit_rules`` (``config/edges/positions/spec.py``: the fixed settings as
rules over ``position.move_since_entry_pct``, a share has no credit). Exits are at closes only, so
a gap through the level exits at that close's price, never at the level.

The trade is priced from closes S..k only, the exit close ``k``: the ``move`` of a long is
``close(k) / close(S) - 1`` and of a short its negation. ``max_adverse`` is the worst close below
the entry for a long and null for a short (as the contract has it); it is at closes, not the
intraday dip of ``fwd_max_drawdown``. Pure: no storage, no clock."""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from algotrade.config.edges.positions.spec import ExitRule
from algotrade.core.model.predicates import FieldValue
from algotrade.engines.structures.exits import scan_exits
from algotrade.engines.structures.position_fields import CloseFacts, EntryFacts, walk_fields

HORIZON, DELISTED = "HORIZON", "DELISTED"


@dataclass(frozen=True)
class ShareClose:
    """One close after entry: its session ``day``, ``close`` price and the catalogue ``fields`` of
    the session it is observed at (as a rule names them; absent: UNKNOWN)."""

    day: date
    close: float
    fields: Mapping[str, FieldValue] | None = None


@dataclass(frozen=True)
class ShareWalk:
    """The walk of one name: ``exit_index`` (1 the first close after entry), ``exit_session``,
    ``exit_kind`` (a rule's, ``HORIZON`` or ``DELISTED``), the side's ``gross_return``
    (before cost), the ``underlying_return`` (the name's own), ``max_adverse`` (null: short) and
    ``unknown_closes`` (closes up to the exit where a rule was UNKNOWN)."""

    exit_index: int
    exit_session: date
    exit_kind: str
    gross_return: float
    underlying_return: float
    max_adverse: float | None
    unknown_closes: int


def walk_share(
    side: str, entry_day: date, entry_close: float, closes: Sequence[ShareClose],
    rules: Sequence[ExitRule], horizon: int, *, delisted: bool = False,
) -> ShareWalk | None:  # fmt: skip
    """Walk one share trade over ``closes`` (the sessions after entry, up to ``horizon`` of them).
    None (nothing measured) with no close, a non-positive or non-finite entry, a bad close before
    the exit is known, or fewer closes than ``horizon`` with no exit unless ``delisted`` (the
    reference records the delisting, as the stored outcome requires): then ``DELISTED`` at the
    last close. A bad close after the exit does not matter: the trade is priced from S..k only."""
    closes = closes[:horizon]
    if not closes or not (math.isfinite(entry_close) and entry_close > 0):
        return None
    good = next(
        (i for i, c in enumerate(closes) if not (math.isfinite(c.close) and c.close > 0)),
        len(closes),
    )
    usable = closes[:good]
    if not usable:
        return None
    entry = EntryFacts(entry_day, entry_close, entry_close)
    facts = [CloseFacts(c.day, i + 1, c.close, c.close) for i, c in enumerate(usable)]
    rows = [
        {**(c.fields or {}), **pos}
        for c, pos in zip(usable, walk_fields(entry, facts), strict=True)
    ]
    scan = scan_exits(rules, rows)
    if scan.hit is not None:
        k, kind, unknown = scan.hit.at, scan.hit.kind, scan.hit.unknown_closes
    elif len(usable) == horizon:
        k, kind, unknown = len(usable) - 1, HORIZON, scan.unknown_closes
    elif good == len(closes) and delisted:
        k, kind, unknown = len(usable) - 1, DELISTED, scan.unknown_closes
    else:
        return None  # a gap, a bad close or a window not yet elapsed: unmeasured, not a trade
    move = usable[k].close / entry_close - 1.0
    dip = max(0.0, 1.0 - min(c.close for c in usable[: k + 1]) / entry_close)
    return ShareWalk(
        k + 1,
        usable[k].day,
        kind,
        -move if side == "short" else move,
        move,
        None if side == "short" else dip,
        unknown,
    )
