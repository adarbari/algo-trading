"""``load_guide_episode``: an episode by its slug (its key) as the config holds it, cause and
notes linked, the indicators whose ``before`` label means it; ``None`` for an unknown slug.
``before_episode``: the one episode whose peak-to-trough years hold the label's year. Then the
fitness tests over the shipped configs: every episode has a page under a unique slug and every
card's ``before`` label means exactly one episode.

``load_guide_indicator``: a regime card by its key, its explanation without any session
value, the prose linked at catalogue names, each ``before`` line with the slug of the episode it
means, how it is computed with its terms linked, the field it reads and its reading list;
``None`` for an unknown key. Then the fitness tests over the shipped configs: every card has a
page, and every catalogue name the regime prose writes is in the catalogue."""

from collections.abc import Container
from datetime import date

from algotrade.config.site.regime.cards import load_cards
from algotrade.config.site.regime.episodes import load_episodes
from algotrade.services.configs import catalog_of
from algotrade.services.read.context import StoreContext
from algotrade.services.read.guide.prose import name_tokens
from algotrade.services.read.guide.regime import (
    before_episode,
    load_guide_episode,
    load_guide_indicator,
)
from algotrade.services.read.regime.indicators import IndicatorLink, TextPart
from tests.unit.services.read.guide.conftest import ADV, CLOSE, SHIPPED


def test_the_episode_page(regime: StoreContext) -> None:
    page = load_guide_episode(regime, "gfc")
    assert page is not None
    assert (page.slug, page.episode.name, page.episode.kind, page.episode.recession) == (
        "gfc", "Financial crisis", "recession", True,
    )  # fmt: skip
    assert (page.episode.peak, page.episode.trough, page.episode.recovered) == (
        date(2007, 10, 9), date(2009, 3, 9), date(2013, 3, 28),
    )  # fmt: skip
    assert (page.episode.nber_start, page.episode.nber_end) == (date(2007, 12, 1), date(2009, 6, 1))
    assert page.cause.fields == (ADV,) and page.notes.text == "Curve."
    ((indicator),) = page.indicators
    assert (indicator.key, indicator.label, indicator.line.text) == (
        "curve", "2008", "Inverted in 2006.",
    )  # fmt: skip


def test_a_shock_has_no_recession_and_a_shared_year_names_no_indicator(
    regime: StoreContext,
) -> None:
    page = load_guide_episode(regime, "eu")
    assert page is not None
    assert (page.episode.recovered, page.episode.nber_start, page.episode.nber_end) == (
        None,
        None,
        None,
    )
    assert page.indicators == ()  # "2011" is held by two episodes: it means neither


def test_unknown_slugs_are_none(regime: StoreContext) -> None:
    assert load_guide_episode(regime, "Financial crisis") is None  # the name is not the slug
    assert load_guide_episode(regime, "nope") is None


def test_before_episode_needs_exactly_one_episode_and_a_year() -> None:
    episodes = load_episodes(SHIPPED).episodes
    found = before_episode("2008", episodes)
    assert found is not None and found.key == "gfc_2007"
    assert before_episode("1960", episodes) is None
    assert before_episode("late 2008", episodes) is None


def test_every_shipped_episode_has_a_page_under_a_unique_slug(site: StoreContext) -> None:
    episodes = load_episodes(SHIPPED).episodes
    slugs = [e.key for e in episodes]
    assert episodes and len(set(slugs)) == len(slugs)
    for e in episodes:
        page = load_guide_episode(site, e.key)
        assert page is not None and page.slug == e.key and page.episode.name == e.name


def test_every_shipped_before_label_means_exactly_one_episode() -> None:
    episodes = load_episodes(SHIPPED).episodes
    for card in load_cards(SHIPPED).cards:
        unknown = [label for label in card.before if before_episode(label, episodes) is None]
        assert not unknown, (
            f"config/site/regime/cards.toml {card.key} before: {unknown} name no single "
            "episode of episodes.toml (a year inside exactly one episode's peak-to-trough)"
        )


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
