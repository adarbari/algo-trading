"""The ``macro-calendar`` task over the recorded FRED payload (ADR 0050): one row per release
date with its release moment in UTC, ``status`` by the session, ``known_from`` per row (the
session for a scheduled date, the release date for a past one), the ISM rules around month
starts and holidays, a rerun that writes nothing, and a release that turns ``released``
keeping its ``known_from``."""

from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from itertools import count
from typing import Any

import pandas as pd
import pytest

from algotrade.config.site.events.releases import MacroReleases
from algotrade.data.events import ALL_TIME, read_events
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_ingestion.tasks.macro.calendar import (
    TABLE,
    ingest_macro_calendar,
    moved_rows,
    release_moment,
    release_rows,
    rows_to_write,
    rule_dates,
)
from algotrade_sources.framework.http import HttpError
from algotrade_sources.vendors.fred.releases import FredReleaseDates
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import FIXED, http_for, task_ctx

PAYLOAD = (
    REPO_ROOT / "tests" / "fixtures" / "sources" / "fred" / "release_dates_10_cpi.json"
).read_bytes()
EMPTY = b'{"count":0,"offset":0,"limit":10000,"release_dates":[]}'
S1, S2 = date(2026, 10, 6), date(2026, 10, 15)


LISTED = [date(2026, 1, 28), date(2026, 3, 18), date(2026, 9, 16), date(2026, 10, 28)]


def entry(key: str, **kw: Any) -> dict[str, Any]:
    base = {"key": key, "name": key.title(), "source": "fred", "release_id": 10}
    doc = {**base, "time_et": "08:30", "terms": "t", **kw}
    return {k: v for k, v in doc.items() if not (k == "release_id" and doc["source"] == "dates")}


def rule(key: str, nth: int) -> dict[str, Any]:
    doc = entry(key, source="rule", nth_business_day=nth, time_et="10:00")
    return {k: v for k, v in doc.items() if k != "release_id"}


REGISTRY = MacroReleases.from_document(
    {
        "release": [
            entry("CPI"),
            {**entry("FOMC", source="dates", time_et="14:00"), "dates": LISTED},
            rule("ISM_MFG", 1),
            rule("ISM_SERVICES", 3),
        ]
    }
)
CPI, FOMC, MFG, SERVICES = REGISTRY.releases


class Feed:
    """FRED answers by release id; a request log."""

    def __init__(self, bodies: dict[str, bytes] | None = None) -> None:
        self.bodies = bodies or {"10": PAYLOAD, "101": PAYLOAD}
        self.urls: list[str] = []

    def transport(self, url: str) -> bytes:
        self.urls.append(url)
        for release_id, body in self.bodies.items():
            if f"release_id={release_id}&" in url:
                return body
        raise HttpError(400, body=b"")


def context(feed: Feed, fred: bool = True) -> TaskContext:
    sources: dict[str, Any] = {}
    if fred:
        sources["fred_release_dates"] = FredReleaseDates(http_for(feed.transport))
    ticks = count()  # every run gets its own run id, as real runs do
    ctx = task_ctx(
        StoreWriter(MemoryBackend()),
        sources=sources,
        clock=lambda: FIXED + timedelta(seconds=next(ticks)),
    )
    ctx.unavailable = {} if fred else {"fred_release_dates": "ALGOTRADE_FRED_API_KEY is not set"}
    return ctx


def stored(ctx: TaskContext, key: str, through: date | None = None) -> pd.DataFrame:
    frame = read_events(ctx.reader, TABLE, *ALL_TIME, [f"MACRO:{key}"], through=through).frame
    return frame.assign(ts=pd.to_datetime(frame["ts"], utc=True)).reset_index(drop=True)


# ----------------------------------------------------------------------------- the ISM rules


