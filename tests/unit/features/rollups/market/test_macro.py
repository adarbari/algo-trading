"""``market_macro@v1`` over a ``macro/series`` store written through the storage layer:
hand-computed levels, transforms and windows, vintages respected (a value with a later vintage
is not seen), the curve from the session's own Treasury curve else FRED, one null-safe row with
no macro data, and a backfill equal to the nightly."""

from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from algotrade.config.site.settings import load_macro
from algotrade.core.time.calendar import sessions_ending
from algotrade.data import StoreReader
from algotrade.features.framework.runner import compute_one, compute_sessions
from algotrade.features.rollups.market import macro
from algotrade.storage.configs.files import FileConfigStore
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.rollup_store import END, store
from tests.helpers.stored_frames import stamped

GROUP = macro.GROUP
F32 = 1e-6
REPO = Path(__file__).resolve().parents[5]


def obs(key: str, day: date, vintage: date, value: float | None) -> dict[str, object]:
    return {
        "instrument_id": macro.ID[key],
        "series": key,
        "obs_date": day,
        "vintage_date": vintage,
        "value": value,
        "vintage_kind": "lagged",
    }


def daily(key: str, values: Sequence[float], end: date = END) -> list[dict[str, object]]:
    """One observation per session up to the session before ``end``, each known the next day
    (so all are known by ``end``)."""
    days = sessions_ending(end, len(values) + 1)[:-1]
    return [obs(key, d, d + timedelta(days=1), v) for d, v in zip(days, values, strict=True)]


def monthly(key: str, values: Sequence[float], last: str = "2026-08-01") -> list[dict[str, object]]:
    """Monthly observations up to ``last``, each published 40 days later."""
    index = pd.date_range(end=last, periods=len(values), freq="MS")
    return [
        obs(key, d.date(), d.date() + timedelta(days=40), v)
        for d, v in zip(index, values, strict=True)
    ]


def write(writer: StoreWriter, rows: list[dict[str, object]], stored: date = END) -> None:
    run = f"macro-{stored}"
    writer.write_table(macro.MACRO, stored, run, stamped(rows, stored, run, source="fred"))


def write_curve(writer: StoreWriter, day: date, rates: dict[str, float]) -> None:
    rows = [
        {"instrument_id": f"RATE:UST-{t}", "ts": pd.Timestamp(day, tz="UTC"), "tenor": t,
         "tenor_days": n, "rate_par": rates[t], "rate_cont": rates[t]}
        for t, n in (("3M", 91), ("2Y", 730), ("10Y", 3650))
    ]  # fmt: skip
    writer.write_table(macro.TREASURY, day, f"rates-{day}", stamped(rows, day, f"rates-{day}"))


def row(reader: StoreReader, session: date = END) -> dict[str, object]:
    frame = compute_one(reader, GROUP, session).frame
    assert frame is not None and list(frame["instrument_id"]) == ["MKT:US"]
    return frame.iloc[0].to_dict()


def test_without_macro_data_the_row_is_written_and_every_macro_column_is_null() -> None:
    writer, reader = store()
    write_curve(writer, END, {"3M": 0.05, "2Y": 0.045, "10Y": 0.04})
    got = row(reader)
    assert got["curve_10y3m"] == pytest.approx(-0.01, abs=F32)
    assert got["curve_10y2y"] == pytest.approx(-0.005, abs=F32)
    assert got["curve_source"] == "treasury"
    rest = [c for c in macro.COLUMNS if not c.startswith("curve_") or c.endswith("_252d")]
    assert all(pd.isna(got[c]) for c in rest), {c: got[c] for c in rest if not pd.isna(got[c])}
    pure = macro.compute({macro.MACRO: None, macro.TREASURY: None}, END, None)
    assert list(pure["instrument_id"]) == ["MKT:US"]
    assert pure.drop(columns="instrument_id").isna().all(axis=None)


def test_levels_and_transforms_by_hand() -> None:
    writer, reader = store()
    year = [100.0] + [101.0] * 11 + [103.0]  # a year apart: 100 -> 103
    write(
        writer,
        daily("BAMLH0A0HYM2", [4.0, 5.25])
        + daily("BAMLC0A0CM", [1.1])
        + daily("VIX", [30.0])
        + daily("VIX3M", [25.0])
        + daily("DFII10", [1.8])
        + monthly("PAYEMS", year)
        + monthly("CPIAUCSL", year)
        + monthly("FEDFUNDS", [2.0] + [3.0] * 11 + [4.5])
        + monthly("NFCI", [0.25])
        + monthly("DRTSCILM", [22.5])
        + monthly("RECPROUSM156N", [31.0])
        + monthly("CFNAIMA3", [-0.8]),
    )
    got = row(reader)
    expected = {
        "hy_oas": 0.0525, "ig_oas": 0.011, "vix": 30.0, "vix3m": 25.0, "vix_term_ratio": 1.2,
        "real_10y": 0.018, "payrolls_yoy": 0.03, "cpi_yoy": 0.03, "fedfunds_chg_12m": 0.025,
        "nfci": 0.25, "sloos_ci_tightening": 0.225, "recession_prob_smoothed": 0.31,
        "cfnai_ma3": -0.8,
    }  # fmt: skip
    for column, value in expected.items():
        assert got[column] == pytest.approx(value, rel=F32), column
    assert pd.isna(got["permits_yoy"]) and pd.isna(got["core_pce_yoy"])  # no series stored


