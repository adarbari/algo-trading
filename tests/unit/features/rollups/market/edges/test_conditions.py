"""``market_conditions@v2``: each verdict by hand over synthetic series. The same-date rule (a
series with no observation on the VIX's date is null, never an older value), nulls before a
series starts and for an incomplete window, a stale VIX is all null, the stand-aside verdict
follows its three conditions with Kleene unknowns, the licences (personal values, open
verdicts) and the calendar columns from the FOMC rows known by the session."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.rollups.market import indicators, trend
from algotrade.features.rollups.market.edges import conditions as c
from algotrade.features.rollups.market.macro import MACRO

END = date(2026, 10, 2)  # a Friday
DAYS = sessions_ending(END, 300)[:-1]  # observations up to the session before END
TREND, INDICATORS = trend.GROUP.table, indicators.GROUP.table


def macro(
    vix: float = 20.0, vix3m: float = 22.0, extra: dict[str, float] | None = None,
    days: list[date] = DAYS, shape: dict[str, dict[int, float]] | None = None,
) -> pd.DataFrame:  # fmt: skip
    """Flat series at the given levels (``extra``: key -> level of VIX9D / VIX6M / VVIX),
    ``shape`` overrides single observations by index of ``days``."""
    levels = {c.VIX: vix, c.VIX3M: vix3m} | {f"IDX:{k}": v for k, v in (extra or {}).items()}
    rows = []
    for key, level in levels.items():
        for i, d in enumerate(days):
            value = ((shape or {}).get(key) or {}).get(i, level)
            rows.append({"instrument_id": key, "obs_date": d, "value": value})
    return pd.DataFrame(rows)


def run(series: pd.DataFrame, session: date = END, **inputs: object) -> dict[str, object]:
    frame = c.compute({MACRO: series, **inputs}, session, c.D)  # type: ignore[arg-type]
    return {k: (None if pd.isna(v) else v) for k, v in frame.iloc[0].to_dict().items()}


def trend_row(
    rv: float | None = 0.12, sma: float | None = 0.03, day: date = DAYS[-1]
) -> pd.DataFrame:
    """A ``market_trend@v2`` row dated ``day`` (default: the VIX's observation date)."""
    return pd.DataFrame(
        [{"session_date": day, "spx_realised_vol_20d": rv, "spx_close_vs_sma200": sma}]
    )


def test_contango_and_the_shared_observation_date() -> None:
    got = run(macro(vix=15, vix3m=20, extra={"VIX9D": 14}))
    assert got["vix_obs_date"] == DAYS[-1]
    assert got["vix_contango_on"] is True and got["vix_front_kink_on"] is False
    assert got["vix9d"] == 14


def test_a_series_without_the_shared_date_is_null_never_an_older_value() -> None:
    older = DAYS[:-1]  # VIX3M's newest observation is a day before the VIX's
    series = pd.concat([macro(days=DAYS).query("`instrument_id` == @c.VIX"),
                        macro(days=older).query("`instrument_id` == @c.VIX3M")])  # fmt: skip
    got = run(series)
    assert got["vix_contango_on"] is None and got["backwardation_run"] is None
    assert got["short_premium_allowed"] is None  # nothing else is on, so unknown


def test_before_a_series_starts_its_columns_and_verdicts_are_null() -> None:
    got = run(macro())  # no VIX9D, VIX6M or VVIX at all
    assert got["vix9d"] is None and got["vix6m"] is None and got["vvix"] is None
    assert got["vix_front_kink_on"] is None and got["vvix_high_on"] is None
    assert got["vvix_pct_252"] is None


def test_an_incomplete_year_gives_no_percentile_verdicts() -> None:
    got = run(macro(days=DAYS[-100:]))
    assert got["vix_pct_252"] is None and got["vix_low_on"] is None
    assert got["vix_high_on"] is None and got["vix_median_252"] is None
    assert got["vix_high_20"] == 20.0  # the 20-observation window is complete


def test_percentile_low_and_high() -> None:
    low = run(macro(shape={c.VIX: {i: 20 + i % 7 for i in range(len(DAYS) - 1)}}, vix=12))
    assert low["vix_pct_252"] == pytest.approx(100 / 252) and low["vix_low_on"] is True
    high = run(macro(shape={c.VIX: dict.fromkeys(range(len(DAYS) - 1), 10)}, vix=30))
    assert high["vix_high_on"] is True and high["vix_low_on"] is False


def test_a_stale_vix_is_all_null() -> None:
    got = run(macro(days=DAYS[:-10]))
    assert got["vix_obs_date"] is None and got["vix_contango_on"] is None
    assert got["short_premium_allowed"] is None and got["vix_pct_252"] is None


def test_vrp_rich_and_cheap_from_realised_vol() -> None:
    rich = run(macro(vix=20), **{TREND: trend_row(rv=0.12)})  # 20 - 12 = 8 points
    assert rich["index_vrp_rich_on"] is True and rich["index_vrp_cheap_on"] is False
    cheap = run(macro(vix=20), **{TREND: trend_row(rv=0.25)})
    assert cheap["index_vrp_rich_on"] is False and cheap["index_vrp_cheap_on"] is True
    unknown = run(macro(vix=20))
    assert unknown["index_vrp_rich_on"] is None


def spike_then_recovery() -> pd.DataFrame:
    n = len(DAYS)
    return macro(
        vix=22,
        vix3m=25,
        shape={c.VIX: {n - 10: 40.0} | dict.fromkeys(range(n - 300, n - 11), 15.0)},
    )


def test_post_spike_recovery() -> None:
    got = run(spike_then_recovery())
    # 22 against a 20-observation high of 40 (45% off), in contango, above the year's median
    assert got["post_spike_recovery_on"] is True
    still = run(macro(vix=39, vix3m=25, shape={c.VIX: {len(DAYS) - 10: 40.0}}))
    assert still["post_spike_recovery_on"] is False  # backwardation: not recovered


def test_short_premium_is_off_in_backwardation_and_on_when_nothing_is_wrong() -> None:
    assert run(macro(vix=30, vix3m=25), **{TREND: trend_row()})["short_premium_allowed"] is False
    assert run(macro(vix=18, vix3m=22), **{TREND: trend_row()})["short_premium_allowed"] is True


def test_cheap_vol_outside_a_recovery_is_off_and_inside_one_is_not() -> None:
    cheap = {TREND: trend_row(rv=0.30)}
    assert run(macro(vix=18, vix3m=22), **cheap)["short_premium_allowed"] is False
    assert run(spike_then_recovery(), **cheap)["short_premium_allowed"] is True


def test_stress_below_the_200_day_with_rising_vix_is_off() -> None:
    n = len(DAYS)
    rising = macro(vix=36, vix3m=40, shape={c.VIX: {n - 6: 30.0}})
    off = run(rising, **{TREND: trend_row(rv=0.2, sma=-0.05)})
    assert off["short_premium_allowed"] is False
    above = run(rising, **{TREND: trend_row(rv=0.2, sma=0.05)})
    assert above["short_premium_allowed"] is True


def test_rate_shock_is_the_yield_change_or_the_inverted_curve() -> None:
    sessions = sessions_ending(END, 80)
    flat = pd.DataFrame({"session_date": sessions, "rate_par": [0.040] * 80})
    up = pd.DataFrame({"session_date": sessions, "rate_par": [0.040] * 17 + [0.047] * 63})
    assert run(macro(), **{c.TREASURY_10Y: flat})["rate_shock_on"] is None  # curve unknown
    on = indicators.GROUP.table
    inverted = pd.DataFrame([{"curve_10y3m_on": True}])
    off = pd.DataFrame([{"curve_10y3m_on": False}])
    assert run(macro(), **{c.TREASURY_10Y: flat, on: off})["rate_shock_on"] is False
    assert run(macro(), **{c.TREASURY_10Y: up, on: off})["rate_shock_on"] is True
    assert run(macro(), **{c.TREASURY_10Y: flat, on: inverted})["rate_shock_on"] is True
    assert run(macro(), **{on: inverted})["rate_shock_on"] is True  # either side is enough


def test_y10_change_needs_both_ends_within_the_tolerance() -> None:
    sessions = sessions_ending(END, 80)
    frame = pd.DataFrame({"session_date": sessions, "rate_par": np.linspace(0.04, 0.05, 80)})
    assert c.y10_change(frame, END) == pytest.approx(0.01 * 63 / 79)
    assert np.isnan(c.y10_change(frame.iloc[-30:], END))  # history does not reach back 63 sessions
    assert np.isnan(c.y10_change(None, END))


def test_vvix_and_the_high_verdict() -> None:
    got = run(macro(extra={"VVIX": 120.0}))
    assert got["vvix_high_on"] is True and got["vvix_pct_252"] == 100.0
    assert run(macro(extra={"VVIX": 90.0}))["vvix_high_on"] is False


def fomc(*rows: tuple[date, date, str]) -> pd.DataFrame:
    """(release date, known_from, status) FOMC rows."""
    return pd.DataFrame(
        [{"release_key": "FOMC", "release_date": r, "known_from": k, "session_date": k,
          "status": s} for r, k, s in rows]
    )  # fmt: skip


def test_sessions_to_fomc_reads_only_dates_known_by_the_session() -> None:
    meeting = date(2026, 10, 28)
    known = fomc((meeting, date(2026, 1, 1), "scheduled"))
    assert c.calendar_columns(known, END)["sessions_to_fomc"] == 18
    later = fomc((meeting, date(2026, 10, 5), "scheduled"))
    assert pd.isna(c.calendar_columns(later, END)["sessions_to_fomc"])  # announced after END
    on_the_day = c.calendar_columns(known, meeting)
    assert on_the_day["sessions_to_fomc"] == 0 and on_the_day["fomc_cycle_week"] == 0


def test_a_moved_meeting_is_dropped_and_the_latest_version_wins() -> None:
    old, new = date(2026, 10, 28), date(2026, 10, 14)
    rows = fomc((old, date(2026, 1, 1), "scheduled"), (old, date(2026, 9, 1), "moved"),
                (new, date(2026, 9, 1), "scheduled"))  # fmt: skip
    assert c.fomc_dates(rows, END) == [new]


def test_cycle_week_counts_whole_weeks_since_the_last_decision() -> None:
    rows = fomc((date(2026, 9, 16), date(2026, 1, 1), "scheduled"))
    assert c.calendar_columns(rows, END)["fomc_cycle_week"] == (END - date(2026, 9, 16)).days // 7
    assert pd.isna(c.calendar_columns(None, END)["fomc_cycle_week"])


def test_calendar_flags() -> None:
    friday = c.calendar_columns(None, date(2026, 10, 2))
    assert friday["weekday"] == 4 and friday["last_before_weekend"] is True
    assert friday["in_opex_week"] is False
    opex = c.calendar_columns(None, date(2026, 10, 16))  # the month's third Friday
    assert opex["in_opex_week"] is True
    monday = c.calendar_columns(None, date(2026, 10, 5))
    assert monday["weekday"] == 0 and monday["last_before_weekend"] is False
    wednesday = c.calendar_columns(None, date(2026, 11, 25))  # Thanksgiving week: Thursday is shut
    assert wednesday["last_before_weekend"] is False  # Friday trades, the week goes on
    good_friday = c.calendar_columns(None, date(2026, 4, 2))  # Thursday before Good Friday
    assert good_friday["last_before_weekend"] is True


def test_season_share_is_of_the_names_with_an_expected_date() -> None:
    frame = pd.DataFrame({"sessions_to_expected_report": [0, 4, 10, 11, 60, None]})
    assert c.season_share(frame) == pytest.approx(3 / 5)
    assert np.isnan(c.season_share(pd.DataFrame({"sessions_to_expected_report": [None]})))
    assert np.isnan(c.season_share(None))


def test_the_row_is_written_with_every_market_input_missing() -> None:
    got = run(pd.DataFrame(columns=["instrument_id", "obs_date", "value"]))
    assert got["weekday"] == 4 and got["in_opex_week"] is False
    assert got["vix_contango_on"] is None and got["rate_shock_on"] is None


def test_values_are_personal_and_every_verdict_is_open() -> None:
    by_name = {f.name: f for f in c.FEATURES}
    personal = (
        "vix", "vix3m", "vix9d", "vix6m", "vvix", "vix_obs_date", "vix_pct_252",
        "vix_median_252", "vix_high_20", "vix_chg_5d", "backwardation_run", "vvix_pct_252",
        "realised_corr_ratio_21",
    )  # fmt: skip
    for name in personal:
        assert by_name[name].licence == "personal", name
    open_ = [n for n in by_name if n not in personal]
    assert {"short_premium_allowed", "rate_shock_on", "y10_chg_63d", "sessions_to_fomc"} <= set(
        open_
    )
    assert all(by_name[n].licence == "open" for n in open_)
    assert set(c.COLUMNS) == set(by_name)


def test_the_headline_regime_does_not_read_the_leaf() -> None:
    from algotrade.features.rollups.market import regime  # noqa: PLC0415

    tables = {i.table for i in regime.GROUP.inputs}
    assert c.GROUP.table not in tables and c.GROUP.key == "market_conditions@v2"
    assert regime.GROUP.key == "regime@v3"


def test_the_index_is_read_for_the_vix_date_never_the_sessions_own() -> None:
    cheap_today = pd.concat(
        [trend_row(rv=0.12), trend_row(rv=0.40, day=END)]
    )  # a crash day: S only
    got = run(macro(vix=20), **{TREND: cheap_today})
    assert got["index_vrp_cheap_on"] is False and got["index_vrp_rich_on"] is True
    only_today = trend_row(rv=0.40, day=END)
    assert run(macro(vix=20), **{TREND: only_today})["index_vrp_cheap_on"] is None


def test_the_corr_ratio_uses_the_index_vol_over_the_members_vol() -> None:
    from algotrade.features.rollups.market.edges import dispersion  # noqa: PLC0415

    days = sessions_ending(END, dispersion.CLOSES)
    closes = [100.0 * (1.0 + 0.01 * ((-1) ** i)) for i in range(dispersion.CLOSES)]
    bars = pd.DataFrame(
        [{"instrument_id": f"S{k}", "session_date": d, "open": p, "high": p, "low": p,
          "close": p, "volume": 1.0} for k in range(60) for d, p in zip(days, closes, strict=True)]
    )  # fmt: skip
    universe = pd.DataFrame([{"instrument_id": f"S{k}", "asset_class": "STOCK"} for k in range(60)])
    ref = pd.DataFrame({"instrument_id": universe["instrument_id"], "in_sp500": True})
    members = dispersion.mean_member_vol(universe, ref, bars, END, 50)
    inputs = {
        c.BARS: bars,
        c.UNIVERSE: universe,
        c.REFERENCE: ref,
        TREND: trend_row(rv=members / 2, day=END),
    }
    got = run(macro(), **inputs)
    assert got["realised_corr_ratio_21"] == pytest.approx(0.5, rel=1e-3)
    assert run(macro())["realised_corr_ratio_21"] is None  # no bars, no universe
