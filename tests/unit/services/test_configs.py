"""``catalog_of``: the shipped catalogue by level (ADR 0088): market fields exist only for the
use sites that read the market level, instrument fields stay what selections see, each field
carries its licence and each declared string domain."""

import pytest

from algotrade.config.strategy.schema import parse_group
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.configs import field_catalog
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT

CATALOG = field_catalog(FileConfigStore(REPO_ROOT / "config"))
MARKET = "market.market_trend@v2.ndx_drawdown_252d"  # open
PERSONAL = "market.market_trend@v2.spx_drawdown_252d"  # an index level under a personal licence
LABEL = "market.market_breadth@v1.breadth_status"


def one(field: str, op: str, value: object) -> object:
    return parse_group({"all": [{"field": field, "op": op, "value": value}]}, "rule")


def test_a_market_field_is_a_gate_field_and_never_a_screener_field() -> None:
    CATALOG.check(one(MARKET, "gt", -0.1), "rule", "gate")  # type: ignore[arg-type]
    with pytest.raises(ConfigurationError, match="market-level field"):
        CATALOG.check(one(MARKET, "gt", -0.1), "rule", "screener")  # type: ignore[arg-type]
    assert MARKET not in CATALOG.fields and CATALOG.levels["market"][MARKET] == "float32"


def test_an_instrument_field_is_not_a_gate_field() -> None:
    with pytest.raises(ConfigurationError, match="instrument-level field"):
        CATALOG.check(one("instrument.sector", "eq", "Tech"), "rule", "gate")  # type: ignore[arg-type]


def test_a_stored_label_has_its_domain_and_every_field_a_licence() -> None:
    assert CATALOG.domains[LABEL] == ("OK", "LOW_COVERAGE", "NO_UNIVERSE")
    CATALOG.check(one(LABEL, "ne", "OK"), "rule", "gate")  # type: ignore[arg-type]
    assert CATALOG.domain_read(LABEL, "BRAND_NEW") is None
    assert set(CATALOG.licences.values()) <= {"open", "personal", "yahoo"}
    assert CATALOG.licences[MARKET] == "open" and CATALOG.licences[PERSONAL] == "personal"


def test_a_personal_market_field_is_no_gate_field_but_an_entry_field() -> None:
    with pytest.raises(ConfigurationError, match="personal-licensed"):
        CATALOG.check(one(PERSONAL, "gt", -0.1), "rule", "gate")  # type: ignore[arg-type]
    CATALOG.check(one(PERSONAL, "gt", -0.1), "rule", "entry")  # type: ignore[arg-type]
