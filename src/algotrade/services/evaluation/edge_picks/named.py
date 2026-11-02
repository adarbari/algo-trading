"""What a named-symbol setup took at one session (ADR 0088 decision 9, 2.12): a time-series edge
(``base = "out_of_window"``, ADR 0073) names its few symbols instead of a screener, so its one row
per session is stored under the sentinel screener ``NAMED``. It decides when its calendar window
or market trigger opens a window at D (``time_series``: the calendar's alone, or the trigger read
at D and before), then through the setup gate as a screener edge does; its picks are the named
symbols the reference snapshot knows at D, in the document's order. Reads nothing after D."""

from dataclasses import replace
from datetime import date

from algotrade.config.edges.document import Edge
from algotrade.config.edges.named import OUT_OF_WINDOW, named_symbols
from algotrade.core.model.errors import ConfigurationError, MissingDataError
from algotrade.core.time.windows import window_name
from algotrade.data import StoreReader
from algotrade.services.evaluation.edge_picks.night import (
    LONG,
    NOT_DECISION_DAY,
    PICKED,
    SKIPPED,
    EdgePicks,
    Night,
    gate_shut,
)
from algotrade.services.evaluation.time_series.harness import resolve_symbols
from algotrade.services.evaluation.time_series.periods import window_decides
from algotrade.services.evaluation.time_series.triggers import trigger_decides
from algotrade.storage.tables.edge_schemas import NAMED


def is_named(edge: Edge) -> bool:
    """Whether ``edge`` is a named-symbol (time-series) setup, whose rows are under ``NAMED``."""
    return edge.base == OUT_OF_WINDOW


def decides(reader: StoreReader, edge: Edge, day: date) -> bool:
    """Whether ``edge`` opens a window decided at ``day``: a market trigger by its readings up to
    D, a calendar window by the calendar."""
    trigger = edge.market_trigger
    if trigger is not None:
        return trigger_decides(reader, trigger, day, edge.outcome.horizon_sessions[0], None)
    name = window_name(edge.schedule)
    if name is None:
        raise ConfigurationError(f"edge {edge.id}: not a time-series edge")
    return window_decides(name, day)


def named_night(night: Night, edge: Edge) -> EdgePicks:
    """``edge``'s row at the session (``NAMED``): ``picked`` with the known named symbols, or why
    not (not a decision day, the gate, a symbol no snapshot knows)."""
    made = EdgePicks(edge.id, NAMED, SKIPPED, top_k=edge.top_k)
    try:
        if not decides(night.reader, edge, night.session):
            return replace(made, status=NOT_DECISION_DAY)
        symbols = named_symbols(edge.universe)
        ids, unknown = resolve_symbols(night.reader, symbols, night.session, None)
    except MissingDataError as missing:
        return replace(made, reason=f"no {missing.dataset} for {night.session.isoformat()}")
    except ConfigurationError as error:
        return replace(made, reason=str(error))
    if edge.gate is not None and (shut := gate_shut(night, edge.gate)) is not None:
        return replace(made, status=shut[0], reason=shut[1])
    picks = tuple(ids[s] for s in symbols if s in ids)
    unknown_symbols = ", ".join(s for s in symbols if s in unknown)
    reason = f"no snapshot knows {unknown_symbols}" if unknown_symbols else ""
    if not picks:
        return replace(made, reason=reason)
    return replace(
        made, status=PICKED, pick_ids=picks, reason=reason, pick_sides=(LONG,) * len(picks)
    )
