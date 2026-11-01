"""``market_triggers@v1``: the VIX spike by hand over VIX / VIX3M series. A stale reading is
null (never 'no spike', never an older spike), the first high day after 21 quiet sessions is the
spike and a long high stretch is one spike, a spike needs 21 sessions of history, it is known
from the session after its close, and nothing after the session is read."""

from collections.abc import Mapping
from datetime import date

import pandas as pd

from algotrade.core.time.calendar import next_session, sessions_ending
from algotrade.features.rollups.market.edges import triggers
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


# ---------------------------------------------------------------- post-spike contango (v2)
LONG = sessions_ending(END, 400)[:-1]
SPIKE, RECOVERED = (40.0, 30.0), (28.0, 32.0)  # VIX / VIX3M: backwardation, then contango 30% off


def episode(first: int) -> dict[int, tuple[float, float]]:
    """A spike (5 sessions in backwardation) at ``first`` and the recovery from ``first + 5``."""
    return {**{first + k: SPIKE for k in range(5)}, first + 5: RECOVERED}


def test_post_spike_contango_is_the_first_recovered_session_known_the_day_after() -> None:
    got = row(series(episode(330) | {336: (15.0, 18.0)}, LONG))
    assert got["post_spike_contango_date"] == next_session(LONG[335])
    assert got["sessions_since_post_spike_contango"] == len(LONG) - 336


def test_a_long_recovery_is_one_trigger_and_a_new_one_needs_21_sessions_off() -> None:
    stay = {330 + k: SPIKE for k in range(5)} | {335 + k: RECOVERED for k in range(30)}
    assert row(series(stay, LONG))["post_spike_contango_date"] == next_session(LONG[335])
    second = {**episode(330), **{336 + k: (15.0, 18.0) for k in range(45)}, **episode(385)}
    assert row(series(second, LONG))["post_spike_contango_date"] == next_session(LONG[390])
    soon = {**episode(330), **{336 + k: (15.0, 18.0) for k in range(15)}, **episode(351)}
    assert row(series(soon, LONG))["post_spike_contango_date"] == next_session(LONG[335])


def test_still_inverted_or_not_far_enough_off_the_high_is_no_trigger() -> None:
    inverted = {330 + k: SPIKE for k in range(5)} | {335: (28.0, 26.0)}
    got = row(series(inverted, LONG))
    assert got["post_spike_contango_date"] is None
    assert got["sessions_since_post_spike_contango"] == triggers.NONE_SEEN
    shallow = {330 + k: SPIKE for k in range(5)} | {335: (35.0, 38.0)}  # only 12% off the high
    assert row(series(shallow, LONG))["post_spike_contango_date"] is None


def test_the_median_window_must_be_complete_so_short_history_has_no_trigger() -> None:
    short = LONG[-200:]
    got = row(series(episode(150), short))
    assert got["post_spike_contango_date"] is None
    assert got["sessions_since_post_spike_contango"] == triggers.NONE_SEEN  # fresh, none seen


def test_a_stale_reading_is_null_for_the_new_columns_too() -> None:
    old = LONG[:-10]
    got = row(series(episode(330), old))
    assert got["post_spike_contango_date"] is None
    assert pd.isna(got["sessions_since_post_spike_contango"])


def test_no_lookahead_for_the_new_trigger() -> None:
    d = next_session(LONG[335])
    assert row(series(episode(330), LONG[:335]), d)["post_spike_contango_date"] is None
    assert row(series(episode(330), LONG[:336]), d)["post_spike_contango_date"] == d


def test_the_vix_spike_columns_do_not_change_with_the_longer_input() -> None:
    both = row(series({130: HIGH}, LONG))  # inside the v1 window (with its 21 sessions of history)
    assert both["vix_spike_date"] == next_session(LONG[130])
    assert row(series({40: HIGH}, LONG))["vix_spike_date"] is None  # older than LOOKBACK


def test_a_post_spike_contango_older_than_the_lookback_is_not_seen() -> None:
    days = sessions_ending(END, 650)[:-1]  # enough history for a trigger 300+ sessions back
    old = row(series(episode(300), days))  # known 344 sessions before END: outside LOOKBACK
    assert old["post_spike_contango_date"] is None
    assert old["sessions_since_post_spike_contango"] == triggers.NONE_SEEN
    seen = row(series(episode(349), days))  # known 295 sessions before END
    assert seen["post_spike_contango_date"] == next_session(days[354])
    assert seen["sessions_since_post_spike_contango"] <= triggers.LOOKBACK
