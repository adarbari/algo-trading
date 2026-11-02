"""The entry sessions of an entry condition (ADR 0088, design 2.4a, E13): for a decision session D
and its names, each close t of the wait (D, then the sessions after it) is read from t's own
partition only (instrument fields per name, market fields from that session's market row), the
rule decided per name by ``engines.selection.entry.first_entry``, and S = t + the offset (>= 1),
so the fields of t are never traded at t's close. A name still waiting reads the next close; a
decided one reads nothing more. A named market field with no value at a close some name reached
is a gap of the session, not of the names: the leg is lost to the market table (``gap``), never
every name ENTRY_UNKNOWN. Both harnesses read through it."""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

from algotrade.config.edges.document import Edge
from algotrade.config.edges.portfolio import PORTFOLIO_KIND
from algotrade.config.edges.positions.cases import EntrySpec
from algotrade.config.edges.positions.chain import CHAIN_KIND
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.fields import (
    FEATURE_FIELD_PREFIX,
    GROUP_FIELD_HEADS,
    field_source,
    group_of_table,
    is_feature_field,
)
from algotrade.core.model.predicates import FieldValue
from algotrade.core.views.market_features import MARKET_FEATURES
from algotrade.data import StoreReader
from algotrade.data.rollups import feature_rows
from algotrade.engines.selection.entry import ENTRY_UNKNOWN, NOT_TRIGGERED, first_entry
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.services.evaluation.cross_section.sessions import entry_session, wait_closes
from algotrade.services.licences import HARNESS_ALL
from algotrade.services.screening.regime import session_market
from algotrade.services.selection import fields_view

MARKET_HEAD = f"{GROUP_FIELD_HEADS['market']}."


@dataclass(frozen=True)
class Entered:
    """``at``: each entered name's S; ``reasons``: each other name's (``NOT_TRIGGERED`` /
    ``ENTRY_UNKNOWN``); ``gap``: the table a reached close had no market value in (the leg is
    lost; ``at`` and ``reasons`` are then empty); ``closes``: the closes read."""

    at: dict[str, date] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)
    gap: str | None = None
    closes: tuple[date, ...] = ()


def split_fields(spec: EntrySpec) -> tuple[list[str], list[str]]:
    """``(instrument fields, market fields)`` the rule names, each sorted."""
    names = sorted({r.field for r in spec.when.rules()})
    return [n for n in names if not n.startswith(MARKET_HEAD)], [
        n for n in names if n.startswith(MARKET_HEAD)
    ]


def read_entries(
    reader: StoreReader,
    spec: EntrySpec,
    offset: int,
    ids: Collection[str],
    decision: date,
    domains: Mapping[str, Sequence[str]] | None = None,
) -> Entered:
    """The entry session of each of ``ids`` decided at D (``decision``) over the wait."""
    own, market = split_fields(spec)
    waiting = sorted(ids)
    out = Entered()
    closes: list[date] = []
    for t in wait_closes(decision, spec.within_sessions):
        if not waiting:
            break
        closes.append(t)
        shared = session_market(reader, market, t)
        if any(shared.get(n) is None for n in market):
            return Entered(gap=MARKET_FEATURES, closes=tuple(closes))
        rows: dict[str, dict[str, FieldValue]] = {i: {} for i in waiting}
        if own:
            view, _ = fields_view(reader, own, t, waiting, historical=True, held=HARNESS_ALL)
            rows = {i: {n: view.get(i, n) for n in own} for i in waiting}
        still: list[str] = []
        for i in waiting:  # a waiting name was FALSE at every earlier close: this one decides
            found = first_entry(spec.when, [{**rows[i], **shared}], domains)
            if found.entered:
                out.at[i] = entry_session(t, offset)
            elif found.reason == ENTRY_UNKNOWN:
                out.reasons[i] = ENTRY_UNKNOWN
            else:
                still.append(i)
        waiting = still
    for i in waiting:  # FALSE at every close of the wait
        out.reasons[i] = NOT_TRIGGERED
    return Entered(out.at, out.reasons, None, tuple(closes))


def entered_rows(
    by_entry: Mapping[date, pd.DataFrame], found: Entered, last: date
) -> tuple[pd.DataFrame | None, date | None]:
    """The outcome rows of the entered names, each from the partition at its own S (``by_entry``:
    one horizon's rows by entry session; ``last``: the leg's S, always among them), so the base
    and the picks are scored over the same entries (risk 22). ``(None, S)`` when an S some name
    entered at has no partition: the leg is lost, never its names dropped."""
    parts = []
    for day in sorted(set(found.at.values())):
        frame = by_entry.get(day)
        if frame is None:
            return None, day
        names = {i for i, s in found.at.items() if s == day}
        parts.append(frame[frame["instrument_id"].isin(names)])
    if not parts:
        return by_entry[last].iloc[0:0], None
    return pd.concat(parts, ignore_index=True), None


def check_entries(
    reader: StoreReader,
    edges: Sequence[Edge],
    features: FeatureSet,
    first: date,
    last: date,
    as_of: datetime,
) -> bool:
    """``check_entry`` of each of ``edges`` (a run's scopes); whether any has an entry condition
    (its legs are then never reused: each depends on every partition of its wait, ADR 0063)."""
    for edge in edges:
        check_entry(reader, edge, features, first, last, as_of)
    return any(edge.outcome.entry is not None for edge in edges)


def check_entry(
    reader: StoreReader,
    edge: Edge,
    features: FeatureSet,
    first: date,
    last: date,
    as_of: datetime,
) -> None:
    """Refuse at run start what an entry condition cannot be measured as: on an ``option_pnl``
    outcome until the writers store every S of the wait (G9-M3); on a book or an ensemble (one
    value per session, no names to enter); a rule naming a field whose feature group has no rows
    over the closes the run reads, D in ``first..last`` and their waits (G9-M4: every name would
    be ENTRY_UNKNOWN, a silent change of the rule)."""
    spec = edge.outcome.entry
    if spec is None:
        return
    where = f"edge {edge.id} outcome.entry"
    if edge.outcome.kind == CHAIN_KIND:
        raise ConfigurationError(
            f"{where}: not on an option_pnl outcome until the option writers store every entry "
            f"session of the wait (G9-M3)"
        )
    if edge.outcome.kind == PORTFOLIO_KIND or edge.ensemble:
        raise ConfigurationError(f"{where}: a book or an ensemble has no names to enter")
    end = wait_closes(last, spec.within_sessions)[-1]
    for name in sorted({r.field for r in spec.when.rules()}):
        for table in _tables(features, name):
            if feature_rows(reader, table, (), first, end, as_of) is None:
                raise ConfigurationError(
                    f"{where}: {name} has no rows in {table} over {first}..{end}, so the rule "
                    f"would be UNKNOWN at every close (G9-M4)"
                )


def _tables(features: FeatureSet, name: str) -> list[str]:
    """The session-grain feature tables ``name`` is read from (a snapshot field: none)."""
    if is_feature_field(name):
        return sorted(features.stored_columns([name.removeprefix(FEATURE_FIELD_PREFIX)]))
    table, _ = field_source(name)
    return [table] if group_of_table(table) is not None else []
