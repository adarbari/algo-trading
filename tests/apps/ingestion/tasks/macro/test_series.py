"""The ``macro`` task over recorded payloads: rows and vintages, the lagged rule, idempotent
reruns, a changed lagged value as a new vintage, and series skipped for a missing credential."""

from datetime import date, timedelta
from itertools import count
from typing import Any

import pandas as pd
import pytest

from algotrade.config.env import config_dir
from algotrade.config.site.macro import MacroSettings
from algotrade.data import StoreReader
from algotrade.data.macro.series import series_as_of, stored_vintages
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import FileConfigStore
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.framework.registry import run_task
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_ingestion.tasks.macro.series import TABLE, ingest_macro, refetch_days
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.vendors.fred.observations import FredObservations, missing_series
from algotrade_sources.vendors.published.csv_series import PublishedSeries
from tests.helpers.ingest_fakes import FIXED, http_for, task_ctx
from tests.helpers.payloads import fred as fred_payloads
from tests.helpers.payloads import published as files

D1, D2, D3 = date(2026, 10, 2), date(2026, 10, 5), date(2026, 10, 6)
FRED_TERMS = "FRED terms of use"


def entry(key: str, **kw: Any) -> dict[str, Any]:
    base = {"key": key, "source": "fred", "kind": "macro", "cadence": "daily", "pit": "lag"}
    return {**base, "terms": FRED_TERMS, "release_lag_days": 1, **kw}


GDP = entry("GDP_REAL", code="GDPC1", cadence="quarterly", pit="alfred", release_lag_days=60)
CURVE = entry("T10Y3M")
SPX = entry(
    "SPX", code="^SPX", source="published", kind="index", release_lag_days=0,
    url="https://stooq.test/q/d/l/?s=^spx&i=d", date_column="Date", value_column="Close",
)  # fmt: skip
REGISTRY = MacroSettings.from_document({"series": [GDP, CURVE, SPX]})


class Feeds:
    """Payloads by FRED series id and published URL fragment; a request log."""

    def __init__(self) -> None:
        self.fred = {"GDPC1": fred_payloads.payload(), "T10Y3M": fred_payloads.CURVE}
        self.urls: list[str] = []
        self.spent = 0  # clock seconds each request takes (a slow source)

    def transport(self, url: str) -> bytes:
        self.urls.append(url)
        if "stooq" in url:
            return files.STOOQ
        for code, body in self.fred.items():
            if f"series_id={code}" in url:
                return body
        raise HttpError(400, body=fred_payloads.UNKNOWN_SERIES)


def context(
    feeds: Feeds,
    fred: bool = True,
) -> TaskContext:
    sources: dict[str, Any] = {
        "published": PublishedSeries(http_for(feeds.transport)),
    }
    if fred:
        policy = RetryPolicy(tries=1, not_found=missing_series)
        sources["fred"] = FredObservations(http_for(feeds.transport, policy))
    ticks = count()  # every run gets its own run id, as real runs do
    clock = lambda: FIXED + timedelta(seconds=next(ticks) * 3 + feeds.spent * len(feeds.urls))  # noqa: E731
    ctx = task_ctx(StoreWriter(MemoryBackend()), sources=sources, clock=clock)
    ctx.unavailable = {} if fred else {"fred": "ALGOTRADE_FRED_API_KEY is not set"}
    return ctx


def table(ctx: TaskContext) -> pd.DataFrame:
    return stored_vintages(StoreReader(ctx.writer._backend))


def rows(frame: pd.DataFrame, key: str) -> list[tuple[Any, ...]]:
    """(obs, vintage, kind, value) of one series, nulls as ``None``."""
    mine = frame[frame["instrument_id"] == f"MACRO:{key}"].sort_values(
        ["obs_date", "vintage_date"], kind="stable"
    )
    return [
        (o, v, k, None if pd.isna(x) else x)
        for o, v, k, x in zip(
            mine["obs_date"], mine["vintage_date"], mine["vintage_kind"], mine["value"],
            strict=True,
        )
    ]  # fmt: skip


