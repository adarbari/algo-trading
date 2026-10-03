"""Use case: read expression features (virtual by default) for one session or a range.

``read_expressions(reader, names, start, end)`` loads only the stored columns the formulas
need (``FeatureSet.stored_columns``: through ``data.rollups.feature_rows``, column-pruned) and
evaluates the expressions in dependency order (``FeatureSet.evaluate``); a materialised one
is read from its table. The same path serves a session (selections, ``FeatureView``,
``field_view``: an ``InstrumentView`` of any catalogue fields) and a series over a date
range. ``site_features()`` is the site's ``FeatureSet``, from the config store given
(default: ``$ALGOTRADE_CONFIG_DIR`` or ./config).
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from functools import cache
from pathlib import Path

import pandas as pd

from algotrade.config.env import config_dir
from algotrade.core.model.fields import FEATURE_FIELD_PREFIX, is_feature_field
from algotrade.data import StoreReader
from algotrade.data.reference import InstrumentView, instrument_view
from algotrade.data.rollups import feature_rows
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.site import site_features as build_site_features
from algotrade.storage.configs.files import FileConfigStore
from algotrade.storage.configs.store import ConfigStore


@cache
def _default_store(root: Path) -> FileConfigStore:
    return FileConfigStore(root)


def site_features(store: ConfigStore | None = None) -> FeatureSet:
    """The site's features: code groups + ``config/site/features/*.toml`` of ``store``."""
    return build_site_features(store if store is not None else _default_store(config_dir()))


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
    ``feature.<name>`` ones computed for the session (tables they need that have no rows
    are added to ``missing``)."""
    expressions = [f.removeprefix(FEATURE_FIELD_PREFIX) for f in fields if is_feature_field(f)]
    stored = [f for f in fields if not is_feature_field(f)]
    view = instrument_view(reader, session, stored, ids, as_of)
    if not expressions:
        return view
    computed = read_expressions(reader, expressions, session, as_of=as_of, features=features)
    extra = computed.frame.drop(columns="session_date").rename(
        columns={n: f"{FEATURE_FIELD_PREFIX}{n}" for n in expressions}
    )
    frame = view.frame.merge(extra, on="instrument_id", how="left")
    return replace(view, frame=frame, missing=tuple(sorted({*view.missing, *computed.missing})))


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
    instrument" from "no rows at all"."""
    fs = features or site_features()
    _, todo = fs.plan(names)
    whole = instruments is None or any(fs.expressions[n].exists for n in todo)
    only = None if whole else instruments
    frames: dict[str, pd.DataFrame | None] = {}
    for table, columns in fs.stored_columns(names).items():
        frames[table] = feature_rows(reader, table, columns, start, end or start, as_of, only)
    missing = tuple(sorted(t for t, f in frames.items() if f is None))
    out = fs.evaluate(frames, names)
    if instruments is not None:
        out = out[out["instrument_id"].isin(set(instruments))].reset_index(drop=True)
    return ExpressionRows(out, missing)
