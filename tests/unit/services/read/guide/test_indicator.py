"""``load_guide_indicator``: a regime card by its key, its explanation without any session
value, the prose linked at catalogue names, each ``before`` line with the slug of the episode it
means, how it is computed with its terms linked, the field it reads and its reading list;
``None`` for an unknown key. Then the fitness tests over the shipped configs: every card has a
page, and every catalogue name the regime prose writes is in the catalogue."""

from collections.abc import Container

from algotrade.config.site.regime.cards import load_cards
from algotrade.config.site.regime.episodes import load_episodes
from algotrade.services.configs import catalog_of
from algotrade.services.read.context import StoreContext
from algotrade.services.read.guide.indicator import load_guide_indicator
from algotrade.services.read.guide.prose import name_tokens
from algotrade.services.read.regime.indicators import IndicatorLink, TextPart
from tests.unit.services.read.guide.conftest import CLOSE, SHIPPED


def test_the_indicator_page(regime: StoreContext) -> None:
    page = load_guide_indicator(regime, "curve")
    assert page is not None
    assert (page.key, page.plain_name, page.technical_name, page.pace) == (
        "curve", "Are long rates below short ones?", "10y minus 3m (T10Y3M)", "slow",
    )  # fmt: skip
    assert page.summary.text == "The 10y minus the 3m."
    assert page.why_it_matters.fields == (CLOSE,)
    assert (page.what_on_means.text, page.lead_time.text, page.track_record.text) == (
        "On below zero.", "6 to 18 months.", "1998.",
    )  # fmt: skip
    assert [(b.label, b.line.text, b.episode) for b in page.before] == [
        ("2008", "Inverted in 2006.", "gfc"),
        ("2011", "Flat.", None),  # two episodes in 2011
        ("1999", "Before any episode.", None),
    ]
    assert page.how == (
        TextPart("The 10-year yield minus the ", None),
        TextPart("3-month bill", "https://fred.stlouisfed.org/series/DGS3MO"),
        TextPart(".", None),
    )
    assert page.feature == "market.regime_indicators@v1.curve_10y3m"
    assert page.sources == (
        IndicatorLink("FRED T10Y3M", "https://fred.stlouisfed.org/series/T10Y3M"),
    )


def test_unknown_keys_are_none(regime: StoreContext) -> None:
    assert load_guide_indicator(regime, "Are long rates below short ones?") is None
    assert load_guide_indicator(regime, "nope") is None


def test_every_shipped_card_has_a_page(site: StoreContext) -> None:
    cards = load_cards(SHIPPED).cards
    assert cards
    for card in cards:
        page = load_guide_indicator(site, card.key)
        assert page is not None and page.feature == card.feature


def test_every_catalogue_name_in_the_regime_prose_is_in_the_catalogue(
    site: StoreContext,
) -> None:
    fields = catalog_of(site.features).fields
    for card in load_cards(SHIPPED).cards:
        texts = [
            card.one_liner, card.why_it_matters, card.what_on_means, card.lead_time,
            card.false_alarms, *card.before.values(),
        ]  # fmt: skip
        _assert_known(texts, fields, f"cards.toml {card.key}")
    for e in load_episodes(SHIPPED).episodes:
        _assert_known([e.cause, e.notes], fields, f"episodes.toml {e.key}")


def _assert_known(texts: list[str], fields: Container[str], where: str) -> None:
    named = {n for text in texts for n in name_tokens(text) if not n[0].isdigit()}
    unknown = sorted(n for n in named if n not in fields)
    assert not unknown, f"config/site/regime/{where} names fields not in the catalogue: {unknown}"
