"""``config/site/field_guide/*.toml`` (ADR 0041 amended): entries and situations in file
order, each use a criterion the rule grammar takes (op, value, mode, tolerance, on_miss),
errors naming the entry; the shipped files load and guide every entry fully."""

from typing import Any

import pytest

from algotrade.config.site.field_guide import FieldGuideSettings, GuideUse, Situation
from algotrade.config.site.settings import load_field_guide
from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.configs.files import FileConfigStore, MemoryConfigStore
from tests.conftest import REPO_ROOT

ENTRY: dict[str, Any] = {
    "name": "rollup.a@v1.rsi",
    "theme": "momentum",
    "reads": " 0 to  100 ",
    "caveats": ["pinned  by a deal"],
    "sources": ["Wilder (1978)"],
    "use": [
        {"for": "oversold", "op": "lt", "value": 30, "mode": "soft", "tolerance": 5, "note": " x "},
        {"for": "strength", "op": "gte", "value": 50, "mode": "score", "tolerance": 20},
        {"for": "known", "op": "not_null"},
        {
            "for": "liquid",
            "op": "gte",
            "value": 1e6,
            "mode": "soft",
            "tolerance": {"relative": 0.2},
            "on_miss": "LIQUIDITY_RISK",
        },
    ],
}


def test_entries_and_situations_in_file_order() -> None:
    guide = FieldGuideSettings.from_document(
        {
            "field": [ENTRY, {"name": "feature.b", "theme": "t", "reads": "r"}],
            "situation": [
                {"name": "deal", "signs": " a  b ", "affects": ["feature.b"], "do": "drop"}
            ],
        }
    )
    first, second = guide.fields
    assert first.name == "rollup.a@v1.rsi" and first.reads == "0 to 100"
    assert first.caveats == ("pinned by a deal",) and first.sources == ("Wilder (1978)",)
    assert first.uses == (
        GuideUse("oversold", "lt", 30, "soft", 5.0, "", "x"),
        GuideUse("strength", "gte", 50, "score", 20.0),
        GuideUse("known", "not_null", None, "hard"),
        GuideUse("liquid", "gte", 1e6, "soft", {"relative": 0.2}, "LIQUIDITY_RISK"),
    )
    assert second.uses == () and second.caveats == () and second.sources == ()
    assert guide.situations == (Situation("deal", "a b", ("feature.b",), "drop"),)
    assert guide.entry("feature.b") is second and guide.entry("feature.c") is None
    assert FieldGuideSettings.from_document(None) == FieldGuideSettings()
    assert load_field_guide(MemoryConfigStore({})) == FieldGuideSettings()


def _with_use(**use: Any) -> dict[str, Any]:
    return {"field": [{**ENTRY, "use": [{"for": "x", "op": "gt", "value": 1, **use}]}]}


