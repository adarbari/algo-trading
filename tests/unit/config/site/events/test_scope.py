"""``config/site/events/scope.toml`` (ADR 0050): the shipped scope list loads with the owner's
names, symbols are spelled as the vendors do and declared once, and every rule names the entry."""

from datetime import UTC, date, datetime
from typing import Any

import pytest

from algotrade.config.site.events.scope import (
    AdminScope,
    EventScope,
    effective_list,
    load_admin_scope,
    load_event_scope,
)
from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.configs.files import FileConfigStore, MemoryConfigStore
from tests.conftest import REPO_ROOT

NAME: dict[str, Any] = {"symbol": "MU", "added_on": date(2026, 10, 6), "note": "memory"}


def load(*names: dict[str, Any]) -> EventScope:
    return EventScope.from_document({"name": list(names)})


def changed(**kw: Any) -> dict[str, Any]:
    return {**NAME, **kw}


def test_the_shipped_scope_loads() -> None:
    found = load_event_scope(FileConfigStore(REPO_ROOT / "config"))
    assert len(found.names) >= 100
    assert {"MU", "TSLL", "BRK.B", "SOXL", "MSTR"} <= set(found.symbols)
    assert len(set(found.symbols)) == len(found.symbols)
    assert all(n.added_on <= date.today() for n in found.names)  # noqa: DTZ011 - a calendar date


def test_a_missing_file_is_an_empty_scope() -> None:
    assert load_event_scope(MemoryConfigStore({})).symbols == ()


def test_a_name_loads_with_its_note_collapsed() -> None:
    second = {"symbol": "BRK.B", "added_on": date(2026, 1, 2)}
    found = load(changed(note="  DRAM\n  and HBM "), second)
    assert found.symbols == ("MU", "BRK.B")
    assert found.names[0].note == "DRAM and HBM" and found.names[1].note == ""


@pytest.mark.parametrize(
    ("doc", "message"),
    [
        ({"name": "MU"}, r"name: expected a list of tables"),
        ({"names": []}, r"unknown key"),
        ({"name": [changed(ticker="MU")]}, r"\[\[name\]\]\[0\].*unknown key"),
        ({"name": [{"added_on": date(2026, 1, 1)}]}, r"\[\[name\]\]\[0\] symbol: required"),
        ({"name": [changed(symbol="mu")]}, r"symbol: expected a listed ticker.*got 'mu'"),
        ({"name": [changed(symbol="EQ:BBG000C2V3D6")]}, r"symbol: expected a listed ticker"),
        ({"name": [changed(symbol="BRK-B")]}, r"symbol: expected a listed ticker"),
        ({"name": [changed(added_on="2026-10-06")]}, r"added_on: expected a date"),
        ({"name": [changed(added_on=datetime(2026, 10, 6, tzinfo=UTC))]}, r"expected a date"),
        ({"name": [NAME, changed(note="again")]}, r"symbols declared more than once: \['MU'\]"),
        ({"name": [changed(api_key="x")]}, r"looks like a secret"),
    ],
)
def test_every_rule_names_the_entry(doc: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        EventScope.from_document(doc)


AT = datetime(2026, 11, 3, 9, 30, tzinfo=UTC)
CHANGE: dict[str, Any] = {"symbol": "MU", "by": "arvinder", "at": AT, "note": " why\n now "}


def test_the_admin_document_loads_collapses_notes_and_round_trips() -> None:
    other = {"symbol": "BRK.B", "by": "arvinder", "at": AT}
    doc = {"added": [CHANGE], "removed": [other]}
    found = AdminScope.from_document(doc)
    assert [(c.symbol, c.by, c.at, c.note) for c in found.added] == [
        ("MU", "arvinder", AT, "why now")
    ]
    assert [c.symbol for c in found.removed] == ["BRK.B"] and found.removed[0].note == ""
    assert AdminScope.from_document(found.to_document()) == found
    assert load_admin_scope(MemoryConfigStore({("admin", "events", "scope"): doc})) == found


def test_a_missing_admin_document_is_no_change() -> None:
    assert load_admin_scope(MemoryConfigStore({})) == AdminScope()
    assert AdminScope().to_document() == {}


def test_the_admin_file_is_read_from_config_admin(tmp_path: Any) -> None:
    folder = tmp_path / "admin" / "events"
    folder.mkdir(parents=True)
    (folder / "scope.toml").write_text(
        '[[added]]\nsymbol = "MU"\nby = "arvinder"\nat = 2026-11-03T09:30:00Z\n'
    )
    found = load_admin_scope(FileConfigStore(tmp_path))
    assert [(c.symbol, c.at) for c in found.added] == [("MU", AT)]
    assert (tmp_path / "admin").is_dir() and FileConfigStore(tmp_path).users() == []


@pytest.mark.parametrize(
    ("doc", "message"),
    [
        ({"added": "MU"}, r"added: expected a list of tables"),
        ({"adds": []}, r"unknown key"),
        ({"added": [{**CHANGE, "symbol": "mu"}]}, r"\[\[added\]\]\[0\] symbol: expected a listed"),
        ({"added": [{**CHANGE, "by": " "}]}, r"by: required"),
        (
            {"added": [{**CHANGE, "at": datetime(2026, 11, 3)}]},  # noqa: DTZ001 - naive on purpose
            r"at: expected a UTC instant",
        ),
        ({"removed": [{**CHANGE, "at": "2026-11-03"}]}, r"\[\[removed\]\]\[0\] at: expected"),
        ({"added": [CHANGE, CHANGE]}, r"added: symbols declared more than once: \['MU'\]"),
        ({"added": [CHANGE], "removed": [CHANGE]}, r"both added and removed: \['MU'\]"),
        ({"added": [{**CHANGE, "token": "x"}]}, r"looks like a secret"),
    ],
)
def test_every_admin_rule_names_the_entry(doc: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        AdminScope.from_document(doc)


SITE_NAMES = {("site", "events", "scope"): {"name": [
    {"symbol": s, "added_on": date(2026, 10, 6)} for s in ("TSLL", "AAA", "NOPE")
]}}  # fmt: skip


def admin_doc(added: tuple[str, ...] = (), removed: tuple[str, ...] = ()) -> dict[str, Any]:
    def rows(symbols: tuple[str, ...]) -> list[dict[str, Any]]:
        return [{"symbol": s, "by": "arvinder", "at": AT, "note": "why"} for s in symbols]

    return {"added": rows(added), "removed": rows(removed)}


def test_the_effective_list_is_site_plus_added_minus_removed() -> None:
    configs = MemoryConfigStore(
        {**SITE_NAMES, ("admin", "events", "scope"): admin_doc(("CCC",), ("AAA",))}
    )
    found = effective_list(configs)
    assert found.symbols == ("TSLL", "NOPE", "CCC")  # AAA removed, CCC added after the site's
    added = found.names[-1]
    assert (added.source, added.by, added.at, added.note) == ("admin", "arvinder", AT, "why")
    assert found.names[0].source == "site" and found.names[0].by is None
    assert [c.symbol for c in found.removed] == ["AAA"]


def test_an_addition_the_site_lists_stays_a_site_name_and_a_stranger_removal_shows_nothing() -> (
    None
):
    configs = MemoryConfigStore(
        {**SITE_NAMES, ("admin", "events", "scope"): admin_doc(("AAA",), ("QQQ",))}
    )
    found = effective_list(configs)
    assert [(n.symbol, n.source) for n in found.names] == [
        ("TSLL", "site"), ("AAA", "site"), ("NOPE", "site"),
    ]  # fmt: skip
    assert found.removed == ()  # QQQ was never on the site list
