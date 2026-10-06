"""``config/site/regime/cards.toml`` (ADR 0047): the shipped cards load in file order with their
feature names, and every rule names the file and the card."""

from copy import deepcopy
from typing import Any

import pytest

from algotrade.config.site.regime.cards import RegimeCards, load_cards
from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.configs.files import FileConfigStore, MemoryConfigStore
from tests.conftest import REPO_ROOT

CARD: dict[str, Any] = {
    "key": "curve",
    "technical_name": "10y minus 3m (T10Y3M)",
    "pace": "slow",
    "feature": "market.regime_indicators@v1.curve",
    "plain_name": "Are long rates below short ones?",
    "one_liner": "The 10-year yield minus the 3-month yield.",
    "why_it_matters": "Inversions precede recessions.",
    "what_on_means": "On when below zero.",
    "lead_time": "6 to 18 months.",
    "false_alarms": "1998 and 2022.",
    "links": [{"title": "FRED T10Y3M", "url": "https://fred.stlouisfed.org/series/T10Y3M"}],
    "before": {"2008": "Inverted in 2006."},
}


def load(*cards: dict[str, Any]) -> RegimeCards:
    return RegimeCards.from_document({"card": list(cards)})


def changed(**kw: Any) -> dict[str, Any]:
    return {**deepcopy(CARD), **kw}


def test_the_shipped_cards_load() -> None:
    cards = load_cards(FileConfigStore(REPO_ROOT / "config")).cards
    assert [c.key for c in cards][:2] == ["curve_10y3m", "hy_oas"]
    assert {c.pace for c in cards} == {"slow", "fast"}
    assert all(c.feature == f"market.regime_indicators@v1.{c.key}" for c in cards)
    assert all(c.links and all(link.url.startswith("https://") for link in c.links) for c in cards)
    assert list(cards[0].before) == ["2008", "2020", "2022"]


def test_a_card_is_typed_and_a_missing_file_has_no_cards() -> None:
    [card] = load(CARD).cards
    assert card.links[0].title == "FRED T10Y3M" and card.before == {"2008": "Inverted in 2006."}
    assert load_cards(MemoryConfigStore({})) == RegimeCards()


@pytest.mark.parametrize(
    ("cards", "message"),
    [
        ([CARD, CARD], r"keys declared more than once: \['curve'\]"),
        ([CARD, changed(key="other")], r"features declared more than once"),
        ([changed(one_liner="  ")], r"\[\[card\]\]\[0\] one_liner: expected a non-empty string"),
        ([changed(why_it_matters="")], r"why_it_matters: expected a non-empty string"),
        ([{k: v for k, v in CARD.items() if k != "feature"}], r"feature: required"),
        ([changed(pace="medium")], r"pace: expected one of \['slow', 'fast'\]"),
        ([changed(links=[])], r"links: expected a non-empty list"),
        (
            [changed(links=[{"title": "x", "url": "http://fred.stlouisfed.org/s"}])],
            r"links\[0\] url: expected an https URL",
        ),
        ([changed(links=[{"title": "x", "url": "https://"}])], r"expected an https URL"),
        (
            [changed(links=[{"title": "", "url": "https://a.org/x"}])],
            r"title: expected a non-empty",
        ),
        ([changed(before={"2008": ""})], r"\[before\] 2008"),
        ([changed(before="none")], r"before: expected a table"),
        ([changed(colour="red")], r"unknown keys \['colour'\]"),
    ],
)
def test_bad_cards_fail_naming_the_card(cards: list[dict[str, Any]], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        load(*cards)


def test_the_document_shape_is_checked() -> None:
    with pytest.raises(ConfigurationError, match="card: expected a list of tables"):
        RegimeCards.from_document({"card": "x"})
    with pytest.raises(ConfigurationError, match="unknown keys"):
        RegimeCards.from_document({"cards": []})
    with pytest.raises(ConfigurationError, match="looks like a secret"):
        RegimeCards.from_document({"card": [changed(api_key="x")]})