def test_a_run_stores_every_series_with_its_vintages() -> None:
    ctx = context(Feeds())
    record = ingest_macro(ctx, REGISTRY, D1)
    assert record.status is RunStatus.COMPLETE
    assert record.items == {
        "GDP_REAL": "OK: 6 rows",
        "T10Y3M": "OK: 3 rows",
        "SPX": "OK: 4 rows",
    }
    frame = table(ctx)
    assert set(frame["vintage_kind"]) == {"alfred", "lagged"}
    # ALFRED rows keep realtime_start; the first vintage's old observation is lagged (+60 days)
    assert rows(frame, "GDP_REAL") == [
        (date(2020, 1, 1), date(2020, 3, 1), "lagged", 18951.9),
        (date(2020, 1, 1), date(2020, 5, 28), "alfred", 18924.3),
        (date(2020, 1, 1), date(2020, 6, 25), "alfred", 18560.0),
        (date(2020, 4, 1), date(2020, 7, 30), "alfred", 17302.5),
        (date(2020, 4, 1), date(2020, 8, 27), "alfred", 17258.2),
        (date(2020, 7, 1), date(2020, 10, 29), "alfred", None),
    ]
    # pit = "lag": obs + 1 day, whatever realtime_start said; "." stays a null
    assert rows(frame, "T10Y3M") == [
        (date(2026, 9, 30), date(2026, 10, 1), "lagged", 0.10),
        (date(2026, 10, 1), date(2026, 10, 2), "lagged", 0.12),
        (date(2026, 10, 2), date(2026, 10, 3), "lagged", None),
    ]
    spx = frame[frame["instrument_id"] == "IDX:SPX"]  # the published file: lag 0, end of night
    assert spx["vintage_date"].tolist() == spx["obs_date"].tolist()
    assert set(spx["series"]) == {"^SPX"} and set(spx["vintage_kind"]) == {"lagged"}
    assert record.stats["vintages"] == {"GDP_REAL": 6, "T10Y3M": 3, "SPX": 4}
    assert record.stats["skipped_series"] == {}
    stored = StoreReader(ctx.writer._backend).table(TABLE, D1)
    assert stored is not None and set(stored["source"]) == {"fred", "published"}


def test_a_session_sees_only_the_vintages_known_by_then() -> None:
    ctx = context(Feeds())
    ingest_macro(ctx, REGISTRY, D1)
    reader = StoreReader(ctx.writer._backend)
    day = series_as_of(reader, ["MACRO:T10Y3M"], date(2026, 10, 2), 5)
    assert day["obs_date"].tolist() == [date(2026, 9, 30), date(2026, 10, 1)]


def test_a_rerun_on_unchanged_data_writes_no_rows() -> None:
    ctx = context(Feeds())
    first = ingest_macro(ctx, REGISTRY, D1)
    before = table(ctx)
    same_day = ingest_macro(ctx, REGISTRY, D1)
    later = ingest_macro(ctx, REGISTRY, D2)  # FRED refetched; the file is due again
    for record in (same_day, later):
        assert record.status is RunStatus.COMPLETE
        assert {k: v for k, v in record.items.items() if k != "SPX"} == {
            "GDP_REAL": "UNCHANGED",
            "T10Y3M": "UNCHANGED",
        }
    assert same_day.items["SPX"] == "NOT_DUE" and later.items["SPX"] == "UNCHANGED"
    pd.testing.assert_frame_equal(table(ctx), before)
    assert StoreReader(ctx.writer._backend).dates(TABLE) == [D1]  # no later partition
    assert later.stats["vintages"] == first.stats["vintages"]