def test_the_first_business_day_skips_weekends_and_holidays() -> None:
    days = rule_dates(MFG, date(2026, 1, 1), date(2026, 12, 31))
    assert [d.isoformat() for d in days] == [
        "2026-01-02",  # Jan 1 is a holiday (a Thursday)
        "2026-02-02",
        "2026-03-02",
        "2026-04-01",
        "2026-05-01",
        "2026-06-01",
        "2026-07-01",
        "2026-08-03",  # Aug 1 is a Saturday
        "2026-09-01",
        "2026-10-01",
        "2026-11-02",  # Nov 1 is a Sunday
        "2026-12-01",
    ]


def test_the_third_business_day_counts_exchange_sessions() -> None:
    days = rule_dates(SERVICES, date(2026, 6, 1), date(2026, 11, 30))
    assert [d.isoformat() for d in days] == [
        "2026-06-03",
        "2026-07-06",  # Jul 3 is the observed holiday: 1st, 2nd, then Monday the 6th
        "2026-08-05",  # Aug 3, 4, 5
        "2026-09-03",  # Sep 1, 2, 3
        "2026-10-05",  # Oct 1, 2, then Monday the 5th
        "2026-11-04",  # Nov 2, 3, 4
    ]


def test_a_rule_date_outside_the_window_is_dropped_and_year_ends_roll_over() -> None:
    days = rule_dates(MFG, date(2026, 12, 2), date(2027, 1, 4))
    assert days == [date(2027, 1, 4)]  # Dec 1 is before the window; Jan 1 holiday, Jan 2-3 weekend


def test_the_release_moment_follows_new_york_summer_and_winter_time() -> None:
    assert release_moment(date(2026, 10, 14), time(8, 30)) == datetime(
        2026, 10, 14, 12, 30, tzinfo=UTC
    )
    assert release_moment(date(2026, 11, 10), time(8, 30)) == datetime(
        2026, 11, 10, 13, 30, tzinfo=UTC
    )
    assert release_moment(date(2026, 3, 18), time(14, 0)) == datetime(
        2026, 3, 18, 18, 0, tzinfo=UTC
    )


# ----------------------------------------------------------------------------- the rows


def test_rows_say_status_by_the_session_and_known_from_the_earlier_date() -> None:
    rows = release_rows(CPI, [date(2026, 9, 11), S1, date(2026, 10, 14)], S1)
    assert list(rows["release_date"]) == [date(2026, 9, 11), S1, date(2026, 10, 14)]
    assert list(rows["status"]) == ["released", "released", "scheduled"]  # on the session: out
    assert list(rows["known_from"]) == [date(2026, 9, 11), S1, S1]
    assert set(rows["instrument_id"]) == {"MACRO:CPI"} and set(rows["time_et"]) == {"08:30"}
    assert rows["ts"].iloc[2] == pd.Timestamp("2026-10-14 12:30", tz="UTC")


def test_rows_to_write_versions_a_turned_date_by_its_own_known_from_and_never_downgrades() -> None:
    held = release_rows(CPI, [date(2026, 10, 14), date(2026, 11, 10)], S1)
    held.loc[1, "status"] = "released"  # stored as released already
    target = release_rows(CPI, [date(2026, 10, 14), date(2026, 11, 10), date(2026, 12, 10)], S2)
    target.loc[1, "status"] = "scheduled"  # an older session would say so: not a downgrade
    out = rows_to_write(target, held)
    assert list(out["release_date"]) == [date(2026, 10, 14), date(2026, 12, 10)]
    assert list(out["status"]) == ["released", "scheduled"]
    assert list(out["known_from"]) == [date(2026, 10, 14), S2]  # released from its own date


def test_a_changed_name_keeps_the_stored_known_from() -> None:
    held = release_rows(CPI, [date(2026, 11, 10)], S1)
    target = release_rows(CPI, [date(2026, 11, 10)], S2).assign(release_name="CPI (renamed)")
    out = rows_to_write(target, held)
    assert list(out["release_name"]) == ["CPI (renamed)"] and list(out["known_from"]) == [S1]


def test_a_moved_date_listed_again_is_written_again() -> None:
    held = release_rows(CPI, [date(2026, 11, 10)], S1).assign(status="moved")
    out = rows_to_write(release_rows(CPI, [date(2026, 11, 10)], S2), held)
    assert list(out["status"]) == ["scheduled"] and list(out["known_from"]) == [S2]


