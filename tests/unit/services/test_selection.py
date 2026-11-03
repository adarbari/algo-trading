"""``fields_view`` turns the field frame into rows column by column: the rows are exactly what
the per-record conversion gave (known values only, NaN / NaT / None left out, timestamps as
ISO text), and an id with nothing known keeps its empty row."""

import pandas as pd

from algotrade.services.licences import HARNESS_ALL
from algotrade.services.read.values import to_scalar
from algotrade.services.selection import fields_view
from tests.unit.services.screening.test_rule_screens import DAY, LIQ, seeded


def _per_record(frame: pd.DataFrame) -> dict[str, dict[str, object]]:
    columns = [c for c in frame.columns if c != "instrument_id"]
    rows: dict[str, dict[str, object]] = {}
    for record in frame.to_dict("records"):
        values = {c: to_scalar(record[c]) for c in columns}
        rows[str(record["instrument_id"])] = {c: v for c, v in values.items() if v is not None}
    return rows


def test_rows_equal_the_per_record_conversion() -> None:
    reader, _ = seeded()
    fields = ["instrument.status", f"{LIQ}.underlying_price", f"{LIQ}.chain_oi", f"{LIQ}.put_tier"]
    view, source = fields_view(reader, fields, DAY, held=HARNESS_ALL)
    expected = _per_record(source.frame)
    assert {i: dict(view.row(i)) for i in view} == expected
    assert any(len(row) < len(fields) for row in expected.values())  # a gap stays out


def test_a_requested_id_with_nothing_known_keeps_an_empty_row() -> None:
    reader, _ = seeded()
    view, _ = fields_view(reader, [f"{LIQ}.chain_oi"], DAY, ["EQ:AAA", "EQ:NOPE"], held=HARNESS_ALL)
    assert dict(view.row("EQ:NOPE")) == {} and dict(view.row("EQ:AAA")) == {f"{LIQ}.chain_oi": 5000}
