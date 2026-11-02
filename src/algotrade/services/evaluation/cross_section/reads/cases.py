"""The case values of a setup at a decision session (ADR 0088, design 2.4, E13b): each name's
case rules are read at D only (instrument fields per name, market fields from D's market row) and
resolved by ``engines.selection.cases.resolve_case``; a case UNKNOWN first makes the name
unselectable (``CASE_UNKNOWN``, counted, never the default). The option trade grain holds a row
per concrete point (``config/edges/positions/key.py``: ``case_points`` stores every combination),
so a resolved name takes the row of its own point's key; the frame is relabelled to the default
point's key so the one ``hit.own_rows`` filter reads it, while the row's values stay its own
point's. A named market field with no value at D is a gap of the session: the leg is lost."""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

from algotrade.config.edges.document import Edge, Outcome
from algotrade.config.edges.positions.cases import CaseValue, Scalar
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
from algotrade.engines.selection.cases import CASE_UNKNOWN, resolve_case
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.services.features import has_rows
from algotrade.services.licences import HARNESS_ALL
from algotrade.services.screening.regime import session_market
from algotrade.services.selection import fields_view

MARKET_HEAD = f"{GROUP_FIELD_HEADS['market']}."  # a market field: read from the market row


@dataclass(frozen=True)
class CaseKeys:
    """An outcome's case values and, for each combination of their values (in ``cases`` order),
    the position key of that point by horizon; ``default``: the defaults' point's."""

    cases: tuple[CaseValue, ...]
    keys: dict[tuple[Scalar, ...], dict[int, str]] = field(default_factory=dict)
    default: dict[int, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Resolved:
    """``chosen``: each selectable name's combination; ``reasons``: each other name's
    (``CASE_UNKNOWN``); ``gap``: the market table D had no value in (the leg is lost)."""

    chosen: dict[str, tuple[Scalar, ...]] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)
    gap: str | None = None


def case_keys(outcome: Outcome) -> CaseKeys | None:
    """The keys of every point ``outcome``'s cases can resolve to, from the points the loader
    filled (``PositionSpec.points``); None without cases. An outcome with cases but no points was
    not loaded against the templates: refused, never measured at the default."""
    spec = outcome.position
    if spec is None or not spec.cases:
        return None
    if not spec.points:
        raise ConfigurationError("case values need the points the loader fills (with_legs)")
    keys: dict[tuple[Scalar, ...], dict[int, str]] = {}
    for values, hold, key in spec.points:
        keys.setdefault(tuple(values), {})[hold] = key
    return CaseKeys(spec.cases, keys, keys[tuple(c.default for c in spec.cases)])


def case_fields(cases: Sequence[CaseValue]) -> list[str]:
    """Every field the cases' rules name, sorted."""
    return sorted({r.field for c in cases for case in c.cases for r in case.when.rules()})


def read_cases(
    reader: StoreReader,
    cases: Sequence[CaseValue],
    ids: Collection[str],
    decision: date,
    domains: Mapping[str, Sequence[str]] | None = None,
) -> Resolved:
    """Each of ``ids``' case values at D (``decision``), from D's partition only."""
    names = case_fields(cases)
    own = [n for n in names if not n.startswith(MARKET_HEAD)]
    market = [n for n in names if n.startswith(MARKET_HEAD)]
    shared = session_market(reader, market, decision)
    if any(shared.get(n) is None for n in market):
        return Resolved(gap=MARKET_FEATURES)
    wanted = sorted(ids)
    rows: dict[str, dict[str, FieldValue]] = {i: {} for i in wanted}
    if own:
        view, _ = fields_view(reader, own, decision, wanted, historical=True, held=HARNESS_ALL)
        rows = {i: {n: view.get(i, n) for n in own} for i in wanted}
    out = Resolved()
    for i in wanted:
        found = [resolve_case(c, {**rows[i], **shared}, domains) for c in cases]
        if all(r.selectable for r in found):
            out.chosen[i] = tuple(r.value for r in found if r.value is not None)
        else:
            out.reasons[i] = CASE_UNKNOWN
    return out


def cased_rows(rows: pd.DataFrame, resolved: Resolved, keys: CaseKeys) -> pd.DataFrame:
    """``rows`` (option rows at S, every position key) with each case point's rows kept only for
    the names that resolved to it, relabelled to the default point's key (by the row's horizon);
    a name that is not selectable keeps none; rows of any other key (a baseline's) as they are."""
    own = pd.Series(False, index=rows.index)
    keep = pd.Series(False, index=rows.index)
    relabel = rows["position_key"].copy()
    for horizon, default in keys.default.items():
        at = rows["horizon_sessions"] == horizon
        mine = at & rows["position_key"].isin({k[horizon] for k in keys.keys.values()})
        wanted = rows["instrument_id"].map(
            {i: keys.keys[v][horizon] for i, v in resolved.chosen.items()}
        )
        own |= mine
        keep |= mine & (rows["position_key"] == wanted)
        relabel[mine] = default
    return rows.assign(position_key=relabel)[~own | keep].reset_index(drop=True)


def check_cases(
    reader: StoreReader,
    edge: Edge,
    features: FeatureSet,
    first: date,
    last: date,
    as_of: datetime,
) -> None:
    """Refuse at run start case values on anything but an ``option_pnl`` position (a share
    template has one per side and share exits are P2) and a case rule over a field whose feature
    group has no rows over the decision sessions ``first..last`` (G9-M4)."""
    spec = edge.outcome.position
    if spec is None or not spec.cases:
        return
    where = f"edge {edge.id} outcome case values"
    if edge.outcome.kind != CHAIN_KIND:
        raise ConfigurationError(f"{where}: only an option_pnl position takes case values")
    for name in case_fields(spec.cases):
        for table in session_tables(features, name):
            if not has_rows(reader, table, first, last, as_of):
                raise ConfigurationError(
                    f"{where}: {name} has no rows in {table} over {first}..{last}, so every "
                    f"name would be CASE_UNKNOWN (G9-M4)"
                )


def session_tables(features: FeatureSet, name: str) -> list[str]:
    """The session-grain feature tables ``name`` is read from (a snapshot field: none)."""
    if is_feature_field(name):
        return sorted(features.stored_columns([name.removeprefix(FEATURE_FIELD_PREFIX)]))
    table, _ = field_source(name)
    return [table] if group_of_table(table) is not None else []