def test_moved_rows_cover_only_stored_scheduled_dates_inside_the_window() -> None:
    window = (date(2026, 1, 1), date(2026, 12, 31))
    held = release_rows(CPI, [date(2025, 12, 10), date(2026, 11, 10), date(2026, 12, 10)], S1)
    held.loc[2, "status"] = "released"  # (a released date is final)
    out = moved_rows(held, [date(2026, 11, 12)], window, S2)
    assert list(out["release_date"]) == [date(2026, 11, 10)]  # 2025-12-10 is outside the window
    assert list(out["status"]) == ["moved"] and list(out["known_from"]) == [S2]
    assert moved_rows(held, [date(2026, 11, 10)], window, S2).empty
    assert moved_rows(held.iloc[0:0], [S1], window, S2).empty


def test_nothing_new_writes_nothing() -> None:
    held = release_rows(CPI, [S1 + timedelta(8)], S1)
    assert rows_to_write(held, held).empty
    assert rows_to_write(held.iloc[0:0], held).empty


# ----------------------------------------------------------------------------- the task


def test_the_task_stores_fred_dates_and_computed_ism_rows() -> None:
    feed = Feed()
    ctx = context(feed)
    record = ingest_macro_calendar(ctx, REGISTRY, S1)
    assert record.status is RunStatus.COMPLETE
    assert record.items["CPI"] == "OK: 15 rows" and record.items["FOMC"] == "OK: 4 rows"
    assert record.items["ISM_MFG"].startswith("OK:") and record.items["ISM_SERVICES"].startswith(
        "OK:"
    )
    assert len(feed.urls) == 1  # one request per fred release; rules and dates fetch nothing
    assert "release_id=10&" in feed.urls[0] and "realtime_start=2025-09-01" in feed.urls[0]
    assert "realtime_end=2027-11-10" in feed.urls[0]  # 400 days ahead
    cpi = stored(ctx, "CPI")
    assert len(cpi) == 15 and set(cpi["source"]) == {"fred"}
    assert dict(cpi["status"].value_counts()) == {"released": 12, "scheduled": 3}
    future = cpi[cpi["status"] == "scheduled"]
    assert list(future["release_date"]) == [
        date(2026, 10, 14),
        date(2026, 11, 10),
        date(2026, 12, 10),
    ]
    assert list(future["known_from"]) == [S1] * 3  # knowable on the session that fetched them
    assert list(future["ts"].dt.strftime("%H:%M")) == ["12:30", "13:30", "13:30"]
    past = cpi[cpi["status"] == "released"]
    assert list(past["known_from"]) == list(past["release_date"])  # a past row: its own date


def test_the_ism_rows_are_computed_with_their_own_source_and_time() -> None:
    ctx = context(Feed())
    ingest_macro_calendar(ctx, REGISTRY, S1)
    mfg = stored(ctx, "ISM_MFG")
    assert set(mfg["source"]) == {"rule"} and set(mfg["time_et"]) == {"10:00"}
    assert date(2026, 11, 2) in set(mfg["release_date"]) and date(2026, 10, 1) in set(
        mfg["release_date"]
    )
    assert min(mfg["release_date"]) >= S1 - timedelta(400) and max(
        mfg["release_date"]
    ) <= S1 + timedelta(400)
    nov = mfg[mfg["release_date"] == date(2026, 11, 2)].iloc[0]
    assert nov["status"] == "scheduled" and nov["known_from"] == S1
    assert nov["ts"] == pd.Timestamp("2026-11-02 15:00", tz="UTC")  # 10:00 EST
    assert list(stored(ctx, "ISM_SERVICES", through=date(2025, 12, 31))["release_date"]) == [
        date(2025, 9, 4),  # Labor Day, Sep 1, is no session
        date(2025, 10, 3),
        date(2025, 11, 5),
        date(2025, 12, 3),
    ]  # past rows are known on their own date: visible to a session back then


