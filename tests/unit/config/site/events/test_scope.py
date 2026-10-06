"""``config/site/events/scope.toml`` (ADR 0050): the shipped scope list loads with the owner's
names, symbols are spelled as the vendors do and declared once, and every rule names the entry."""

from datetime import UTC, date, datetime
from typing import Any

import pytest

from algotrade.config.site.events.scope import EventScope, load_event_scope
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
