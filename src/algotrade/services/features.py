"""Use case: read expression features (virtual by default) for one session or a range.

``read_expressions(reader, names, start, end)`` loads only the stored columns the formulas
need (``FeatureSet.stored_columns``: through ``data.rollups.feature_rows``, column-pruned) and
evaluates the expressions in dependency order (``FeatureSet.evaluate``); a materialised one
is read from its table. The same path serves a session (selections, ``FeatureView``,
``field_view``: an ``InstrumentView`` of any catalogue fields; ``entity_field_view`` the
same for a market's row, ADR 0047) and a series over a date range. ``site_features()`` is
the site's ``FeatureSet``, from the config store given (default: ``$ALGOTRADE_CONFIG_DIR``
or ./config); ``catalogue(store, user)`` is a user's
(site + ``config/users/<user>/features``, ADR 0023 step 4) and ``config_features(resolved)``
the one a resolved config's selection is evaluated with (site + the user features it names).
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from functools import cache
from pathlib import Path

import pandas as pd

from algotrade.config.env import config_dir
from algotrade.config.strategy.resolve import ResolvedConfig
from algotrade.core.model.fields import FEATURE_FIELD_PREFIX, is_feature_field
from algotrade.data import StoreReader
from algotrade.data.reference import InstrumentView, instrument_view
from algotrade.data.rollups import feature_rows, group_view
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.site import site_features as build_site_features
from algotrade.features.site import user_features, with_user_features
from algotrade.storage.configs.files import FileConfigStore
from algotrade.storage.configs.store import ConfigStore


@cache
def _default_store(root: Path) -> FileConfigStore:
    return FileConfigStore(root)


def site_features(store: ConfigStore | None = None) -> FeatureSet:
    """The site's features: code groups + ``config/site/features/*.toml`` of ``store``."""
    return build_site_features(store if store is not None else _default_store(config_dir()))


def site_store(store: ConfigStore | None) -> ConfigStore | None:
    """``store`` when it declares site expression features, else ``None`` (the site default:
    a store that holds only strategy configs, e.g. in tests, still sees the site's)."""
    return store if store is not None and store.names("site", "features") else None


def catalogue(store: ConfigStore | None = None, user: str | None = None) -> FeatureSet:
    """The features ``user`` sees: the site's plus their own (from ``store``). Another user's
    features are never in it."""
    site = site_features(site_store(store))
    if store is None or user is None:
        return site
    return user_features(store, user, site)


def config_features(config: ResolvedConfig) -> FeatureSet:
    """The site's features plus the user features ``config`` references (as resolved)."""
    return with_user_features(site_features(), config.features)


@dataclass(frozen=True)
class FeatureCheck:
    """One user feature, checked: its type, what it reads, and a sample evaluation on the
    latest session its inputs have (``session`` ``None``: nothing stored yet)."""

    name: str
    where: str
    dtype: str
    kind: str
    inputs: tuple[str, ...]
    session: date | None = None
    rows: int = 0
    non_null: int = 0
    sample: tuple[tuple[str, object], ...] = ()


def check_user_features(
    reader: StoreReader | None, store: ConfigStore, user: str, sample: int = 5
) -> list[FeatureCheck]:
    """Load, check and (with a ``reader``) evaluate each of ``user``'s features; a bad
    definition fails the load with its file, feature and position."""
    fs = catalogue(store, user)
    out = []
    for name, e in fs.expressions.items():
        if e.scope != "user":
            continue
        f = e.feature
        check = FeatureCheck(name, e.definition.where, f.dtype, f.kind, f.inputs)
        tables = fs.stored_columns([name]) if reader is not None else {}
        dates = [d for t in tables for d in reader.dates(t)] if reader is not None else []
        if reader is not None and dates:
            frame = read_expressions(reader, [name], max(dates), features=fs).frame
            present = frame.dropna(subset=[name])
            shown = tuple(zip(present["instrument_id"], present[name], strict=True))[:sample]
            check = replace(
                check, session=max(dates), rows=len(frame), non_null=len(present), sample=shown
            )
        out.append(check)
    return out


@dataclass(frozen=True)
class ExpressionRows:
    """``frame``: ``session_date``, ``instrument_id`` + one column per expression, one row
    per (session, instrument) with a row in any table read. ``missing``: tables read with no
    rows at all in the range (their features are null: UNKNOWN)."""

    frame: pd.DataFrame
    missing: tuple[str, ...]


