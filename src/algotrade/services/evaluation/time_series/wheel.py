"""A named option sleeve with a wheel (ADR 0088, X7, backend-concepts-2 §2.11): the wheel's
phases and transitions over the generic cycle book (``cycle.py``). The put phase is the edge's
own outcome, the call phase ``positions/key.wheel_call``; a cycle starts as a put, an assigned
put hands its shares to the call, and a called-away call starts over."""

from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime

from algotrade.config.edges.document import Edge
from algotrade.config.edges.positions.key import wheel_call
from algotrade.config.edges.positions.templates import Templates
from algotrade.config.edges.verdict import OptionCosts
from algotrade.core.model.errors import ConfigurationError
from algotrade.data import StoreReader
from algotrade.services.evaluation.cross_section.portfolio.cycle import CALL, PUT, WHEEL
from algotrade.services.evaluation.time_series.cycle import cycle_book


def wheel_book(
    reader: StoreReader,
    edge: Edge,
    templates: Templates,
    symbols: Mapping[str, str],
    names: int,
    entries: Sequence[date],
    may_start: Callable[[date], bool | None],
    as_of: datetime,
    option_costs: OptionCosts | None = None,
) -> dict[str, float | int | str | None]:
    """``edge``'s wheel book (``cycle.cycle_book``) over the ``entries`` of ``symbols``;
    ``may_start``: whether a new put may be sold on an entry session (the setup's gate)."""
    call = wheel_call(edge.outcome, templates)
    if call is None:
        raise ConfigurationError(f"edge {edge.id}: not a wheel")
    phases = {PUT: edge.outcome, CALL: call}
    return cycle_book(reader, edge, phases, WHEEL, PUT, symbols, names, entries, may_start, as_of,
                      option_costs)  # fmt: skip
