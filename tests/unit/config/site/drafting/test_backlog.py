"""``feature_backlog.toml``: slug and enum checks, unique keys and aliases, ``promoted_to``
exactly when PROMOTED, catalogue names that exist, and the capped prompt list."""

from typing import Any

import pytest

from algotrade.config.site.drafting.backlog import FeatureBacklogSettings, open_keys
from algotrade.config.site.settings import load_feature_backlog
from algotrade.core.model.errors import ConfigurationError
from algotrade.features.site import site_features
from algotrade.storage.configs.files import FileConfigStore, MemoryConfigStore
from tests.conftest import REPO_ROOT
from tests.unit.config.site.test_settings import site


def item(**over: Any) -> dict[str, Any]:
    return {"key": "a_thing", "description": "A thing", "feasibility": "UNCLEAR", **over}


def parse(*items: dict[str, Any]) -> FeatureBacklogSettings:
    return FeatureBacklogSettings.from_document({"item": list(items)})


def test_no_file_is_an_empty_backlog() -> None:
    assert load_feature_backlog(MemoryConfigStore({})).items == ()


def test_the_shipped_file_loads_and_is_sound() -> None:
    settings = FeatureBacklogSettings.from_document(site("feature_backlog"))
    assert load_feature_backlog(FileConfigStore(REPO_ROOT / "config")) == settings
    names = {f.name for f in site_features(FileConfigStore(REPO_ROOT / "config")).features.values()}
    assert [i.key for i in settings.items] == sorted(i.key for i in settings.items)
    for i in settings.items:
        assert set(i.closest) <= names, f"{i.key}: closest names not in the catalogue"
        assert (i.status == "PROMOTED") == bool(i.promoted_to), i.key
        if i.promoted_to:
            assert i.promoted_to in names, f"{i.key}: promoted_to not in the catalogue"
    assert {i.key for i in settings.items} >= {"support_level_history", "free_cash_flow_yield"}


@pytest.mark.parametrize("bad", ["Upper", "has space", "dash-ed", ""])
def test_keys_and_aliases_are_slugs(bad: str) -> None:
    with pytest.raises(ConfigurationError, match=r"slug|non-empty"):
        parse(item(key=bad))
    with pytest.raises(ConfigurationError, match="aliases: expected a slug"):
        parse(item(aliases=[bad or " "]))


def test_enums_and_unknown_keys_are_refused() -> None:
    with pytest.raises(ConfigurationError, match=r"feasibility: expected one of"):
        parse(item(feasibility="EASY"))
    with pytest.raises(ConfigurationError, match=r"status: expected one of"):
        parse(item(status="DONE"))
    with pytest.raises(ConfigurationError, match=r"\[\[item\]\]\[0\]: unknown keys \['note'\]"):
        parse(item(note="x"))
    with pytest.raises(ConfigurationError, match=r"feature_backlog\.toml: unknown keys"):
        FeatureBacklogSettings.from_document({"items": []})


def test_duplicate_keys_and_aliases_are_refused() -> None:
    with pytest.raises(ConfigurationError, match="key appears twice"):
        parse(item(), item())
    with pytest.raises(ConfigurationError, match="alias 'x' of 'b'"):
        parse(item(aliases=["x"]), item(key="b", aliases=["x"]))
    with pytest.raises(ConfigurationError, match="alias 'a_thing' of 'b'"):
        parse(item(), item(key="b", aliases=["a_thing"]))


def test_promoted_to_is_required_exactly_when_promoted() -> None:
    assert parse(item(status="PROMOTED", promoted_to="rsi_14")).items[0].promoted_to == "rsi_14"
    with pytest.raises(ConfigurationError, match="promoted_to: required"):
        parse(item(status="PROMOTED"))
    with pytest.raises(ConfigurationError, match="promoted_to: required"):
        parse(item(status="OPEN", promoted_to="rsi_14"))


def test_open_keys_are_open_only_sorted_and_capped() -> None:
    many = [item(key=f"k{n:03d}", description=f"d{n}") for n in range(70)]
    many += [
        item(key="a_done", status="WONT_DO"),
        item(key="b_built", status="PROMOTED", promoted_to="x"),
    ]
    pairs = open_keys(parse(*reversed(many)))
    assert len(pairs) == 60 and pairs[0] == ("k000", "d0") and pairs == tuple(sorted(pairs))
    assert open_keys(parse(*many), limit=2) == (("k000", "d0"), ("k001", "d1"))
