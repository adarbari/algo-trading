"""``dividends@v2``: trailing-12-month sum split-adjusted to the session, zero vs unknown by
history, specials, a stored ``price_stats@v2`` read through the framework, and the
materialised ``div_yield`` expression computed from them."""

from dataclasses import replace
from datetime import date, timedelta

import pandas as pd
import pytest

from algotrade.features.framework.runner import compute_in_memory, compute_one
from algotrade.features.rollups.corporate import dividends
from algotrade.features.rollups.corporate.dividends import GROUP, DividendParams
from algotrade.features.rollups.price import price_stats
from algotrade.features.site import site_features
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT
from tests.helpers.rollup_store import END, series, store, write_bars, write_dividends, write_split


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
    params_by_key = {GROUP.key: params} if params else None
    out = compute_in_memory(reader, [price_stats.GROUP, GROUP], [END], params_by_key)  # type: ignore[arg-type]
    frame = out[GROUP.key][0].frame
    assert frame is not None
    return frame.set_index("instrument_id")


def test_ttm_is_split_adjusted_to_the_session() -> None:
    reader, _ = _setup()
    rows = _rows(reader)
    a = rows.loc["EQ:A"]
    assert a["div_ttm"] == pytest.approx(0.82 / 4 + 0.25 + 0.25)
    assert a["div_count_ttm"] == 3 and a["last_ex_date"] == END
    special = _rows(reader, DividendParams(include_special=True)).loc["EQ:A"]
    assert special["div_ttm"] == pytest.approx(a["div_ttm"] + 1.0)


def test_zero_needs_a_year_of_history_and_a_payer_is_always_known() -> None:
    reader, _ = _setup()
    rows = _rows(reader)
    none = rows.loc["EQ:NONE"]
    assert (none["div_ttm"], none["div_count_ttm"]) == (0.0, 0)
    assert pd.isna(none["last_ex_date"])
    new = rows.loc["EQ:NEW"]
    assert new[["div_ttm", "div_count_ttm", "last_ex_date"]].isna().all()
    young = rows.loc["EQ:YOUNG"]
    assert young["div_ttm"] == pytest.approx(0.40) and young["div_count_ttm"] == 1
    lenient = _rows(reader, DividendParams(min_history_days=50)).loc["EQ:NEW"]
    assert lenient["div_ttm"] == 0.0


def test_the_materialised_yield_is_ttm_over_close() -> None:
    reader, _ = _setup()
    yields = site_features(FileConfigStore(REPO_ROOT / "config")).groups["div_yield@v1"]
    out = compute_in_memory(reader, [price_stats.GROUP, GROUP, yields], [END])  # type: ignore[arg-type]
    frame = out["div_yield@v1"][0].frame
    assert frame is not None
    got = frame.set_index("instrument_id")["div_yield"]
    ttm = _rows(reader)["div_ttm"]
    assert got["EQ:A"] == pytest.approx(ttm["EQ:A"] / series(260)[-1], rel=1e-6)
    assert got["EQ:NONE"] == 0.0 and pd.isna(got["EQ:NEW"])


def test_reads_stored_price_stats_and_needs_them() -> None:
    reader, _ = _setup()
    assert compute_one(reader, GROUP, END).no_input == (
        f"no rollups/instrument/price_stats@v2 for {END}"
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
