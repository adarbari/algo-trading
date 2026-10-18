"""``etf_macro@v1``: hand-computed levels and means, staleness, the VX curve (monthly expiries
after the session only, the trade date equal to the VIX date), the cape and carry columns, absent
series as null columns, point in time through the real loaders, and the licence / map fitness."""

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from algotrade.config.site.macro import MacroSettings
from algotrade.core.time.calendar import sessions_ending
from algotrade.data import feature_inputs as inputs
from algotrade.features.rollups.bridges import etf_macro as em
from algotrade.features.rollups.bridges import etf_map
from tests.helpers.rollup_store import END, store
from tests.helpers.stored_frames import stamped
from tests.unit.config.site.test_settings import site

D = em.D
REPO = Path(__file__).resolve().parents[5]
F32 = 1e-6
PINNED = "f22e673df0ba9d8f6387c0ed04cd4c7f5b36498608e32ecd8105b3ed4d45bf54"
IDS = pd.DataFrame(
    {"symbol": list(etf_map.carriers()), "instrument_id": [f"EQ:{t}" for t in etf_map.carriers()]}
)


def obs(use: em.Use, day: date, value: float) -> dict[str, object]:
    return {"instrument_id": use.id, "obs_date": day, "value": value}


def daily(use: em.Use, values: list[float], end: date = END) -> list[dict[str, object]]:
    days = sessions_ending(end, len(values) + 1)[:-1]
    return [obs(use, d, v) for d, v in zip(days, values, strict=True)]


def run(
    rows: list[dict[str, object]], vx: pd.DataFrame | None = None, session: date = END
) -> pd.DataFrame:
    macro = pd.DataFrame(rows) if rows else None
    out = em.compute({em.MACRO: macro, em.VX: vx, em.SYMBOL_IDS: IDS}, session, D)
    return out.set_index("instrument_id")


def vx_rows(trade: date, expiries: list[date], settles: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {"session_date": trade, "instrument_id": [f"FUT:VX-{e}" for e in expiries],
         "expiry": expiries, "settle": settles}
    )  # fmt: skip


def test_a_level_is_in_decimals_and_only_its_fund_carries_it() -> None:
    hy = em.LEVELS["hy_oas"][0]
    got = run(daily(hy, [4.0, 4.5, 5.0]))
    assert got.loc["EQ:HYG", "hy_oas"] == pytest.approx(0.05, abs=F32)
    assert got.loc["EQ:LQD"].isna().all() or np.isnan(got.loc["EQ:LQD", "hy_oas"])
    assert np.isnan(got.loc["EQ:SPY", "hy_oas"])


def test_a_mean_needs_the_share_of_its_window_and_a_stale_series_is_null() -> None:
    hy = em.LEVELS["hy_oas"][0]
    full = run(daily(hy, [4.0] * 49 + [5.0]))
    assert full.loc["EQ:HYG", "hy_oas_ma50"] == pytest.approx((48 * 4 + 5) / 49 / 100, abs=F32)
    assert np.isnan(full.loc["EQ:HYG", "hy_oas_ma200"])  # 50 of 200 observations
    thin = run(daily(hy, [4.0] * 39))  # 39 of 50 < 80%
    assert np.isnan(thin.loc["EQ:HYG", "hy_oas_ma50"])
    assert thin.loc["EQ:HYG", "hy_oas"] == pytest.approx(0.04, abs=F32)
    old = run(daily(hy, [4.0] * 5, end=END - timedelta(days=30)))
    assert np.isnan(old.loc["EQ:HYG", "hy_oas"])


def test_the_delayed_class_tolerates_ten_days_of_publication_lag() -> None:
    wti = em.LEVELS["wti"][0]
    rows = [obs(wti, END - timedelta(days=12), 70.0)]
    assert run(rows).loc["EQ:USO", "wti"] == pytest.approx(70.0)
    assert np.isnan(run([obs(wti, END - timedelta(days=25), 70.0)]).loc["EQ:USO", "wti"])


def test_cape_and_fx_carry_by_fund_with_a_missing_series_null() -> None:
    day = END - timedelta(days=40)
    rows = [
        obs(em.CAPES["EWJ"], day, 21.5),
        obs(em.RATES["USD"], day, 4.0),
        obs(em.RATES["JPY"], day, 1.0),
        obs(em.CAPES["EWG"], END - timedelta(days=130), 18.0),  # stale
    ]
    got = run(rows)
    assert got.loc["EQ:EWJ", "cape"] == pytest.approx(21.5)
    assert np.isnan(got.loc["EQ:EWG", "cape"])
    assert got.loc["EQ:FXY", "fx_carry"] == pytest.approx(-0.03, abs=F32)
    assert np.isnan(got.loc["EQ:FXE", "fx_carry"])  # no EUR rate stored


def test_no_macro_and_no_futures_still_gives_one_null_row_per_fund_found() -> None:
    got = run([])
    assert set(got.index) == {f"EQ:{t}" for t in etf_map.carriers()}
    assert got.isna().all().all()


def test_a_fund_missing_from_the_reference_has_no_row() -> None:
    ids = IDS[IDS["symbol"] != "HYG"]
    out = em.compute({em.MACRO: None, em.VX: None, em.SYMBOL_IDS: ids}, END, D)
    assert "EQ:HYG" not in set(out["instrument_id"])