def test_a_rerun_on_an_unchanged_calendar_writes_nothing() -> None:
    ctx = context(Feed())
    ingest_macro_calendar(ctx, REGISTRY, S1)
    again = ingest_macro_calendar(ctx, REGISTRY, S1)
    assert set(again.items.values()) == {"UNCHANGED"} and again.stats["rows"] == 0


def test_a_later_run_turns_a_date_released_as_a_version_known_from_its_date() -> None:
    ctx = context(Feed())
    ingest_macro_calendar(ctx, REGISTRY, S1)
    later = ingest_macro_calendar(ctx, REGISTRY, S2, only=["CPI"])
    assert later.items == {
        "CPI": "OK: 1 rows"
    }  # the 2026-10-14 date; the window moved nothing else
    release = date(2026, 10, 14)
    cpi = stored(ctx, "CPI").set_index("release_date")
    assert cpi.loc[release, "status"] == "released" and cpi.loc[release, "known_from"] == release
    assert cpi.loc[date(2026, 11, 10), "status"] == "scheduled" and len(cpi) == 15
    # a session before the release date still reads it scheduled; from the date on, released
    for session, status in ((S1, "scheduled"), (date(2026, 10, 13), "scheduled"),
                            (release, "released"), (S2, "released")):  # fmt: skip
        known = stored(ctx, "CPI", through=session).set_index("release_date")
        assert known.loc[release, "status"] == status, session


def test_a_date_fred_moves_is_a_new_row_and_the_old_one_is_marked_moved() -> None:
    feed = Feed({"10": PAYLOAD, "101": PAYLOAD})
    ctx = context(feed)
    ingest_macro_calendar(ctx, REGISTRY, S1, only=["CPI"])
    feed.bodies["10"] = PAYLOAD.replace(b"2026-11-10", b"2026-11-12")
    later = date(2026, 10, 7)
    record = ingest_macro_calendar(ctx, REGISTRY, later, only=["CPI"])
    assert record.items["CPI"] == "OK: 2 rows"  # the new date and the old one's moved version
    before = stored(ctx, "CPI", through=S1).set_index("release_date")
    assert (
        date(2026, 11, 12) not in before.index
        and before.loc[date(2026, 11, 10), "status"] == "scheduled"
    )
    after = stored(ctx, "CPI", through=later).set_index("release_date")
    assert after.loc[date(2026, 11, 10), "status"] == "moved"
    assert after.loc[date(2026, 11, 12), "status"] == "scheduled"
    assert after.loc[date(2026, 11, 10), "known_from"] == later
    again = ingest_macro_calendar(ctx, REGISTRY, later, only=["CPI"])
    assert again.items["CPI"] == "UNCHANGED"  # the moved version is not rewritten


def test_a_fetch_that_returns_nothing_marks_nothing_moved() -> None:
    feed = Feed()
    ctx = context(feed)
    ingest_macro_calendar(ctx, REGISTRY, S1, only=["CPI"])
    feed.bodies["10"] = EMPTY
    record = ingest_macro_calendar(ctx, REGISTRY, S2, only=["CPI"])
    assert record.items["CPI"] == "NO_DATA"
    assert "moved" not in set(stored(ctx, "CPI")["status"])


def test_a_registry_exception_replaces_the_rule_date_and_a_later_run_moves_the_old_one() -> None:
    window = (date(2025, 1, 1), date(2025, 3, 31))
    assert rule_dates(MFG, *window)[0] == date(2025, 1, 2)
    shifted = replace(MFG, exceptions={"2025-01": date(2025, 1, 3)})
    assert rule_dates(shifted, *window) == [date(2025, 1, 3), date(2025, 2, 3), date(2025, 3, 3)]
    ctx = context(Feed())
    ingest_macro_calendar(ctx, REGISTRY, date(2024, 12, 30), only=["ISM_MFG"])
    registry = MacroReleases((CPI, FOMC, shifted, SERVICES))
    record = ingest_macro_calendar(ctx, registry, date(2025, 1, 6), only=["ISM_MFG"])
    assert record.items["ISM_MFG"].startswith("OK:")
    jan = stored(ctx, "ISM_MFG").set_index("release_date")
    assert jan.loc[date(2025, 1, 2), "status"] == "moved"
    assert jan.loc[date(2025, 1, 3), "status"] == "released"