@pytest.mark.parametrize(
    ("doc", "message"),
    [
        ({"field": {"name": "x"}}, r"expected a list of tables"),
        ({"field": [{"theme": "t", "reads": "r"}]}, r"\[\[field\]\]\[0\] name"),
        ({"field": [{"name": "a", "reads": "r"}]}, r"\[\[field\]\]\[0\] theme"),
        ({"field": [{"name": "a", "theme": "t"}]}, r"\[\[field\]\]\[0\] reads"),
        (
            {"field": [{"name": "a", "theme": "t", "reads": "r", "caveats": [""]}]},
            r"caveats: expected",
        ),
        ({"field": [{"name": "a", "theme": "t", "reads": "r", "bands": []}]}, r"unknown keys"),
        ({"field": [ENTRY, ENTRY]}, r"guided twice"),
        (_with_use(op="like"), r"\[\[use\]\]\[0\] op"),
        ({"field": [{**ENTRY, "use": [{"for": "x", "op": "gt"}]}]}, r"value: expected a value"),
        (
            {"field": [{**ENTRY, "use": [{"for": "x", "op": "is_null", "value": 1}]}]},
            r"is_null takes none",
        ),
        (_with_use(mode="maybe"), r"mode"),
        (_with_use(mode="soft"), r"a soft criterion needs one"),
        (_with_use(mode="hard", tolerance=1), r"a hard criterion takes none"),
        (_with_use(mode="soft", tolerance=-1), r"tolerance: expected a number >= 0"),
        (_with_use(mode="soft", tolerance=True), r"tolerance: expected a number"),
        (_with_use(mode="soft", tolerance={"absolute": 1}), r"unknown keys"),
        (_with_use(mode="score", tolerance=1, on_miss="WATCH"), r"on_miss: soft criteria only"),
        (_with_use(mode="soft", tolerance=1, on_miss="PANIC"), r"on_miss"),
        ({"field": [{**ENTRY, "use": [{"op": "gt", "value": 1}]}]}, r"\[\[use\]\]\[0\] for"),
        ({"situation": [{"name": "s", "signs": "x", "do": "y"}]}, r"affects: expected"),
        (
            {"situation": [{"name": "s", "signs": "x", "affects": ["a"]}]},
            r"\[\[situation\]\]\[0\] do",
        ),
        ({"guide": []}, r"unknown keys"),
    ],
)
def test_errors_name_the_entry(doc: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        FieldGuideSettings.from_document(doc)


def test_a_situations_slug_is_its_name_kebab_cased_and_unique() -> None:
    def situation(name: str) -> dict[str, object]:
        return {"name": name, "signs": "x", "affects": ["feature.b"], "do": "y"}

    one = FieldGuideSettings.from_document({"situation": [situation("Recent listing, spin-off")]})
    assert one.situations[0].slug == "recent-listing-spin-off"
    clash = {"situation": [situation("a null"), situation("A null!")]}
    with pytest.raises(ConfigurationError, match=r"share a slug: \['a-null'\]"):
        FieldGuideSettings.from_document(clash)


def test_files_load_in_name_order_and_a_field_is_guided_once() -> None:
    store = MemoryConfigStore(
        {
            ("site", "field_guide", "b"): {
                "field": [{"name": "feature.b", "theme": "t", "reads": "r"}]
            },
            ("site", "field_guide", "a"): {
                "situation": [{"name": "s", "signs": "x", "affects": ["feature.b"], "do": "y"}]
            },
            ("alice", "field_guide", "c"): {
                "field": [{"name": "feature.c", "theme": "t", "reads": "r"}]
            },
        }
    )
    guide = load_field_guide(store)
    assert [f.name for f in guide.fields] == ["feature.b"] and [
        s.name for s in guide.situations
    ] == ["s"]
    twice = {"a": {"field": [ENTRY]}, "b": {"field": [ENTRY]}}
    with pytest.raises(ConfigurationError, match="guided twice"):
        FieldGuideSettings.from_documents(twice)
    with pytest.raises(ConfigurationError, match=r"field_guide/b\.toml \[\[field\]\]\[0\] theme"):
        FieldGuideSettings.from_documents({"b": {"field": [{"name": "x", "reads": "r"}]}})


def test_the_guide_is_read_once_per_store(monkeypatch: pytest.MonkeyPatch) -> None:
    # Every Guide read and help button loads it: parsing it per request held the GIL 0.12 s.
    store = MemoryConfigStore({("site", "field_guide", "a"): {"field": [ENTRY]}})
    loads: list[str] = []
    load = store.load
    monkeypatch.setattr(store, "load", lambda *key: loads.append(key[2]) or load(*key))
    first = load_field_guide(store)
    assert load_field_guide(store) is first and loads == ["a"]
    assert load_field_guide(MemoryConfigStore({})) == FieldGuideSettings()  # another store


def test_the_shipped_guide_is_complete() -> None:
    store = FileConfigStore(REPO_ROOT / "config")
    assert store.names("site", "field_guide") == [
        "events",
        "fundamentals",
        "instrument",
        "levels",
        "liquidity",
        "momentum",
        "options-chain",
        "options-wing",
        "situations",
        "trend",
        "volatility",
        "volume",
    ]
    assert store.load("alice", "field_guide", "momentum") is None  # site-only
    guide = load_field_guide(store)
    assert len(guide.fields) >= 30 and len(guide.situations) >= 5
    for e in guide.fields:
        assert e.uses and e.caveats and e.sources, (
            f"{e.name}: every entry has uses, caveats and sources"
        )
        assert all(u.note or u.mode == "hard" or u.tolerance is not None for u in e.uses)
    assert any(s.name == "pending takeover" for s in guide.situations)
