"""``config/site/events/releases.toml`` (ADR 0050): the shipped registry loads the nine releases
with their verified FRED ids and the two ISM rules, and every rule names the entry."""

from datetime import date
from typing import Any

import pytest

from algotrade.config.site.events.releases import MacroReleases, load_macro_releases
from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.configs.files import FileConfigStore, MemoryConfigStore
from tests.conftest import REPO_ROOT

CPI: dict[str, Any] = {
    "key": "CPI",
    "name": "Consumer Price Index",
    "source": "fred",
    "release_id": 10,
    "time_et": "08:30",
    "terms": "FRED",
}
ISM: dict[str, Any] = {
    "key": "ISM_MFG",
    "name": "ISM Manufacturing",
    "source": "rule",
    "nth_business_day": 1,
    "time_et": "10:00",
    "terms": "a rule",
}


FOMC: dict[str, Any] = {
    "key": "FOMC",
    "name": "FOMC Press Release",
    "source": "dates",
    "dates": [date(2026, 1, 28), date(2026, 3, 18)],
    "time_et": "14:00",
    "terms": "the Fed calendar",
}


def load(*releases: dict[str, Any]) -> MacroReleases:
    return MacroReleases.from_document({"release": list(releases)})


def test_the_shipped_registry_loads_the_ten_releases() -> None:
    found = load_macro_releases(FileConfigStore(REPO_ROOT / "config"))
    assert found.keys == (
        "CPI", "EMPLOYMENT", "PCE", "GDP", "PPI", "RETAIL_SALES", "ISM_MFG", "ISM_SERVICES", "FOMC",
        "FOMC_UNSCHEDULED",
    )  # fmt: skip
    ids = {r.key: r.release_id for r in found.fred}
    assert ids == {"CPI": 10, "EMPLOYMENT": 50, "PCE": 54, "GDP": 53, "PPI": 46, "RETAIL_SALES": 9}
    fomc = next(r for r in found.releases if r.key == "FOMC")
    assert fomc.source == "dates" and fomc.release_id is None and len(fomc.dates) == 26 * 8 - 1
    assert fomc.dates[0] == date(2002, 1, 30) and fomc.dates[-1] == date(2027, 12, 8)
    rules = {r.key: (r.nth_business_day, r.time_et) for r in found.releases if r.source == "rule"}
    assert rules == {"ISM_MFG": (1, "10:00"), "ISM_SERVICES": (3, "10:00")}
    assert fomc.time_et == "14:00"
    assert all(r.terms and r.name for r in found.releases)
    assert [r.instrument_id for r in found.releases][:2] == ["MACRO:CPI", "MACRO:EMPLOYMENT"]


def test_a_missing_file_has_no_releases() -> None:
    assert load_macro_releases(MemoryConfigStore({})).releases == ()


def test_a_release_loads_with_the_keys_its_source_needs() -> None:
    found = load(CPI, ISM)
    assert found.releases[0].release_id == 10 and found.releases[0].nth_business_day is None
    assert found.releases[1].nth_business_day == 1 and found.releases[1].release_id is None
    assert found.releases[1].clock.hour == 10 and [r.key for r in found.fred] == ["CPI"]


def test_ism_exceptions_load_as_month_to_date_and_the_shipped_ones_are_empty() -> None:
    found = load(changed(ISM, exceptions={"2025-01": date(2025, 1, 3)}))
    assert found.releases[0].exceptions == {"2025-01": date(2025, 1, 3)}
    assert load(ISM).releases[0].exceptions == {}
    shipped = load_macro_releases(FileConfigStore(REPO_ROOT / "config"))
    assert all(r.exceptions == {} for r in shipped.releases)  # none verified: see releases.toml


def changed(base: dict[str, Any], **kw: Any) -> dict[str, Any]:
    return {**base, **kw}


def without(base: dict[str, Any], key: str) -> dict[str, Any]:
    return {k: v for k, v in base.items() if k != key}


