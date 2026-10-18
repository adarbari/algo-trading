"""``short_interest@v1``: the latest report public by the session per instrument, with its
settlement date; a report not yet public is never read; no row without one. And
``feature.short_interest_ratio`` over the share count."""

from datetime import date

import pandas as pd

from algotrade.features.rollups.events import short_interest as si
from algotrade.features.site import site_features
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT
from tests.helpers.rollup_store import END

SESSION = date(2026, 10, 2)


def report(iid: str, settled: date, known: date, short: int, dtc: float) -> dict[str, object]:
    return {"instrument_id": iid, "ts": pd.Timestamp(settled, tz="UTC"), "known_from": known,
            "short_position": short, "days_to_cover": dtc}  # fmt: skip


def test_the_latest_public_report_per_instrument_wins() -> None:
    rows = [
        report("EQ:A", date(2026, 8, 31), date(2026, 9, 11), 100, 1.0),
        report("EQ:A", date(2026, 9, 15), date(2026, 9, 25), 150, 1.5),
        report("EQ:A", date(2026, 9, 30), date(2026, 10, 12), 999, 9.9),  # not public yet
        report("EQ:B", date(2026, 9, 15), date(2026, 9, 25), 70, 3.0),
    ]
    out = si.compute({si.EVENTS: pd.DataFrame(rows)}, SESSION, None).set_index("instrument_id")
    assert out.at["EQ:A", "short_position"] == 150 and out.at["EQ:A", "days_to_cover"] == 1.5
    assert out.at["EQ:A", "short_interest_date"] == date(2026, 9, 15)
    assert out.at["EQ:B", "short_position"] == 70


def test_no_report_public_by_the_session_gives_no_row() -> None:
    later = pd.DataFrame([report("EQ:A", date(2026, 9, 30), date(2026, 10, 12), 1, 1.0)])
    assert si.compute({si.EVENTS: later}, SESSION, None).empty
    assert si.compute({si.EVENTS: None}, SESSION, None).empty


def test_the_ratio_is_the_short_position_over_current_shares_and_null_without_them() -> None:
    fs = site_features(FileConfigStore(REPO_ROOT / "config"))
    shorts = pd.DataFrame(
        {"instrument_id": ["EQ:A", "EQ:B", "EQ:C"], "session_date": END,
         "short_position": [10.0, 5.0, 8.0], "days_to_cover": [1.0, 2.0, 3.0],
         "short_interest_date": date(2026, 9, 15)}
    )  # fmt: skip
    funds = pd.DataFrame(
        {"instrument_id": ["EQ:A", "EQ:B"], "session_date": END,
         "shares_outstanding": [100.0, 50.0], "market_cap_status": ["OK", "STALE"]}
    )  # fmt: skip
    out = fs.evaluate(
        {"rollups/instrument/short_interest@v1": shorts,
         "rollups/instrument/fundamentals@v4": funds}, ["short_interest_ratio"],
    )  # fmt: skip
    got = out.set_index("instrument_id")["short_interest_ratio"]
    assert got["EQ:A"] == 0.1
    assert pd.isna(got.get("EQ:B")) and pd.isna(got.get("EQ:C"))  # stale count; no count
