"""``market_macro@v3`` over a ``macro/series`` store written through the storage layer:
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
    pure = macro.compute({macro.MACRO: None, macro.TREASURY: None}, END, macro.D)
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
        + monthly("CFNAIMA3", [-0.8])
        + monthly("EBP", [0.4, 1.25], last="2026-08-01")  # percentage points
        + monthly("EBP_RECESSION_PROB", [0.62])  # a fraction already
        + daily("OFR_FSI", [3.5, -1.25])
        + daily("EPU_DAILY", [180.0]),
    )
    got = row(reader)
    expected = {
        "hy_oas": 0.0525, "ig_oas": 0.011, "vix": 30.0, "vix3m": 25.0, "vix_term_ratio": 1.2,
        "real_10y": 0.018, "payrolls_yoy": 0.03, "cpi_yoy": 0.03, "fedfunds_chg_12m": 0.025,
        "nfci": 0.25, "sloos_ci_tightening": 0.225, "recession_prob_smoothed": 0.31,
        "cfnai_ma3": -0.8, "ebp": 0.0125, "ebp_recession_prob": 0.62, "ofr_fsi": -1.25,
        "epu": 180.0,
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


def test_a_yoy_uses_the_year_ago_value_as_the_session_knew_it() -> None:
    writer, reader = store()
    year_ago, now, revised_on = date(2025, 8, 1), date(2026, 8, 1), END + timedelta(days=3)
    write(
        writer,
        [
            obs("CPIAUCSL", year_ago, date(2025, 9, 10), 100.0),
            obs("CPIAUCSL", year_ago, revised_on, 90.0),  # revised after END
            obs("CPIAUCSL", now, date(2026, 9, 10), 103.0),
        ],
    )
    assert row(reader)["cpi_yoy"] == pytest.approx(0.03, rel=F32)
    later = sessions_ending(revised_on + timedelta(days=3), 1)[0]
    assert row(reader, later)["cpi_yoy"] == pytest.approx(103 / 90 - 1, rel=F32)


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
    write(short[0], monthly("UNRATE", rates[-11:]))  # 11 months: the trend, not the Sahm gap
    got = row(short[1])
    assert got["unrate_vs_12m_avg"] == pytest.approx((4.4 - np.mean(rates[-11:])) / 100, rel=1e-5)
    assert pd.isna(got["sahm_gap"])  # 9 of the previous 12 months have a 3-month mean


def _unrate(rates: list[float], drop: tuple[int, ...]) -> dict[str, object]:
    """UNRATE monthly to August 2026 (each released about 35 days later), without the months
    at ``drop`` (positions in ``rates``): months never published."""
    writer, reader = store()
    rows = monthly("UNRATE", rates)
    rows = [{**r, "vintage_date": r["obs_date"] + timedelta(days=35), "vintage_kind": "alfred"}
            for i, r in enumerate(rows) if i not in drop]  # fmt: skip
    write(writer, rows)
    return row(reader)


def test_one_missing_month_is_skipped_and_three_are_too_many() -> None:
    """October 2025's unemployment rate was never published (the shutdown): v2 read nothing
    for a year after it; one gap now leaves 11 of 12 months, three leave 9 (null)."""
    rates = [3.5, 3.6, 3.4, 3.5, 3.5, 3.6, 3.7, 3.7, 3.8, 3.9, 4.0, 4.1, 4.2, 4.3, 4.4]
    gap = 9  # a month inside both windows
    got = _unrate(rates, (gap,))
    kept = rates[3:gap] + rates[gap + 1 :]
    assert got["unrate_vs_12m_avg"] == pytest.approx((4.4 - np.mean(kept)) / 100, rel=1e-5)
    present = dict(enumerate(rates)) | {gap: None}

    def ma3(i: int) -> float:
        values = [present[j] for j in range(i - 2, i + 1) if present.get(j) is not None]
        return float(np.mean(values)) if len(values) >= 2 else np.nan  # type: ignore[arg-type]

    lows = [ma3(i) for i in range(2, 14)]
    assert got["sahm_gap"] == pytest.approx((ma3(14) - np.nanmin(lows)) / 100, rel=1e-5)
    three = _unrate(rates, (9, 10, 11))  # 9 of 12 months; 9 of the 12 lows
    assert pd.isna(three["unrate_vs_12m_avg"]) and pd.isna(three["sahm_gap"])
    assert three["unrate"] == pytest.approx(0.044, rel=F32)


def test_params_bound_the_minimums() -> None:
    with pytest.raises(ValueError, match="min_months_12"):
        macro.Params(min_months_12=13)
    with pytest.raises(ValueError, match="min_months_3"):
        macro.Params(min_months_3=0)


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


def test_the_last_session_of_a_backfill_reads_its_own_partition_as_known() -> None:
    """Every series stored in one partition dated the newest session (a backfill): that session
    reads each lagged series' previous observation (its own is public the next day), an ALFRED
    vintage dated on it, and the index levels, exactly as the session before reads its own."""
    writer, reader = store()
    days = sessions_ending(END, 30)
    known = list(zip(days, [*days[1:], END + timedelta(days=1)], strict=True))  # lag 1
    rows = [obs("BAMLH0A0HYM2", d, v, 3.0 + i / 100) for i, (d, v) in enumerate(known)]
    rows += [obs("VIX", d, v, 15.0 + i / 10) for i, (d, v) in enumerate(known)]
    rows += [{**obs("UNRATE", date(2026, 8, 1), END, 4.2), "vintage_kind": "alfred"}]
    write(writer, rows)
    chunk = {r.session: r.frame.iloc[0] for r in compute_sessions(reader, GROUP, days[-3:])}  # type: ignore[union-attr]
    newest, before = chunk[END], chunk[days[-2]]
    assert newest["hy_oas"] == pytest.approx((3.0 + 28 / 100) / 100, rel=F32)  # days[-2]'s
    assert before["hy_oas"] == pytest.approx((3.0 + 27 / 100) / 100, rel=F32)
    assert newest["vix"] == pytest.approx(15.0 + 2.8, rel=F32)
    assert newest["unrate"] == pytest.approx(0.042, rel=F32) and pd.isna(before["unrate"])
    pd.testing.assert_series_equal(newest, compute_one(reader, GROUP, END).frame.iloc[0])  # type: ignore[union-attr]


def test_transforms_and_licences_follow_the_registry() -> None:
    registry = load_macro(FileConfigStore(REPO / "config"))
    for key, use in macro.SERIES.items():
        series = registry.by_key(key)
        assert use.transform == series.transform, key
        assert use.id(key) == series.instrument_id, key
        assert (key in macro.PERSONAL) == (series.licence == "personal"), key
