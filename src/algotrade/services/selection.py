"""Use case: evaluate a ``Selection`` against point-in-time L1 + rollup data."""

from dataclasses import replace
from datetime import date, datetime

from algotrade.config.schema import Selection
from algotrade.core.feature_view import FeatureValue, FeatureView
from algotrade.data import StoreReader
from algotrade.data.reference import instrument_view
from algotrade.engines.selection.evaluate import SelectionResult, evaluate_selection
from algotrade.services.views import to_value


def selection_view(
    reader: StoreReader, selection: Selection, session: date, as_of: datetime | None = None
) -> tuple[FeatureView, tuple[str, ...]]:
    """One row per instrument known on ``session``, keyed by field name, plus the rollup
    tables that had no data for the session (their fields stay UNKNOWN)."""
    fields = {r.field for r in selection.where.rules()}
    if selection.order_by:
        fields.add(selection.order_by)
    view = instrument_view(reader, session, sorted(fields), as_of=as_of)
    columns = [c for c in view.frame.columns if c != "instrument_id"]
    rows: dict[str, dict[str, FeatureValue]] = {}
    for record in view.frame.to_dict("records"):
        values = {c: to_value(record[c]) for c in columns}
        rows[str(record["instrument_id"])] = {c: v for c, v in values.items() if v is not None}
    return FeatureView(session, rows), view.missing


def select(
    reader: StoreReader, selection: Selection, session: date, as_of: datetime | None = None
) -> SelectionResult:
    view, missing = selection_view(reader, selection, session, as_of)
    return replace(evaluate_selection(selection, view), missing_tables=missing)
