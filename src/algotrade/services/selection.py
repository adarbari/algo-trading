"""Use case: evaluate a ``Selection`` against point-in-time L1 + rollup data, and expression
features (``feature.<name>``) computed on read (``services.features``)."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import date, datetime

from algotrade.config.strategy.schema import Selection
from algotrade.core.views.feature_view import FeatureValue, FeatureView
from algotrade.data import StoreReader
from algotrade.data.reference import InstrumentView
from algotrade.engines.selection.evaluate import SelectionResult, evaluate_selection
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.services.features import field_view
from algotrade.services.views import to_value


def fields_view(
    reader: StoreReader,
    fields: Sequence[str],
    session: date,
    ids: Sequence[str] | None = None,
    as_of: datetime | None = None,
    features: FeatureSet | None = None,
) -> tuple[FeatureView, InstrumentView]:
    """One row per instrument known on ``session`` (only ``ids``, each with a row even when
    nothing is known of it, when given), keyed by field name; missing values are left out
    (UNKNOWN). ``feature.<name>`` fields are computed from the stored features they need.
    Also the ``InstrumentView`` it came from (``missing`` tables; ``pre_snapshot``)."""
    view = field_view(reader, session, sorted(set(fields)), ids, as_of=as_of, features=features)
    columns = [c for c in view.frame.columns if c != "instrument_id"]
    rows: dict[str, dict[str, FeatureValue]] = {i: {} for i in ids or ()}
    for record in view.frame.to_dict("records"):
        values = {c: to_value(record[c]) for c in columns}
        rows[str(record["instrument_id"])] = {c: v for c, v in values.items() if v is not None}
    if ids is not None:
        wanted = set(ids)
        rows = {i: r for i, r in rows.items() if i in wanted}
    return FeatureView(session, rows), view


def selection_view(
    reader: StoreReader,
    selection: Selection,
    session: date,
    as_of: datetime | None = None,
    features: FeatureSet | None = None,
) -> tuple[FeatureView, InstrumentView]:
    """``fields_view`` of the fields ``selection`` reads, for every instrument known on
    ``session``."""
    return fields_view(reader, selection_fields(selection), session, as_of=as_of, features=features)


def selection_fields(selection: Selection) -> list[str]:
    """The fields ``selection`` reads (its rules' and its order), sorted."""
    fields = {r.field for r in selection.where.rules()}
    if selection.order_by:
        fields.add(selection.order_by)
    return sorted(fields)


def select(
    reader: StoreReader,
    selection: Selection,
    session: date,
    as_of: datetime | None = None,
    features: FeatureSet | None = None,
) -> SelectionResult:
    """Point in time: the reference snapshot and rollups for ``session``, read ``as_of``.
    ``features``: the catalogue ``feature.<name>`` fields come from (default: the site's; a
    user's config: ``services.features.config_features``)."""
    view, source = selection_view(reader, selection, session, as_of, features)
    return replace(
        evaluate_selection(selection, view),
        missing_tables=source.missing,
        pre_snapshot=source.pre_snapshot,
    )
