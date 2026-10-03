"""``dividends@v1``: trailing-12-month sum split-adjusted to the session, yield, zero vs
unknown by history, specials, and a stored ``price_stats@v1`` read through the framework."""

from dataclasses import replace
from datetime import date, timedelta

import pandas as pd
import pytest

from algotrade.features.framework.runner import compute_in_memory, compute_one
from algotrade.features.rollups import dividends, price_stats
from algotrade.features.rollups.dividends import ROLLUP, DividendParams
from tests.rollup_helpers import END, series, store, write_bars, write_dividends, write_split


def _setup() -> tuple[object, list[date]]:
    writer, reader = store()
    closes = {"EQ:A": series(260), "EQ:NONE": series(260, 2), "EQ:NEW": series(100, 3)}
    closes["EQ:YOUNG"] = series(100, 4)
    days = write_bars(writer, closes)
    write_dividends(
        writer,
        [
            ("EQ:A", END - timedelta(days=365), 9.0, "recurring"),  # just outside the window
            ("EQ:A", END - timedelta(days=300), 0.82, "recurring"),  # before the 4:1 split
            ("EQ:A", END - timedelta(days=100), 0.25, "recurring"),
            ("EQ:A", END - timedelta(days=10), 1.00, "special"),
            ("EQ:A", END, 0.25, "recurring"),  # ex today: counts
            ("EQ:A", END + timedelta(days=5), 0.30, "recurring"),  # declared, not yet ex
            ("EQ:YOUNG", END - timedelta(days=20), 0.40, "recurring"),
        ],
    )
    write_split(writer, "EQ:A", END - timedelta(days=200), 4.0, END)
    return reader, days


def _rows(reader: object, params: DividendParams | None = None) -> pd.DataFrame:
    params_by_key = {ROLLUP.key: params} if params else None
    out = compute_in_memory(reader, [price_stats.ROLLUP, ROLLUP], [END], params_by_key)  # type: ignore[arg-type]
    frame = out[ROLLUP.key][0].frame
    assert frame is not None
    return frame.set_index("instrument_id")


def test_ttm_is_split_adjusted_to_the_session() -> None:
    reader, _ = _setup()
    rows = _rows(reader)
    a = rows.loc["EQ:A"]
    assert a["div_ttm"] == pytest.approx(0.82 / 4 + 0.25 + 0.25)
    assert a["div_count_ttm"] == 3 and a["last_ex_date"] == END
    close = series(260)[-1]
    assert a["div_yield"] == pytest.approx(a["div_ttm"] / close)
    special = _rows(reader, DividendParams(include_special=True)).loc["EQ:A"]
    assert special["div_ttm"] == pytest.approx(a["div_ttm"] + 1.0)


def test_zero_needs_a_year_of_history_and_a_payer_is_always_known() -> None:
    reader, _ = _setup()
    rows = _rows(reader)
    none = rows.loc["EQ:NONE"]
    assert (none["div_ttm"], none["div_yield"], none["div_count_ttm"]) == (0.0, 0.0, 0)
    assert pd.isna(none["last_ex_date"])
    new = rows.loc["EQ:NEW"]
    assert new[["div_ttm", "div_yield", "div_count_ttm", "last_ex_date"]].isna().all()
    young = rows.loc["EQ:YOUNG"]
    assert young["div_ttm"] == pytest.approx(0.40) and young["div_count_ttm"] == 1
    lenient = _rows(reader, DividendParams(min_history_days=50)).loc["EQ:NEW"]
    assert lenient["div_ttm"] == 0.0


def test_reads_stored_price_stats_and_needs_them() -> None:
    reader, _ = _setup()
    assert compute_one(reader, ROLLUP, END).no_input == (
        f"no rollups/instrument/price_stats@v1 for {END}"
    )


def test_split_factors_and_params() -> None:
    divs = pd.DataFrame(
        {"instrument_id": ["EQ:A", "EQ:A", "EQ:B"], "event_date": [date(2026, 1, 5)] * 2 + [END]}
    )
    splits = pd.DataFrame(
        {
            "instrument_id": ["EQ:A", "EQ:A", "EQ:B"],
            "event_date": [date(2026, 3, 1), END + timedelta(days=1), date(2026, 3, 1)],
            "ratio": [2.0, 3.0, 5.0],
        }
    )
    assert list(dividends.split_factors(divs, splits, END)) == [2.0, 2.0, 1.0]
    assert list(dividends.split_factors(divs, None, END)) == [1.0, 1.0, 1.0]
    assert dividends.ttm(None, None, END, DividendParams()).empty
    with pytest.raises(ValueError, match="min_history_days"):
        replace(DividendParams(), min_history_days=0)
