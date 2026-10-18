"""``analyst_status``: the history a comparison reads (never a later session, one vendor and kind),
the window of an earlier snapshot, and the two fitness tests that keep the windows working: the
slack covers a refresh window, the lookback covers the longest stale age plus the longest window."""

import tomllib
from datetime import date, timedelta

import pandas as pd

from algotrade.config.site.settings import SourcesSettings
from algotrade.core.time.calendar import sessions_ending
from algotrade.features.rollups.consensus import analyst_status as st
from algotrade.features.rollups.consensus.analyst_ratings import CHANGE_DAYS, RatingsParams
from algotrade.features.rollups.consensus.analyst_revisions import WINDOWS
from algotrade.features.rollups.consensus.analyst_status import AnalystParams
from tests.conftest import REPO_ROOT


def frame(rows: list[tuple[str, str, str, date]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"instrument_id": i, "source": src, "kind": kind, "session_date": day, "period": "p"}
            for i, src, kind, day in rows
        ]
    )


def test_history_rows_are_one_vendors_kind_up_to_the_session_and_never_a_later_one() -> None:
    snapshots = frame(
        [
            ("EQ:A", "fmp", "estimates_annual", date(2027, 1, 8)),
            ("EQ:A", "fmp", "estimates_annual", date(2027, 1, 15)),
            ("EQ:A", "fmp", "estimates_annual", date(2027, 1, 18)),  # a later session
            ("EQ:A", "fmp", "price_target", date(2027, 1, 15)),  # another kind
            ("EQ:A", "finnhub", "estimates_annual", date(2027, 1, 15)),  # another vendor
        ]
    )
    got = st.history_rows(snapshots, "estimates_annual", "fmp", date(2027, 1, 15))
    assert list(got["session_date"]) == [date(2027, 1, 8), date(2027, 1, 15)]
    assert set(st.NEEDED) <= set(got.columns)
    assert st.history_rows(None, "estimates_annual", "fmp", date(2027, 1, 15)).empty


def test_the_window_of_an_earlier_snapshot_is_counted_from_each_names_anchor() -> None:
    anchor = pd.Series(pd.to_datetime(["2027-01-15", "2027-01-01"]))
    first, last = st.days_back(anchor, 90)
    assert list(last) == list(pd.to_datetime(["2026-10-17", "2026-10-03"]))
    assert list(last - first) == [timedelta(days=st.SNAPSHOT_SLACK)] * 2


def test_the_snapshot_slack_covers_a_refresh_window_of_each_vendor() -> None:
    """Otherwise raising ``refresh_days`` would silently leave a gap no snapshot can fill, and
    every window would read null."""
    shipped = SourcesSettings.from_document(
        tomllib.loads((REPO_ROOT / "config/site/sources.toml").read_text())
    )
    for settings in (shipped, SourcesSettings()):
        assert settings.fmp_refresh_days <= st.SNAPSHOT_SLACK
        assert settings.finnhub_refresh_days <= st.SNAPSHOT_SLACK


def test_the_history_lookback_reaches_the_longest_window_from_the_longest_stale_age() -> None:
    """A snapshot stale_days old (the code's and the configured values) is still served; the one
    90 days before it, plus the slack, must be read in the holiday-heaviest stretch as well."""
    configured = tomllib.loads((REPO_ROOT / "config/site/rollups.toml").read_text())
    reach = max(
        AnalystParams().stale_days,
        RatingsParams().stale_days,
        *(v["stale_days"] for k, v in configured.items() if k.startswith("analyst_")),
    )
    days = reach + max(CHANGE_DAYS, *WINDOWS) + st.SNAPSHOT_SLACK
    for session in (date(2027, 1, 15), date(2027, 2, 26), date(2026, 12, 31), date(2027, 7, 9)):
        oldest = sessions_ending(session, st.HISTORY_LOOKBACK + 1)[0]
        assert oldest <= session - timedelta(days=days), session
