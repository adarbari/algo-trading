"""Use case: evaluate a ``Selection`` against point-in-time L1 + rollup data, and expression
features (``feature.<name>``) computed on read (``services.features``)."""

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


def selection_view(
    reader: StoreReader,
    selection: Selection,
    session: date,
    as_of: datetime | None = None,
    features: FeatureSet | None = None,
) -> tuple[FeatureView, InstrumentView]:
    """One row per instrument known on ``session``, keyed by field name, plus the
    ``InstrumentView`` it came from (``missing`` tables stay UNKNOWN; ``pre_snapshot``).
    ``feature.<name>`` fields are computed from the stored features they need."""
    fields = {r.field for r in selection.where.rules()}
    if selection.order_by:
        fields.add(selection.order_by)
    view = field_view(reader, session, sorted(fields), as_of=as_of, features=features)
    columns = [c for c in view.frame.columns if c != "instrument_id"]
    rows: dict[str, dict[str, FeatureValue]] = {}
    for record in view.frame.to_dict("records"):
        values = {c: to_value(record[c]) for c in columns}
        rows[str(record["instrument_id"])] = {c: v for c, v in values.items() if v is not None}
    return FeatureView(session, rows), view


def select(
    reader: StoreReader, selection: Selection, session: date, as_of: datetime | None = None
) -> SelectionResult:
    """Point in time: the reference snapshot and rollups for ``session``, read ``as_of``."""
    view, source = selection_view(reader, selection, session, as_of)
    return replace(
        evaluate_selection(selection, view),
        missing_tables=source.missing,
        pre_snapshot=source.pre_snapshot,
    )
