"""``market_triggers@v1``: the VIX spike by hand over VIX / VIX3M series. A stale reading is
null (never 'no spike', never an older spike), the first high day after 21 quiet sessions is the
spike and a long high stretch is one spike, a spike needs 21 sessions of history, it is known
from the session after its close, and nothing after the session is read."""

from collections.abc import Mapping
from datetime import date

import pandas as pd

from algotrade.core.time.calendar import next_session, sessions_ending
from algotrade.features.rollups.market import triggers
from algotrade.features.rollups.market.observations import as_series

END = date(2026, 10, 2)
DAYS = sessions_ending(END, 80)[:-1]  # observations up to the session before END
CALM = (15.0, 18.0)  # VIX, VIX3M: contango
HIGH = (35.0, 30.0)  # at least 30 and backwardated


def series(readings: Mapping[int, tuple[float, float]], days: list[date] = DAYS) -> dict:
    """VIX / VIX3M by session index of ``days`` (``CALM`` elsewhere)."""
    rows = []
    for i, d in enumerate(days):
        vix, vix3m = readings.get(i, CALM)
        rows += [
            {"instrument_id": triggers.VIX, "obs_date": d, "value": vix},
            {"instrument_id": triggers.VIX3M, "obs_date": d, "value": vix3m},
        ]
    return as_series(pd.DataFrame(rows))


def row(s: dict, session: date = END) -> dict[str, object]:
    return triggers.trigger_row(s, session)


def test_the_spike_is_known_from_the_session_after_its_close() -> None:
    got = row(series({40: HIGH}))
    assert got["vix_spike_date"] == next_session(DAYS[40])
    assert got["vix_spike_level"] == 35.0
    assert (
        got["sessions_since_vix_spike"] == len(DAYS) - 41
    )  # D is index 41; END is index len(DAYS)


def test_a_high_vix_in_contango_is_no_spike() -> None:
    got = row(series({40: (35.0, 40.0)}))
    assert got["vix_spike_date"] is None and pd.isna(got["vix_spike_level"])
    assert got["sessions_since_vix_spike"] == triggers.NONE_SEEN  # fresh, none seen: not null


def test_a_stale_reading_is_null_not_no_spike_and_not_the_old_spike() -> None:
    old = DAYS[:60]  # the newest observation is 20 sessions before END
    assert triggers.vix_stale(series({40: HIGH}, old), END)
    got = row(series({40: HIGH}, old))
    assert got["vix_spike_date"] is None and pd.isna(got["vix_spike_level"])
    fresh = row(series({40: HIGH}, old), next_session(old[-1]))
    assert fresh["vix_spike_date"] == next_session(old[40])  # read in time, it is there


def test_one_stale_leg_is_stale() -> None:
    s = series({40: HIGH})
    s[triggers.VIX3M] = s[triggers.VIX3M].iloc[:-10]
    assert triggers.vix_stale(s, END)
    assert pd.isna(row(s)["sessions_since_vix_spike"])


def test_a_stretch_of_high_days_is_one_spike() -> None:
    got = row(series(dict.fromkeys(range(40, 70), HIGH)))  # 30 high days in a row
    assert got["vix_spike_date"] == next_session(DAYS[40])


def test_a_high_day_after_21_quiet_sessions_is_a_new_spike_after_20_it_is_not() -> None:
    # high day 30, then 21 quiet sessions (31..51), then a high day 52
    assert row(series({30: HIGH, 52: HIGH}))["vix_spike_date"] == next_session(DAYS[52])
    # 20 quiet sessions: the second high day is part of the first spike
    assert row(series({30: HIGH, 51: HIGH}))["vix_spike_date"] == next_session(DAYS[30])


def test_a_spike_needs_21_sessions_of_history() -> None:
    assert row(series({10: HIGH}))["vix_spike_date"] is None
    assert row(series({21: HIGH}))["vix_spike_date"] == next_session(DAYS[21])


def test_no_lookahead_a_later_reading_never_moves_an_earlier_session() -> None:
    d = next_session(DAYS[40])
    early = row(series({40: HIGH}), d)
    late = row(series({40: HIGH, 41: HIGH, 60: HIGH}, DAYS[:41]), d)  # only 0..40 known by D
    assert early["vix_spike_date"] == late["vix_spike_date"] == d
    assert early["sessions_since_vix_spike"] == 0
    # known only through D - 1 sessions' observations: the spike is not yet there
    before = row(series({40: HIGH}, DAYS[:40]), DAYS[40])
    assert before["vix_spike_date"] is None


def test_no_series_at_all_is_null() -> None:
    pure = triggers.compute({triggers.MACRO: None}, END, None)
    assert list(pure["instrument_id"]) == ["MKT:US"]
    assert pure.drop(columns="instrument_id").isna().all(axis=None)
