"""``PORTFOLIO_FIELDS`` (ADR 0088, G15): each names a Guide term that exists, the catalogue offers
them to a gate, entry and case rule only, an option-only field is not offered to a share book, and
the computed producers ``LEVELS`` names resolve to a module (the R-1 providers check)."""

import importlib.util

import pytest

from algotrade.config.edges.positions.templates import load_templates
from algotrade.config.site.guide.glossary import load_guide_glossary
from algotrade.config.strategy.catalog import FieldCatalog
from algotrade.config.strategy.levels import CASE, ENTRY, EXIT, GATE, LEVELS, SCREENER, UNIVERSE
from algotrade.config.strategy.portfolio_fields import PORTFOLIO_FIELDS, fields_for
from algotrade.config.strategy.schema import parse_group
from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT

SHIPPED = FileConfigStore(REPO_ROOT / "config")
TEMPLATES = load_templates(SHIPPED)


def _catalog(template: str) -> FieldCatalog:
    fields = fields_for(TEMPLATES[template])
    return FieldCatalog.build(
        {}, levels={"portfolio": fields}, licences=dict.fromkeys(fields, "open")
    )


def _rule(field: str) -> object:
    return parse_group({"all": [{"field": field, "op": "lt", "value": 5}]}, "rule")


def test_every_portfolio_field_has_its_guide_term_and_each_term_a_field() -> None:
    terms = {t.id for t in load_guide_glossary(SHIPPED).terms if t.id.startswith("portfolio_")}
    assert {f.guide for f in PORTFOLIO_FIELDS} == terms
    assert len({f.name for f in PORTFOLIO_FIELDS}) == len(PORTFOLIO_FIELDS) == 5


def test_an_option_only_field_is_not_offered_to_a_share_book() -> None:
    assert "portfolio.open_collateral" not in fields_for(TEMPLATES["long_shares"])
    assert "portfolio.open_collateral" in fields_for(TEMPLATES["short_put"])


@pytest.mark.parametrize("site", [GATE, ENTRY, CASE])
def test_a_gate_entry_or_case_rule_reads_a_portfolio_field(site: str) -> None:
    _catalog("short_put").check(_rule("portfolio.open_positions"), "rule", site=site)


@pytest.mark.parametrize("site", [SCREENER, UNIVERSE, EXIT])
def test_the_other_sites_refuse_a_portfolio_field(site: str) -> None:
    with pytest.raises(ConfigurationError, match="portfolio"):
        _catalog("short_put").check(_rule("portfolio.open_positions"), "rule", site=site)


def test_every_computed_producer_resolves_to_a_module() -> None:
    for level in LEVELS:
        if level.producer is not None:
            assert importlib.util.find_spec(f"algotrade.{level.producer}"), level.key
