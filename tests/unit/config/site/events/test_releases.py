"""``config/site/events/releases.toml`` (ADR 0050): the shipped registry loads the nine releases
with their verified FRED ids and the two ISM rules, and every rule names the entry."""

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


def load(*releases: dict[str, Any]) -> MacroReleases:
    return MacroReleases.from_document({"release": list(releases)})


def test_the_shipped_registry_loads_the_nine_releases() -> None:
    found = load_macro_releases(FileConfigStore(REPO_ROOT / "config"))
    assert found.keys == (
        "CPI", "EMPLOYMENT", "PCE", "GDP", "PPI", "RETAIL_SALES", "ISM_MFG", "ISM_SERVICES", "FOMC",
    )  # fmt: skip
    ids = {r.key: r.release_id for r in found.fred}
    assert ids == {
        "CPI": 10, "EMPLOYMENT": 50, "PCE": 54, "GDP": 53, "PPI": 46,
        "RETAIL_SALES": 9, "FOMC": 101,
    }  # fmt: skip
    rules = {r.key: (r.nth_business_day, r.time_et) for r in found.releases if r.source == "rule"}
    assert rules == {"ISM_MFG": (1, "10:00"), "ISM_SERVICES": (3, "10:00")}
    assert {r.key: r.time_et for r in found.fred}["FOMC"] == "14:00"
    assert all(r.terms and r.name for r in found.releases)
    assert [r.instrument_id for r in found.releases][:2] == ["MACRO:CPI", "MACRO:EMPLOYMENT"]


def test_a_missing_file_has_no_releases() -> None:
    assert load_macro_releases(MemoryConfigStore({})).releases == ()


def test_a_release_loads_with_the_keys_its_source_needs() -> None:
    found = load(CPI, ISM)
    assert found.releases[0].release_id == 10 and found.releases[0].nth_business_day is None
    assert found.releases[1].nth_business_day == 1 and found.releases[1].release_id is None
    assert found.releases[1].clock.hour == 10 and [r.key for r in found.fred] == ["CPI"]


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
            r"CPI source: expected one of \['fred', 'rule'\]",
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
        ({"release": [changed(CPI, api_key="x")]}, r"looks like a secret"),
    ],
)
def test_every_rule_names_the_entry(doc: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        MacroReleases.from_document(doc)