def test_without_fred_the_rules_still_run_and_the_fred_releases_are_skipped() -> None:
    ctx = context(Feed(), fred=False)
    record = ingest_macro_calendar(ctx, REGISTRY, S1)
    assert record.status is RunStatus.COMPLETE
    assert record.items["CPI"].startswith("SKIPPED: ALGOTRADE_FRED_API_KEY")
    assert record.items["ISM_MFG"].startswith("OK:")
    assert set(record.stats["skipped_releases"]) == {"CPI"}  # FOMC lists its dates: no fetch
    assert stored(ctx, "CPI").empty and not stored(ctx, "ISM_MFG").empty


def test_a_release_fred_has_no_dates_for_is_no_data() -> None:
    ctx = context(Feed({"10": EMPTY, "101": PAYLOAD}))
    record = ingest_macro_calendar(ctx, REGISTRY, S1)
    assert record.items["CPI"] == "NO_DATA" and record.items["FOMC"].startswith("OK:")


def test_a_failed_request_fails_that_release_only() -> None:
    ctx = context(Feed({"101": PAYLOAD}))
    record = ingest_macro_calendar(ctx, REGISTRY, S1)
    assert record.items["CPI"].startswith("FETCH_ERROR") and record.items["FOMC"].startswith("OK:")


def test_an_unknown_release_key_is_refused() -> None:
    with pytest.raises(KeyError, match="NOPE"):
        ingest_macro_calendar(context(Feed()), REGISTRY, S1, only=["NOPE"])


def test_a_dates_release_writes_exactly_the_listed_rows_without_a_fetch() -> None:
    feed = Feed()
    ctx = context(feed)
    record = ingest_macro_calendar(ctx, REGISTRY, S1, only=["FOMC"])
    assert record.items["FOMC"] == "OK: 4 rows" and feed.urls == []
    fomc = stored(ctx, "FOMC")
    assert list(fomc["release_date"]) == LISTED and set(fomc["source"]) == {"registry"}
    assert list(fomc["status"]) == ["released"] * 3 + ["scheduled"]
    assert list(fomc["ts"].dt.strftime("%H:%M")) == ["19:00", "18:00", "18:00", "18:00"]
    again = ingest_macro_calendar(ctx, REGISTRY, S1, only=["FOMC"])
    assert again.items["FOMC"] == "UNCHANGED"


def test_a_stored_fomc_row_not_in_the_list_is_retired_as_moved_from_the_run_session() -> None:
    ctx = context(Feed())
    old = replace(FOMC, source="fred", release_id=101, dates=())
    ingest_macro_calendar(ctx, MacroReleases((CPI, old, MFG, SERVICES)), S1, only=["FOMC"])
    daily = stored(ctx, "FOMC")
    assert len(daily) == 15 and set(daily["status"]) == {"released", "scheduled"}
    record = ingest_macro_calendar(ctx, REGISTRY, S2, only=["FOMC"])
    assert record.items["FOMC"].startswith("OK:")
    now = stored(ctx, "FOMC")
    by_date = now.set_index("release_date")
    stray = by_date[~by_date.index.isin(LISTED)]
    assert len(stray) > 0 and set(stray["status"]) == {"moved"}
    assert set(stray["known_from"]) == {S2}
    assert set(by_date.loc[by_date.index.isin(LISTED), "status"]) <= {"released", "scheduled"}
    before = stored(ctx, "FOMC", through=S1)  # a session before the fix still reads the rows
    assert "moved" not in set(before["status"])
    assert set(daily["release_date"]) <= set(before["release_date"])
    assert ingest_macro_calendar(ctx, REGISTRY, S2, only=["FOMC"]).items["FOMC"] == "UNCHANGED"
