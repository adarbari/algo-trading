"""The stepped SEC pace keys (``config/site/vendors/sec_pace.py``): defaults from the site file
and the validation of ``[sec_edgar] filing_text_*``."""

import tomllib
from typing import Any

import pytest

from algotrade.config.site.settings import SourcesSettings
from algotrade.core.model.errors import ConfigurationError
from tests.conftest import REPO_ROOT


def _site_sources() -> dict[str, Any]:
    return tomllib.loads((REPO_ROOT / "config" / "site" / "sources.toml").read_text())


def test_filing_text_stepped_pace_defaults_and_validates() -> None:
    settings = SourcesSettings.from_document(_site_sources())
    assert (settings.sec_filing_text_max_rps, settings.sec_filing_text_min_rps) == (8, 5)
    assert settings.sec_filing_text_recover_s == 900.0
    assert settings.sec_filing_text_error_cooldown_s == 30.0
    assert settings.vendor("sec_edgar").min_interval_s == 0.2  # the nightly stays at 5/s
    changed = SourcesSettings.from_document(
        {"sec_edgar": {"filing_text_max_rps": 10, "filing_text_min_rps": 2}}
    )
    assert (changed.sec_filing_text_max_rps, changed.sec_filing_text_min_rps) == (10, 2)


@pytest.mark.parametrize(
    ("section", "message"),
    [
        ({"filing_text_max_rps": 11}, r"filing_text_max_rps: expected <= 10"),
        ({"filing_text_min_rps": 9}, r"filing_text_min_rps: expected <= filing_text_max_rps"),
        ({"filing_text_min_rps": 0}, r"filing_text_min_rps: expected an integer >= 1"),
        ({"filing_text_max_rps": 7.5}, r"filing_text_max_rps: expected an integer"),
        ({"filing_text_recover_s": 0}, r"filing_text_recover_s: expected > 0"),
        ({"filing_text_error_cooldown_s": 0}, r"filing_text_error_cooldown_s: expected > 0"),
        ({"filing_text_recover_s": -1}, r"filing_text_recover_s: expected a number"),
    ],
)
def test_filing_text_stepped_pace_rejects_bad_values(section: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        SourcesSettings.from_document({"sec_edgar": section})
