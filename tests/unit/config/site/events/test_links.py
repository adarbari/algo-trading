"""``config/site/events/links.toml``: the shipped file loads, every key in it is a release of
``releases.toml`` (a typo would be a link that never shows) and every address is https, and the
loader refuses a malformed key or address."""

from typing import Any

import pytest

from algotrade.config.site.events.links import EventLinks, load_event_links
from algotrade.config.site.events.releases import load_macro_releases
from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.configs.files import FileConfigStore, MemoryConfigStore
from tests.conftest import REPO_ROOT


def test_every_configured_macro_key_is_a_known_release_key() -> None:
    configs = FileConfigStore(REPO_ROOT / "config")
    known = set(load_macro_releases(configs).keys)
    configured = set(load_event_links(configs).macro)
    assert configured, "the shipped links.toml has no macro links"
    assert configured <= known, f"links.toml names unknown release keys: {configured - known}"


def test_every_shipped_address_is_a_plain_https_page() -> None:
    macro = load_event_links(FileConfigStore(REPO_ROOT / "config")).macro
    assert all(url.startswith("https://") and " " not in url for url in macro.values())


def test_a_missing_file_has_no_links() -> None:
    assert load_event_links(MemoryConfigStore({})).macro == {}


@pytest.mark.parametrize(
    ("doc", "message"),
    [
        ({"macros": {}}, r"unknown key"),
        ({"macro": ["CPI"]}, r"macro: expected a table"),
        ({"macro": {"cpi": "https://www.bls.gov/cpi/"}}, r"expected .*got 'cpi'"),
        ({"macro": {"CPI": "http://www.bls.gov/cpi/"}}, r"CPI: expected an https URL"),
        ({"macro": {"CPI": "https://user:pw@www.bls.gov/cpi/"}}, r"expected an https URL"),
        ({"macro": {"CPI": "https://www.bls.gov/cpi/?q=1"}}, r"expected an https URL"),
        ({"macro": {"CPI": "javascript:alert(1)"}}, r"expected an https URL"),
        ({"macro": {"CPI": 3}}, r"expected an https URL"),
    ],
)
def test_a_malformed_document_is_refused(doc: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        EventLinks.from_document(doc)
