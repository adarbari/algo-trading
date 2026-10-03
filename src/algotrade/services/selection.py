"""Use case: evaluate a ``Selection`` against point-in-time L1 + rollup data."""

from datetime import date, datetime

from algotrade.config.catalog import REFERENCE_TABLE, field_source
from algotrade.config.schema import Selection
from algotrade.core.feature_view import FeatureValue, FeatureView
from algotrade.engines.selection.evaluate import SelectionResult, evaluate_selection
from algotrade.services.views import to_value
from algotrade.storage.readers import StoreReader

ROLLUP_HINT = "algotrade-ingest features --date {d}"


def selection_view(
    reader: StoreReader, selection: Selection, session: date, as_of: datetime | None = None
) -> FeatureView:
    """One row per instrument known on ``session`` (the L1 snapshot), keyed by field name.

    Only the tables the selection references are read. Values missing for an instrument
    stay absent, which the evaluator treats as UNKNOWN.
    """
    fields = {r.field for r in selection.where.rules()}
    if selection.order_by:
        fields.add(selection.order_by)
    reference = reader.instruments(session, as_of=as_of)
    rows: dict[str, dict[str, FeatureValue]] = {str(i): {} for i in reference["instrument_id"]}
    by_table: dict[str, list[tuple[str, str]]] = {}
    for name in sorted(fields):
        table, column = field_source(name)
        by_table.setdefault(table, []).append((name, column))
    for table, wanted in by_table.items():
        if table == REFERENCE_TABLE:
            frame = reference
        else:
            frame = reader.require(table, session, ROLLUP_HINT.format(d=session), as_of)
        present = [(n, c) for n, c in wanted if c in frame.columns]
        for record in frame.to_dict("records"):
            row = rows.get(str(record["instrument_id"]))
            if row is not None:
                row.update({n: to_value(record[c]) for n, c in present})
    return FeatureView(session, rows)


def select(
    reader: StoreReader, selection: Selection, session: date, as_of: datetime | None = None
) -> SelectionResult:
    return evaluate_selection(selection, selection_view(reader, selection, session, as_of))
