"""``attribution.toml``: the headline cap, the default without the file, bad values named."""

import pytest

from algotrade.config.site.events.attribution import AttributionSettings, load_attribution
from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.configs.files import FileConfigStore, MemoryConfigStore
from tests.conftest import REPO_ROOT


def _configs(doc: dict[str, object] | None) -> MemoryConfigStore:
    return MemoryConfigStore({} if doc is None else {("site", "events", "attribution"): doc})


def test_no_file_or_no_store_is_the_default_cap() -> None:
    assert load_attribution(_configs(None)) == AttributionSettings(news_per_night=40)
    assert load_attribution(None).news_per_night == 40


def test_the_file_sets_the_cap_and_zero_turns_the_headlines_off() -> None:
    assert load_attribution(_configs({"news_per_night": 12})).news_per_night == 12
    assert load_attribution(_configs({"news_per_night": 0})).news_per_night == 0


@pytest.mark.parametrize("doc", [{"news_per_night": -1}, {"news_per_night": "many"}, {"cap": 3}])
def test_a_wrong_value_or_key_is_a_configuration_error(doc: dict[str, object]) -> None:
    with pytest.raises(ConfigurationError):
        load_attribution(_configs(doc))


def test_the_committed_file_loads() -> None:
    assert load_attribution(FileConfigStore(REPO_ROOT / "config")).news_per_night == 40