def field_view(
    reader: StoreReader,
    session: date,
    fields: Sequence[str],
    ids: Sequence[str] | None = None,
    as_of: datetime | None = None,
    features: FeatureSet | None = None,
) -> InstrumentView:
    """``data.reference.instrument_view`` for any catalogue fields: stored ones as read,
    ``feature.<name>`` ones computed for the session, for ``ids`` only when given (tables they
    need that have no partition for the session are added to ``missing``)."""
    stored = [f for f in fields if not is_feature_field(f)]
    view = instrument_view(reader, session, stored, ids, as_of)
    frame, missing = _with_expressions(
        reader, session, fields, view.frame, view.missing, ids, as_of, features
    )
    return replace(view, frame=frame, missing=missing)


def entity_field_view(
    reader: StoreReader,
    session: date,
    fields: Sequence[str],
    ids: Sequence[str],
    as_of: datetime | None = None,
    features: FeatureSet | None = None,
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """``field_view`` for entities that are not instruments (a market's ``MKT:US`` row, ADR
    0045): one row per id of ``ids``, group fields (``market.<group>@v<N>.<column>``) from
    exactly ``session``'s partition, ``feature.<name>`` ones computed -> (the frame, the tables
    with no partition for the session)."""
    stored = [f for f in fields if not is_feature_field(f)]
    frame, missing = group_view(reader, session, stored, ids, as_of)
    return _with_expressions(reader, session, fields, frame, missing, ids, as_of, features)


def _with_expressions(
    reader: StoreReader,
    session: date,
    fields: Sequence[str],
    frame: pd.DataFrame,
    missing: tuple[str, ...],
    ids: Sequence[str] | None,
    as_of: datetime | None,
    features: FeatureSet | None,
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """``frame`` plus the ``feature.<name>`` fields of ``fields``, computed for ``session``."""
    expressions = [f.removeprefix(FEATURE_FIELD_PREFIX) for f in fields if is_feature_field(f)]
    if not expressions:
        return frame, missing
    computed = read_expressions(
        reader, expressions, session, as_of=as_of, instruments=ids, features=features
    )
    extra = computed.frame.drop(columns="session_date").rename(
        columns={n: f"{FEATURE_FIELD_PREFIX}{n}" for n in expressions}
    )
    joined = frame.merge(extra, on="instrument_id", how="left")
    return joined, tuple(sorted({*missing, *computed.missing}))


def _stored(
    reader: StoreReader, table: str, start: date, end: date, as_of: datetime | None
) -> bool:
    """Does ``table`` have rows in ``start..end`` known at ``as_of`` (None: now)?"""
    if as_of is None:
        return any(start <= d <= end for d in reader.dates(table))
    return feature_rows(reader, table, ["instrument_id"], start, end, as_of) is not None


def read_expressions(
    reader: StoreReader,
    names: Sequence[str],
    start: date,
    end: date | None = None,
    as_of: datetime | None = None,
    instruments: Sequence[str] | None = None,
    features: FeatureSet | None = None,
) -> ExpressionRows:
    """Expression features ``names`` for ``start..end`` (``end``: ``start``), point in time,
    for ``instruments`` only when given. Rows are read only for them unless a formula uses
    ``exists(group)``, which needs every row of the session to tell "no row for this
    instrument" from "no rows at all". ``missing``: the tables read with no partition in the
    range (never one that merely has no rows for ``instruments``)."""
    fs = features or site_features()
    _, todo = fs.plan(names)
    whole = instruments is None or any(fs.expressions[n].exists for n in todo)
    only = None if whole else instruments
    last = end or start
    frames: dict[str, pd.DataFrame | None] = {}
    for table, columns in fs.stored_columns(names).items():
        frames[table] = feature_rows(reader, table, columns, start, last, as_of, only)
    # Narrowed to some instruments, no rows may only mean none of theirs: then the table is
    # missing only when it has no partition in the range at all.
    empty = [t for t, f in frames.items() if f is None]
    if only is not None:
        empty = [t for t in empty if not _stored(reader, t, start, last, as_of)]
    missing = tuple(sorted(empty))
    out = fs.evaluate(frames, names)
    if instruments is not None:
        out = out[out["instrument_id"].isin(set(instruments))].reset_index(drop=True)
    return ExpressionRows(out, missing)