def test_monthly_expiry_rule() -> None:
    assert em.is_monthly_expiry(date(2026, 10, 21))  # Wed, 30 days before Nov 20 (3rd Friday)
    assert not em.is_monthly_expiry(date(2026, 10, 14))  # a weekly
    assert not em.is_monthly_expiry(date(2026, 10, 28))
    assert em.is_monthly_expiry(date(2026, 11, 18))


def test_vx_basis_and_roll_use_monthly_expiries_after_the_session() -> None:
    vix = em.VIX
    trade = date(2026, 10, 1)  # the previous session of END
    vx = vx_rows(
        trade,
        [date(2026, 9, 16), date(2026, 10, 7), date(2026, 10, 21), date(2026, 11, 18)],
        [99.0, 11.0, 20.5, 21.5],  # expired, a weekly, F1, F2
    )
    got = run([obs(vix, trade, 20.0)], vx)
    assert got.loc["EQ:SPY", "vx_basis"] == pytest.approx(20.5 / 20.0 - 1, abs=F32)
    assert got.loc["EQ:SPY", "vx_roll"] == pytest.approx(21.5 / 20.5 - 1, abs=F32)


def test_vx_basis_is_null_when_the_vix_date_differs_from_the_trade_date() -> None:
    trade = date(2026, 10, 1)
    vx = vx_rows(trade, [date(2026, 10, 21), date(2026, 11, 18)], [20.5, 21.5])
    got = run([obs(em.VIX, date(2026, 9, 30), 20.0)], vx)
    assert np.isnan(got.loc["EQ:SPY", "vx_basis"])
    assert got.loc["EQ:SPY", "vx_roll"] == pytest.approx(21.5 / 20.5 - 1, abs=F32)


def test_a_curve_without_a_settle_is_null() -> None:
    trade = date(2026, 10, 1)
    vx = vx_rows(trade, [date(2026, 10, 21), date(2026, 11, 18)], [np.nan, 21.5])
    got = run([obs(em.VIX, trade, 20.0)], vx)
    assert np.isnan(got.loc["EQ:SPY", "vx_basis"]) and np.isnan(got.loc["EQ:SPY", "vx_roll"])


def vintages(use: em.Use, day: date, vintage: date, value: float) -> pd.DataFrame:
    row = {
        "instrument_id": use.id, "series": use.key, "obs_date": day, "vintage_date": vintage,
        "value": value, "vintage_kind": "lagged",
    }  # fmt: skip
    return stamped([row], vintage, f"m-{vintage}", source="fred")


def test_a_vintage_published_after_the_session_is_not_read_through_the_loader() -> None:
    writer, reader = store()
    hy = em.LEVELS["hy_oas"][0]
    day = END - timedelta(days=3)
    writer.write_table(em.MACRO, END, "a", vintages(hy, day, END, 4.0))
    writer.write_table(
        em.MACRO, END + timedelta(days=1), "b", vintages(hy, day, END + timedelta(days=1), 9.0)
    )
    loaded = inputs.load_input(reader, em.MACRO, [END], em.HISTORY_SESSIONS, ids=tuple(em.USES))
    frame = loaded.at(END, em.HISTORY_SESSIONS)
    assert frame is not None and list(frame["value"]) == [4.0]


def vx_stored(trade: date, known: date, settle: float, run_id: str) -> pd.DataFrame:
    row = {
        "instrument_id": "FUT:VX-2026-10-21", "root": "VX", "expiry": date(2026, 10, 21),
        "known_from": known, "contract": "VX", "settle": settle,
    }  # fmt: skip
    return stamped([row], trade, run_id)


def test_a_vx_row_known_from_the_session_after_is_absent_and_a_restatement_waits() -> None:
    writer, reader = store()
    trade = date(2026, 10, 1)
    writer.write_table(em.VX, trade, "a", vx_stored(trade, END, 20.0, "a"))
    writer.write_table(em.VX, END, "b", vx_stored(END, END + timedelta(days=3), 25.0, "b"))
    # the restatement of the trade date, known only from later
    writer.write_table(em.VX, trade, "c", vx_stored(trade, END + timedelta(days=3), 30.0, "c"))
    loaded = inputs.load_input(reader, em.VX, [END], 5)
    frame = loaded.at(END, 5)
    assert frame is not None
    assert list(frame["session_date"]) == [trade] and list(frame["settle"]) == [20.0]
    later = loaded.at(END + timedelta(days=3), 5)
    assert later is not None and 30.0 in set(later["settle"])


def test_the_map_is_pinned_to_the_version() -> None:
    """Changing which fund carries a signal changes what the stored columns mean: bump
    ``etf_map.VERSION`` (and the group's version), then update the pin."""
    assert (etf_map.VERSION, etf_map.map_hash()) == (1, PINNED)


def test_licences_and_staleness_classes_follow_macro_toml() -> None:
    settings = MacroSettings.from_document(site("macro"))
    by_key = {s.key: s for s in settings.series}
    personal = {k for k, s in by_key.items() if s.licence == "personal"}
    used = {u.key for u in em.USES.values()}
    assert used <= set(by_key)
    assert {k for k in used if k in by_key and k in em.PERSONAL} == {
        k for k in used if k in personal
    }
    for u in em.USES.values():
        if u.key in by_key:
            assert by_key[u.key].kind == ("index" if u.index else "macro")
            monthly = by_key[u.key].cadence == "monthly"
            assert monthly == (u.cls == em.MONTHLY)
