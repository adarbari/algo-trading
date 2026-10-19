"""``filing_text_change@v1``: a row per instrument of a company whose latest periodic filing
became known in the last five sessions; one company with two share classes gives both the same
row; a company with no instrument (null id) has no row; statuses with null measures; typed
output."""

from datetime import date, timedelta

import pandas as pd

from algotrade.features.framework.columns import conform
from algotrade.features.rollups.text import filing_text_change as ftc
from tests.unit.features.rollups.text.test_comparison import REPORT, SESSION, frame, ten_q


def compute(data: pd.DataFrame | None) -> pd.DataFrame:
    return ftc.compute({ftc.FILING_TEXT: data}, SESSION, None)


def test_a_recent_filing_gives_a_typed_row_with_its_comparison() -> None:
    old = ten_q("OLD", REPORT - timedelta(days=365), date(2025, 8, 5))
    out = compute(frame(ten_q("NEW", REPORT, date(2026, 9, 30)), old))
    [row] = out.to_dict("records")
    assert row["instrument_id"] == "EQ:AAA" and row["ftc_accession"] == "NEW"
    assert row["ftc_prior_accession"] == "OLD" and row["ftc_form"] == "10-Q"
    assert row["ftc_known_from"] == date(2026, 9, 30) and row["ftc_status"] == "OK"
    assert row["ftc_cosine"] == 1.0 and row["ftc_items_compared"] == 2
    typed = conform("rollups/instrument/filing_text_change@v1", out, ftc.COLUMNS)
    assert str(typed["ftc_cosine"].dtype) == "float32"
    assert str(typed["ftc_items_compared"].dtype) == "int64[pyarrow]"


def test_two_share_classes_of_one_company_share_the_row_and_a_null_id_has_none() -> None:
    old = ten_q("OLD", REPORT - timedelta(days=365), date(2025, 8, 5))
    both = [r | {"instrument_id": i} for r in ten_q("NEW", REPORT, date(2026, 9, 30))
            for i in ("EQ:AAA", "EQ:AAB")]  # fmt: skip
    out = compute(frame(both, old))
    assert out["instrument_id"].tolist() == ["EQ:AAA", "EQ:AAB"]
    assert out["ftc_accession"].nunique() == 1
    delisted = frame(ten_q("NEW", REPORT, date(2026, 9, 30), iid=None), old)
    assert compute(delisted).empty


def test_a_non_ok_status_has_null_measures_never_zero() -> None:
    out = compute(frame(ten_q("NEW", REPORT, date(2026, 9, 30))))
    [row] = out.to_dict("records")
    assert row["ftc_status"] == "NO_PRIOR" and row["ftc_prior_accession"] is None
    assert all(pd.isna(row[c]) for c in ("ftc_cosine", "ftc_jaccard", "ftc_items_compared"))


def test_nothing_recent_or_no_input_gives_no_rows() -> None:
    assert compute(None).empty and compute(pd.DataFrame()).empty
    assert compute(frame(ten_q("STALE", REPORT, date(2026, 9, 1)))).empty