def test_a_changed_lagged_value_is_a_new_vintage_dated_the_run_session() -> None:
    feeds = Feeds()
    ctx = context(feeds)
    ingest_macro(ctx, REGISTRY, D1)
    feeds.fred["T10Y3M"] = fred_payloads.CURVE_REVISED
    record = ingest_macro(ctx, REGISTRY, D2)
    assert record.items["T10Y3M"] == "OK: 1 rows" and record.items["GDP_REAL"] == "UNCHANGED"
    frame = table(ctx)
    assert rows(frame, "T10Y3M")[1:3] == [
        (date(2026, 10, 1), date(2026, 10, 2), "lagged", 0.12),  # the old vintage is kept
        (date(2026, 10, 1), D2, "lagged", 0.13),
    ]
    assert record.stats["vintages"]["T10Y3M"] == 4
    reader = StoreReader(ctx.writer._backend)
    before = series_as_of(reader, ["MACRO:T10Y3M"], date(2026, 10, 3), 5)
    after = series_as_of(reader, ["MACRO:T10Y3M"], D2, 5)
    assert before["value"].dropna().tolist() == [0.10, 0.12]  # a session before the run: old
    assert after["value"].dropna().tolist() == [0.10, 0.13]
    again = ingest_macro(ctx, REGISTRY, D3)
    assert again.items["T10Y3M"] == "UNCHANGED"  # the new vintage is what is stored now


def test_a_missing_credential_skips_its_series_and_counts_them() -> None:
    feeds = Feeds()
    ctx = context(feeds, fred=False)
    record = ingest_macro(ctx, REGISTRY, D1)
    assert record.status is RunStatus.COMPLETE  # a skip is not a failure
    reason = "SKIPPED: ALGOTRADE_FRED_API_KEY is not set"
    assert record.items == {"GDP_REAL": reason, "T10Y3M": reason, "SPX": "OK: 4 rows"}
    assert record.stats["skipped_series"] == {
        "GDP_REAL": "ALGOTRADE_FRED_API_KEY is not set",
        "T10Y3M": "ALGOTRADE_FRED_API_KEY is not set",
    }
    assert record.stats["items"] == {"SKIPPED": 2, "OK": 1}
    assert not any("series_id" in u for u in feeds.urls)
    assert set(table(ctx)["instrument_id"]) == {"IDX:SPX"}


def test_a_source_the_registry_never_built_is_skipped_with_that_reason() -> None:
    ctx = context(Feeds())
    ctx.sources = {k: v for k, v in ctx.sources.items() if k != "published"}
    record = ingest_macro(ctx, REGISTRY, D1)
    assert record.items["SPX"] == "SKIPPED: published is not built"


def test_an_unknown_series_has_no_data_and_a_failed_fetch_makes_the_run_partial() -> None:
    feeds = Feeds()
    del feeds.fred["GDPC1"]  # FRED answers "series does not exist"

    def broken(url: str) -> bytes:
        if "stooq" in url:
            raise HttpError(500)
        return feeds.transport(url)

    ctx = context(feeds)
    ctx.sources["published"] = PublishedSeries(http_for(broken, RetryPolicy(tries=1)))
    record = ingest_macro(ctx, REGISTRY, D1)
    assert record.status is RunStatus.PARTIAL
    assert record.items["GDP_REAL"] == "NO_DATA" and record.items["T10Y3M"].startswith("OK")
    assert record.items["SPX"].startswith("FETCH_ERROR")
    assert record.stats["vintages"]["GDP_REAL"] == 0 or "GDP_REAL" not in record.stats["vintages"]
    assert set(table(ctx)["instrument_id"]) == {"MACRO:T10Y3M"}  # the others still stored


def test_only_picks_keys_and_since_bounds_the_observations() -> None:
    feeds = Feeds()
    ctx = context(feeds)
    record = ingest_macro(ctx, REGISTRY, D1, only=["SPX"], since=date(2026, 9, 30))
    assert list(record.items) == ["SPX"]
    assert table(ctx)["obs_date"].min() == date(2026, 9, 30)  # 09-28 and 09-29 left out
    ingest_macro(ctx, REGISTRY, D1, only=["SPX"])  # an explicit key is fetched, never NOT_DUE
    assert len(table(ctx)) == 4
    with pytest.raises(KeyError, match="NOPE"):
        ingest_macro(ctx, REGISTRY, D1, only=["NOPE"])


