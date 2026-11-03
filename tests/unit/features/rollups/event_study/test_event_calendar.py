"""``event_calendar@v1`` (the next reaction session of each macro release, per name) and the two
expression features over it: days to the next impact event and impact events before the expiry."""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from algotrade.core.time.calendar import next_session, sessions_to
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.rollups.event_study import event_calendar as ec
from algotrade.features.rollups.event_study.moves import MACRO_KEYS
from algotrade.features.site import site_features
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT
from tests.helpers.stored_frames import stamped

SESSION = date(2026, 10, 2)  # a Friday
A, B = "EQ:A", "EQ:B"


def _release(key: str, day: date, known: date = date(2026, 1, 2), time: str = "08:30"):
    return {"instrument_id": f"MACRO:{key}", "ts": pd.Timestamp(day, tz="UTC"),
            "known_from": known, "release_key": key, "release_name": key, "release_date": day,
            "time_et": time, "status": "scheduled"}  # fmt: skip


def _bars() -> pd.DataFrame:
    return pd.DataFrame(
        [{"instrument_id": i, "session_date": SESSION, "close": 10.0} for i in (A, B)]
    )


def _row(releases: list[dict[str, object]]) -> pd.Series:
    inputs = {"bars/1d": _bars(), ec.MACRO_RELEASE: stamped(releases, SESSION, "m")}
    out = ec.compute(inputs, SESSION, None).set_index("instrument_id")
    row = out.loc[A]
    assert isinstance(row, pd.Series)
    return row


def test_the_next_release_after_the_session_is_the_one_ahead() -> None:
    today, soon, later = SESSION, SESSION + timedelta(days=5), SESSION + timedelta(days=40)
    row = _row([_release("CPI", today), _release("CPI", soon), _release("CPI", later)])
    assert row["cpi_next_date"] == soon  # today's 08:30 release has reacted already
    assert row["cpi_sessions_to"] == sessions_to(SESSION, soon)
    assert pd.isna(row["ppi_next_date"]) and pd.isna(row["ppi_sessions_to"])  # none listed: UNKNOWN


def test_a_release_after_the_close_reacts_on_the_next_session_and_a_late_known_one_is_hidden() -> (
    None
):
    late = _release("GDP", SESSION, time="16:30")  # today after the close: tomorrow's session
    unknown_yet = _release("PCE", SESSION + timedelta(days=9), known=SESSION + timedelta(days=1))
    row = _row([late, unknown_yet])
    assert row["gdp_next_date"] == next_session(SESSION)
    assert pd.isna(row["pce_next_date"])  # not known by the session


@pytest.fixture(scope="module")
def fs() -> FeatureSet:
    return site_features(FileConfigStore(REPO_ROOT / "config"))


def _frames(multiples: dict[str, float | None], status: str = "OK", expiry_days: int = 14):
    day = SESSION
    cal = {f"{k.lower()}_next_date": None for k in MACRO_KEYS}
    cal |= {f"{k.lower()}_sessions_to": np.nan for k in MACRO_KEYS}
    cal["cpi_next_date"], cal["cpi_sessions_to"] = day + timedelta(days=7), 5
    cal["fomc_next_date"], cal["fomc_sessions_to"] = day + timedelta(days=20), 14
    react = {f"macro_{k.lower()}_multiple_median": multiples.get(k) for k in MACRO_KEYS}
    react |= {"reaction_status": status, "earnings_n": 8, "earnings_multiple_median": None}
    frames = {
        "rollups/instrument/event_calendar@v1": {
            "instrument_id": [A],
            **{k: [v] for k, v in cal.items()},
        },
        "rollups/instrument/event_reaction@v1": {
            "instrument_id": [A],
            **{k: [v] for k, v in react.items()},
        },
        "rollups/instrument/earnings@v1": {
            "instrument_id": [A],
            "days_to_earnings": [30],
            "next_earnings_date": [day + timedelta(days=45)],
        },
        "rollups/instrument/nearest_expiry@v1": {
            "instrument_id": [A],
            "expiry_date": [day + timedelta(days=expiry_days)],
        },
    }
    return {
        name: pd.DataFrame(cols).assign(session_date=pd.Timestamp(SESSION))
        for name, cols in frames.items()
    }


def test_the_expressions_count_only_kinds_that_have_moved_the_name(fs: FeatureSet) -> None:
    frames = _frames({"CPI": 2.0, "FOMC": 1.0})  # CPI matters (2.0 >= 1.5), FOMC does not
    out = fs.evaluate(frames, ["days_to_next_impact_event", "impact_events_before_expiry"])
    row = out.set_index("instrument_id").loc[A]
    assert row["days_to_next_impact_event"] == 5
    assert row["impact_events_before_expiry"] == 1  # CPI in 7 days, expiry in 14
    both = fs.evaluate(
        _frames({"CPI": 2.0, "FOMC": 2.0}, expiry_days=30), ["impact_events_before_expiry"]
    )
    assert both.iloc[0]["impact_events_before_expiry"] == 2


def test_no_impact_event_is_null_for_the_days_and_zero_for_the_count(fs: FeatureSet) -> None:
    out = fs.evaluate(
        _frames({"CPI": 0.9, "FOMC": 1.0}),
        ["days_to_next_impact_event", "impact_events_before_expiry"],
    )
    row = out.iloc[0]
    assert pd.isna(row["days_to_next_impact_event"])  # none ahead of a kind that matters
    assert row["impact_events_before_expiry"] == 0
    short = fs.evaluate(
        _frames({"CPI": 2.0}, status="SHORT_HISTORY"),
        ["days_to_next_impact_event", "impact_events_before_expiry"],
    ).iloc[0]
    assert pd.isna(short["days_to_next_impact_event"]) and pd.isna(
        short["impact_events_before_expiry"]
    )
