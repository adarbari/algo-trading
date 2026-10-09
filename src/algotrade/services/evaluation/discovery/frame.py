"""The discovery frame of one grid session: the winners and their controls with every usable
catalogue feature read at S (ED6 winners study, definition 3).

Point in time: a feature is read from the rollup partition of S itself (``entity_field_view``:
exactly that session, never a later or earlier one), for the winners and controls only; an UNKNOWN
value is NaN, dropped by the statistics and counted, never imputed. A feature is left out of
a session, with the reason recorded, when
- it is an ``edge_score_*`` (a learned scorer fitted on windows that overlap the label), or reads
  one;
- it is, or is derived from, a matching variable (``adv_usd_20d``: the controls are matched on it);
- one of the tables it reads has no partition on or before S (``first_partition``: the first
  session the table was stored; the universe, company, shares, chains and IV tables start long
  after the history and would put today's knowledge on an old S).
Only numeric instrument features are tested.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from algotrade.config.edges.winners import WinnersStudySettings
from algotrade.core.model.fields import NUMERIC_TYPES
from algotrade.data import StoreReader
from algotrade.data.feature_inputs import first_stored_session
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.framework.feature import Feature
from algotrade.services.evaluation.discovery.controls import assign_cells, draw_controls
from algotrade.services.evaluation.discovery.grid import GridSession, read_eligible
from algotrade.services.evaluation.discovery.labels import Labels, read_labels
from algotrade.services.features import entity_field_view

EDGE_SCORE_PREFIX = "edge_score_"
MATCHING = frozenset({"price_stats.adv_usd_20d"})  # ``<group>.<column>`` of the matching variable
EDGE_SCORE = "learned edge score"
MATCHING_VARIABLE = "matching variable"


@dataclass(frozen=True)
class Reads:
    """What a feature is computed from: the stored ``tables`` its groups read, the group
    ``columns`` (``<group>.<column>``) and the expression features (``names``) beneath it."""

    tables: frozenset[str]
    columns: frozenset[str]
    names: frozenset[str]


@dataclass(frozen=True)
class Candidates:
    """``fields``: the selection fields to read at one session, sorted; ``excluded``: (field,
    reason) of the instrument features not read there."""

    fields: tuple[str, ...]
    excluded: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class SessionFrame:
    """One grid session ready for the statistics. ``frame``: ``instrument_id``, ``winner``
    (bool), ``cell`` and one column per read field (NaN: UNKNOWN); ``excluded``: (field, reason)."""

    grid: GridSession
    labels: Labels
    controls_wanted: int
    seed: tuple[int, int]
    frame: pd.DataFrame
    excluded: tuple[tuple[str, str], ...]


def feature_reads(features: FeatureSet, feature: Feature) -> Reads:
    """The tables, group columns and expression names ``feature`` is computed from, through the
    expression features it uses."""
    by_name = {g.name: g for g in features.code.values()}
    tables: set[str] = set()
    columns: set[str] = set()
    names: set[str] = set()

    def visit(f: Feature) -> None:
        if f.group:
            group = features.code[f.group]
            tables.update(i.table for i in group.inputs)
            columns.add(f"{group.name}.{f.name}")
            return
        expression = features.expressions[f.name]
        for ref in expression.refs:
            group_name = ref.partition(".")[0]
            tables.update(i.table for i in by_name[group_name].inputs)
            columns.add(ref)
        for used in expression.uses:
            if used not in names:
                names.add(used)
                visit(features.expressions[used].feature)

    visit(feature)
    return Reads(frozenset(tables), frozenset(columns), frozenset(names))


def usable_fields(
    features: FeatureSet, session: date, first_partition: Mapping[str, date | None]
) -> Candidates:
    """The numeric instrument features to read at ``session`` and those left out with the reason.
    ``first_partition``: table -> first session stored (None: never stored)."""
    fields: list[str] = []
    excluded: list[tuple[str, str]] = []
    for f in sorted(features.features.values(), key=lambda x: x.field):
        if f.entity != "instrument" or f.dtype not in NUMERIC_TYPES:
            continue
        reads = feature_reads(features, f)
        why = _why_not(f, reads, session, first_partition)
        if why:
            excluded.append((f.field, why))
        else:
            fields.append(f.field)
    return Candidates(tuple(fields), tuple(excluded))


def _why_not(
    f: Feature, reads: Reads, session: date, first_partition: Mapping[str, date | None]
) -> str:
    if f.name.startswith(EDGE_SCORE_PREFIX) or any(
        n.startswith(EDGE_SCORE_PREFIX) for n in reads.names
    ):
        return EDGE_SCORE
    if reads.columns & MATCHING:
        return MATCHING_VARIABLE
    for table in sorted(reads.tables):
        first = first_partition.get(table)
        if first is None:
            return f"input {table} never stored"
        if first > session:
            return f"input {table} first stored {first}, after the session"
    return ""


def first_partitions(reader: StoreReader, features: FeatureSet) -> dict[str, date | None]:
    """The first stored partition of every table an instrument feature reads (None: none)."""
    tables: set[str] = set()
    for f in features.features.values():
        if f.entity == "instrument":
            tables |= feature_reads(features, f).tables
    return {t: first_stored_session(reader, t) for t in sorted(tables)}


def assemble(
    values: pd.DataFrame,
    fields: tuple[str, ...],
    winners: set[str],
    controls: set[str],
    cells: pd.Series,
) -> pd.DataFrame:
    """The frame of ``winners`` and ``controls`` from ``values`` (``instrument_id`` and any of
    ``fields``; a field absent from it is wholly UNKNOWN), sorted by id."""
    ids = sorted(winners | controls)
    base = values.drop_duplicates("instrument_id").set_index("instrument_id").reindex(ids)
    numeric = {
        f: pd.to_numeric(base[f], errors="coerce").to_numpy(dtype=float)
        if f in base.columns
        else np.full(len(ids), np.nan)
        for f in fields
    }
    head = pd.DataFrame(
        {
            "instrument_id": ids,
            "winner": [i in winners for i in ids],
            "cell": [str(cells.get(i, "")) for i in ids],
        }
    )
    return pd.concat([head, pd.DataFrame(numeric)], axis=1)


def read_values(
    reader: StoreReader,
    session: date,
    fields: tuple[str, ...],
    ids: list[str],
    features: FeatureSet,
) -> pd.DataFrame:
    """``instrument_id`` and ``fields`` of ``ids`` from exactly the partition of ``session``
    (never an earlier or later one); a table with no partition leaves its fields out (UNKNOWN)."""
    view, _ = entity_field_view(reader, session, list(fields), ids, features=features)
    return view


def session_frame(
    reader: StoreReader,
    grid: GridSession,
    settings: WinnersStudySettings,
    features: FeatureSet,
    first_partition: Mapping[str, date | None],
) -> SessionFrame:
    """Read one grid session: the eligible names, the winners, the controls and the features at
    ``grid.session`` (``MissingDataError`` when the session's rollups or outcomes are not
    stored, or too many names lack an outcome)."""
    day = grid.session
    eligible = read_eligible(reader, day, settings, features)
    labels = read_labels(reader, day, list(eligible["instrument_id"]), settings)
    cells = assign_cells(eligible, settings)
    drawn = draw_controls(cells, labels.winners, day, settings)
    candidates = usable_fields(features, day, first_partition)
    ids = sorted(labels.winners | set(drawn.ids))
    view = read_values(reader, day, candidates.fields, ids, features)
    frame = assemble(view, candidates.fields, set(labels.winners), set(drawn.ids), cells)
    return SessionFrame(grid, labels, drawn.wanted, drawn.seed, frame, candidates.excluded)