def test_since_asks_fred_for_that_window() -> None:
    feeds = Feeds()
    ingest_macro(context(feeds), REGISTRY, D1, only=["T10Y3M"], since=date(1970, 1, 1))
    assert "observation_start=1970-01-01" in feeds.urls[0]


def test_a_published_file_is_refetched_by_cadence_but_at_most_weekly() -> None:
    monthly = MacroSettings.from_document(
        {"series": [{**SPX, "key": "EBP", "cadence": "monthly"}, {**SPX, "cadence": "weekly"}]}
    )
    assert [refetch_days(s) for s in monthly.series] == [7, 7]
    assert refetch_days(REGISTRY.by_key("SPX")) == 1
    ctx = context(Feeds())
    ingest_macro(ctx, REGISTRY, D1, only=["SPX"])
    assert ingest_macro(ctx, REGISTRY, D1).items["SPX"] == "NOT_DUE"
    assert ingest_macro(ctx, REGISTRY, D2).items["SPX"] == "UNCHANGED"


def test_the_registry_entry_runs_the_task_from_the_site_registry() -> None:
    ctx = context(Feeds())
    ctx.configs = FileConfigStore(config_dir())
    record = run_task(
        "macro", ctx, {"session": D1, "only": "SPX,T10Y3M", "since": date(2026, 9, 1)}
    )
    assert set(record.items) == {"SPX", "T10Y3M"} and record.stats["since"] == "2026-09-01"
    assert record.status is RunStatus.COMPLETE


def test_since_never_trims_an_alfred_request_and_drops_the_older_rows_afterwards() -> None:
    """The first vintage dates what ALFRED's archive predates: it is only known from the whole
    history, so a window would make a late release look pre-archive and date it too early."""
    feeds = Feeds()
    ctx = context(feeds)
    ingest_macro(ctx, REGISTRY, D1, only=["GDP_REAL"])
    full = rows(table(ctx), "GDP_REAL")
    ctx = context(feeds)
    record = ingest_macro(ctx, REGISTRY, D1, only=["GDP_REAL"], since=date(2020, 4, 1))
    assert "observation_start" not in feeds.urls[-1]
    assert record.items["GDP_REAL"] == "OK: 3 rows"
    assert rows(table(ctx), "GDP_REAL") == [r for r in full if r[0] >= date(2020, 4, 1)]


def test_a_spent_run_budget_skips_the_rest_and_makes_the_run_partial() -> None:
    feeds = Feeds()
    feeds.spent = 1000  # every request takes 1000 s: the 900 s budget goes with the first
    ctx = context(feeds)
    record = ingest_macro(ctx, REGISTRY, D1)
    assert record.status is RunStatus.PARTIAL
    assert record.items["GDP_REAL"].startswith("OK")
    assert record.items["T10Y3M"] == "SKIPPED: run budget of 900s spent"
    assert record.items["SPX"] == "SKIPPED: run budget of 900s spent"
    assert record.stats["over_budget"] == ["T10Y3M", "SPX"]
    assert record.stats["skipped_series"] == {}  # fetchable: check_macro still grades them
    assert len(feeds.urls) == 1
    assert set(table(ctx)["instrument_id"]) == {"MACRO:GDP_REAL"}


def test_the_budget_is_a_typed_macro_setting() -> None:
    assert REGISTRY.run_budget_s == 900
    tight = MacroSettings.from_document({"macro": {"run_budget_s": 60}, "series": [CURVE]})
    assert tight.run_budget_s == 60
    with pytest.raises(Exception, match="run_budget_s"):
        MacroSettings.from_document({"macro": {"run_budget_s": 0}})
