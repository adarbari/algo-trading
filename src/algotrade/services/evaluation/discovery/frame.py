"""The discovery frame of one grid session: the winners, their controls and the losers with every
usable catalogue feature read at S (ED6 winners study, definition 3).

Point in time: a feature is read from the rollup partition of S itself (``entity_field_view``:
exactly that session, never a later or earlier one), for the winners, controls and losers only;
an UNKNOWN value is NaN, dropped by the statistics and counted, never imputed. A feature is
left out of a session, with the reason recorded, when
- it is an ``edge_score_*`` (a learned scorer fitted on windows that overlap the label), or reads
  one;
- it is, or is derived from, a matching variable (``adv_usd_20d`` and the volatility field: the
  controls are matched on them, reason "matched on");
- one of the tables it reads has no partition on or before S (``first_partition``: the first
  session the table was stored; the universe, company, shares, chains and IV tables start long
  after the history and would put today's knowledge on an old S).
Only numeric instrument features are tested.
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from algotrade.config.edges.winners import WinnersStudySettings
from algotrade.core.model.fields import NUMERIC_TYPES, group_of_table
from algotrade.data import StoreReader
from algotrade.data.feature_inputs import first_stored_session
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.framework.feature import Feature
from algotrade.services.evaluation.discovery.controls import assign_cells, draw_controls
from algotrade.services.evaluation.discovery.grid import GridSession, read_eligible
from algotrade.services.evaluation.discovery.labels import Labels, read_labels
from algotrade.services.features import entity_field_view

EDGE_SCORE_PREFIX = "edge_score_"
LIQUIDITY = "price_stats.adv_usd_20d"  # ``<group>.<column>`` of the liquidity matching variable
EDGE_SCORE = "learned edge score"
MATCHING_VARIABLE = "matched on"


def matching_columns(settings: WinnersStudySettings) -> frozenset[str]:
    """The ``<group>.<column>`` of every variable the controls are matched on: the dollar volume
    and the volatility field (``rollup.<group>@v<N>.<column>``)."""
    _, group_key, column = settings.volatility_field.split(".", 2)
    return frozenset({LIQUIDITY, f"{group_key.partition('@')[0]}.{column}"})


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
    """One grid session ready for the statistics. ``frame``: ``instrument_id``, ``winner`` and
    ``loser`` (bool; a control is neither), ``cell`` and one column per read field (NaN: UNKNOWN);
    ``excluded``: (field, reason); ``unknown_volatility``: names at the floors with no volatility,
    not eligible."""

    grid: GridSession
    labels: Labels
    controls_wanted: int
    seed: tuple[int, int]
    frame: pd.DataFrame
    excluded: tuple[tuple[str, str], ...]
    unknown_volatility: int = 0


def feature_reads(features: FeatureSet, feature: Feature) -> Reads:
    """The tables, group columns and expression names ``feature`` is computed from, through the
    expression features it uses."""
    by_name = {g.name: g for g in features.code.values()}
    tables: set[str] = set()
    columns: set[str] = set()
    names: set[str] = set()

    by_key = {g.key: g for g in features.code.values()}

    def read_group(key: str) -> None:
        """The tables of a group's inputs; an input that is itself a group's table adds that
        group's inputs, transitively (a group built on reference or company data is late)."""
        for i in by_key[key].inputs:
            if i.table in tables:
                continue
            tables.add(i.table)
            found = group_of_table(i.table)
            if found is not None and found[1] in by_key:
                read_group(found[1])

    def visit(f: Feature) -> None:
        if f.group:
            columns.add(f"{features.code[f.group].name}.{f.name}")
            read_group(f.group)
            return
        expression = features.expressions[f.name]
        for ref in expression.refs:
            group_name = ref.partition(".")[0]
            read_group(by_name[group_name].key)
            columns.add(ref)
        for used in expression.uses:
            if used not in names:
                names.add(used)
                visit(features.expressions[used].feature)

    visit(feature)
    return Reads(frozenset(tables), frozenset(columns), frozenset(names))


def usable_fields(
    features: FeatureSet,
    session: date,
    first_partition: Mapping[str, date | None],
    matching: frozenset[str] = frozenset({LIQUIDITY}),
) -> Candidates:
    """The numeric instrument features to read at ``session`` and those left out with the reason.
    ``first_partition``: table -> first session stored (None: never stored)."""
    fields: list[str] = []
    excluded: list[tuple[str, str]] = []
    for f in sorted(features.features.values(), key=lambda x: x.field):
        if f.entity != "instrument" or f.dtype not in NUMERIC_TYPES:
            continue
        reads = feature_reads(features, f)
        why = _why_not(f, reads, session, first_partition, matching)
        if why:
            excluded.append((f.field, why))
        else:
            fields.append(f.field)
    return Candidates(tuple(fields), tuple(excluded))


def _why_not(
    f: Feature,
    reads: Reads,
    session: date,
    first_partition: Mapping[str, date | None],
    matching: frozenset[str],
) -> str:
    if f.name.startswith(EDGE_SCORE_PREFIX) or any(
        n.startswith(EDGE_SCORE_PREFIX) for n in reads.names
    ):
        return EDGE_SCORE
    if reads.columns & matching:
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
    losers: Collection[str] = (),
) -> pd.DataFrame:
    """The frame of ``winners``, ``controls`` and ``losers`` from ``values`` (``instrument_id`` and
    any of ``fields``; a field absent from it is wholly UNKNOWN), sorted by id."""
    lost = set(losers)
    ids = sorted(winners | controls | lost)
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
            "loser": [i in lost for i in ids],
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
    labels = read_labels(reader, day, list(eligible.names["instrument_id"]), settings)
    cells = assign_cells(eligible.names, settings)
    pool = labels.measured_ids - labels.losers
    drawn = draw_controls(cells, labels.winners, day, settings, pool)
    candidates = usable_fields(features, day, first_partition, matching_columns(settings))
    ids = sorted(labels.winners | labels.losers | set(drawn.ids))
    view = read_values(reader, day, candidates.fields, ids, features)
    frame = assemble(
        view, candidates.fields, set(labels.winners), set(drawn.ids), cells, set(labels.losers)
    )
    return SessionFrame(
        grid, labels, drawn.wanted, drawn.seed, frame, candidates.excluded,
        eligible.unknown_volatility,
    )  # fmt: skip