@pytest.mark.parametrize(
    ("doc", "message"),
    [
        ({"release": "CPI"}, r"release: expected a list of tables"),
        ({"releases": []}, r"unknown key"),
        ({"release": [changed(CPI, feed="x")]}, r"\[\[release\]\]\[0\].*unknown key"),
        ({"release": [without(CPI, "key")]}, r"\[\[release\]\]\[0\] key: required"),
        ({"release": [changed(CPI, key="cpi")]}, r"key: expected .*got 'cpi'"),
        ({"release": [without(CPI, "name")]}, r"\[\[release\]\]\[0\] name: required"),
        ({"release": [without(CPI, "terms")]}, r"terms: required"),
        (
            {"release": [changed(CPI, source="web")]},
            r"CPI source: expected one of \['fred', 'rule', 'dates'\]",
        ),
        ({"release": [changed(CPI, time_et="8:30")]}, r"CPI time_et: expected HH:MM.*'8:30'"),
        ({"release": [changed(CPI, time_et="24:00")]}, r"CPI time_et: expected HH:MM"),
        ({"release": [without(CPI, "release_id")]}, r"CPI release_id: required"),
        ({"release": [changed(CPI, release_id=0)]}, r"CPI release_id: .*integer >= 1"),
        ({"release": [changed(CPI, nth_business_day=1)]}, r"nth_business_day: not used by"),
        ({"release": [without(ISM, "nth_business_day")]}, r"ISM_MFG nth_business_day: required"),
        ({"release": [changed(ISM, nth_business_day=24)]}, r"nth_business_day: expected 1 to 23"),
        ({"release": [changed(ISM, release_id=10)]}, r"ISM_MFG release_id: not used by"),
        (
            {"release": [CPI, changed(CPI, name="again")]},
            r"keys declared more than once: \['CPI'\]",
        ),
        ({"release": [changed(FOMC, dates=[])]}, r"FOMC dates: required, a non-empty list"),
        ({"release": [without(FOMC, "dates")]}, r"FOMC dates: required"),
        (
            {"release": [changed(FOMC, dates=[date(2026, 3, 18), date(2026, 1, 28)])]},
            r"FOMC dates: not sorted",
        ),
        (
            {"release": [changed(FOMC, dates=[date(2026, 1, 28), date(2026, 1, 28)])]},
            r"FOMC dates: repeated \[datetime.date\(2026, 1, 28\)\]",
        ),
        ({"release": [changed(FOMC, dates=["2026-01-28"])]}, r"FOMC dates: expected dates"),
        ({"release": [changed(FOMC, release_id=101)]}, r"FOMC release_id: not used by"),
        ({"release": [changed(CPI, dates=[date(2026, 1, 28)])]}, r"CPI dates: not used by"),
        ({"release": [changed(CPI, api_key="x")]}, r"looks like a secret"),
    ],
)
def test_every_rule_names_the_entry(doc: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        MacroReleases.from_document(doc)


def shipped(key: str) -> Any:
    found = load_macro_releases(FileConfigStore(REPO_ROOT / "config"))
    return next(r for r in found.releases if r.key == key)


def test_fomc_has_eight_scheduled_meetings_a_year_and_a_known_from_before_the_first() -> None:
    """ADR 0088 (D2): scheduled meetings only (2020 lost the cancelled 03-18), and each
    year's declared ``known_from`` is on or before its first meeting, with a source URL."""
    fomc = shipped("FOMC")
    per_year = {y: [d for d in fomc.dates if d.year == y] for y in range(2002, 2028)}
    assert {y: len(ds) for y, ds in per_year.items() if len(ds) != 8} == {2020: 7}
    assert [p.year for p in fomc.publications] == list(range(2002, 2028))
    for p in fomc.publications:
        assert p.known_from <= per_year[p.year][0], p.year
        assert p.source.startswith("https://www.federalreserve.gov/"), p.year


def test_the_unscheduled_fomc_dates_are_kept_apart_from_the_scheduled_ones() -> None:
    fomc, unscheduled = shipped("FOMC"), shipped("FOMC_UNSCHEDULED")
    assert not set(fomc.dates) & set(unscheduled.dates)
    for day in (date(2008, 1, 22), date(2020, 3, 3), date(2020, 3, 15)):
        assert day in unscheduled.dates and day not in fomc.dates
    assert not unscheduled.publications


def year(**kw: Any) -> dict[str, Any]:
    return {
        "year": 2026,
        "known_from": date(2025, 12, 31),
        "source": "https://x",
        "inferred": True,
        **kw,
    }


@pytest.mark.parametrize(
    ("years", "message"),
    [
        (
            [year(known_from=date(2026, 2, 1))],
            r"year 2026: known_from 2026-02-01 is after the first",
        ),
        ([year(year=2025)], r"declared \[2025\] but dates cover \[2026\]"),
        ([year(), year()], r"years must be unique and ascending"),
        ([year(source=" ")], r"source: expected a non-empty string"),
        ([year(inferred="yes")], r"inferred: expected true or false"),
        ([year(known_from="2025-12-31")], r"known_from: expected a date"),
        ([{k: v for k, v in year().items() if k != "source"}], r"source: required"),
    ],
)
def test_a_bad_declared_year_names_the_release(years: list[dict[str, Any]], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        load({**FOMC, "dates": [date(2026, 1, 28)], "year": years})


def test_a_declared_year_loads_and_only_a_dates_release_may_declare_one() -> None:
    found = load({**FOMC, "dates": [date(2026, 1, 28)], "year": [year()]}).releases[0]
    assert found.known_from_by_year == {2026: date(2025, 12, 31)}
    with pytest.raises(ConfigurationError, match=r"year: not used by source = 'rule'"):
        load({**ISM, "year": [year()]})
