"""``universe``: who an edge trades in words, read from its rules as written."""

from algotrade.core.model.predicates import Rule
from algotrade.services.read.context import StoreContext
from algotrade.services.read.guide.edges.site_edges import site_edges
from algotrade.services.read.guide.edges.universe import Universe, universe_text


def test_a_universe_in_words() -> None:
    rules = (
        Rule("instrument.security_type", "in", ("COMMON_STOCK", "ADR")),
        Rule("rollup.price_stats@v2.adv_usd_20d", "gte", 50_000_000),
        Rule("rollup.price_stats@v2.close", "gt", 5),
    )
    assert universe_text(Universe(rules, "liquid_common_stocks")) == (
        "Common stocks and ADRs, trading at least $50M a day and priced above $5"
    )


def test_a_hand_list_names_its_symbols_and_counts_the_rest() -> None:
    names = tuple(f"S{i}" for i in range(10))
    text = universe_text(Universe((Rule("instrument.symbol", "in", names),), None))
    assert text == "10 listed symbols: S0, S1, S2, S3, S4, S5, S6, S7 and 2 more"


def test_a_preset_without_rules_is_named() -> None:
    assert universe_text(Universe((), "bdc_listed")) == "Bdc listed"
    assert universe_text(Universe((), None)) == "Every instrument in the snapshot"


def test_every_site_edge_has_a_universe_sentence(site: StoreContext) -> None:
    for e in site_edges(site):
        assert universe_text(e.universe).strip(), e.edge.id