def test_a_value_with_a_later_vintage_is_not_seen() -> None:
    writer, reader = store()
    jan, revised_on = date(2026, 8, 1), END + timedelta(days=3)
    write(
        writer,
        [
            obs("UNRATE", jan, date(2026, 9, 5), 4.1),
            obs("UNRATE", jan, revised_on, 4.6),  # the revision, published after END
            obs("UNRATE", date(2026, 9, 1), revised_on, 4.8),  # September, published after END
        ],
    )
    assert row(reader)["unrate"] == pytest.approx(0.041, rel=F32)
    later = sessions_ending(revised_on + timedelta(days=3), 1)[0]
    assert row(reader, later)["unrate"] == pytest.approx(0.048, rel=F32)


def test_the_curve_comes_from_fred_when_the_session_has_no_curve_of_its_own() -> None:
    writer, reader = store()
    write_curve(writer, END - timedelta(days=1), {"3M": 0.05, "2Y": 0.045, "10Y": 0.04})
    write(writer, daily("T10Y3M", [0.5, 0.75]) + daily("T10Y2Y", [0.25]))
    got = row(reader)
    assert (got["curve_source"], got["curve_10y3m"]) == ("fred", pytest.approx(0.0075, rel=F32))
    assert got["curve_10y2y"] == pytest.approx(0.0025, rel=F32)


def test_unemployment_trend_and_sahm_gap_by_hand() -> None:
    writer, reader = store()
    rates = [3.5, 3.6, 3.4, 3.5, 3.5, 3.6, 3.7, 3.7, 3.8, 3.9, 4.0, 4.1, 4.2, 4.3, 4.4]
    write(writer, monthly("UNRATE", rates))
    got = row(reader)
    ma3 = pd.Series(rates).rolling(3).mean().to_numpy()
    assert got["unrate"] == pytest.approx(0.044, rel=F32)
    assert got["unrate_vs_12m_avg"] == pytest.approx((4.4 - np.mean(rates[-12:])) / 100, rel=1e-5)
    assert got["sahm_gap"] == pytest.approx((ma3[-1] - min(ma3[2:-1])) / 100, rel=1e-5)
    short = store()
    write(short[0], monthly("UNRATE", rates[-14:]))  # 14 months: the trend, not the Sahm gap
    got = row(short[1])
    assert not pd.isna(got["unrate_vs_12m_avg"]) and pd.isna(got["sahm_gap"])


def test_claims_credit_and_curve_windows_by_hand() -> None:
    writer, reader = store()
    weeks = pd.date_range(end="2026-09-26", periods=60, freq="7D")
    claims = [250.0] * 50 + [200.0] + [230.0] * 9  # the low is 200 within the last 52 weeks
    hy = [3.0] * 100 + [2.5] + [3.5] * 38 + [4.2]
    curve = [0.5] * 270 + [-0.2] * 30
    write(
        writer,
        [
            obs("IC4WSA", d.date(), d.date() + timedelta(days=5), v)
            for d, v in zip(weeks, claims, strict=True)
        ]
        + daily("BAMLH0A0HYM2", hy)
        + daily("T10Y3M", curve),
    )
    got = row(reader)
    assert got["claims_4w_vs_52w_low"] == pytest.approx(230 / 200, rel=F32)
    then = hy[len(hy) - 126]  # the observation on the session 126 sessions before END
    assert got["hy_oas_chg_126d"] == pytest.approx((4.2 - then) / 100, rel=1e-5)
    assert got["hy_oas_vs_126d_low"] == pytest.approx((4.2 - 2.5) / 100, rel=1e-5)
    assert got["curve_inverted_days_252d"] == 30
    short = store()
    write(short[0], daily("BAMLH0A0HYM2", hy[-100:]) + daily("T10Y3M", curve[-200:]))
    got = row(short[1])
    assert pd.isna(got["hy_oas_chg_126d"]) and pd.isna(got["hy_oas_vs_126d_low"])
    assert pd.isna(got["curve_inverted_days_252d"])
    assert got["hy_oas"] == pytest.approx(0.042, rel=F32)


def test_backfill_equals_nightly() -> None:
    writer, reader = store()
    write(
        writer, daily("BAMLH0A0HYM2", list(np.linspace(3, 5, 200))) + monthly("UNRATE", [4.0] * 15)
    )
    days = sessions_ending(END, 5)
    backfill = list(compute_sessions(reader, GROUP, days))
    for result in backfill:
        nightly = compute_one(reader, GROUP, result.session).frame
        assert result.frame is not None and nightly is not None
        pd.testing.assert_frame_equal(result.frame, nightly)
    assert backfill[0].frame["hy_oas"].iloc[0] < backfill[-1].frame["hy_oas"].iloc[0]  # type: ignore[index]


def test_transforms_and_licences_follow_the_registry() -> None:
    registry = load_macro(FileConfigStore(REPO / "config"))
    for key, use in macro.SERIES.items():
        series = registry.by_key(key)
        assert use.transform == series.transform, key
        assert use.id(key) == series.instrument_id, key
        assert (key in macro.PERSONAL) == (series.licence == "personal"), key
