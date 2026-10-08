"""``load_guide_episode``: an episode by its slug (its key) as the config holds it, cause and
notes linked, the indicators whose ``before`` label means it; ``None`` for an unknown slug.
``before_episode``: the one episode whose peak-to-trough years hold the label's year. Then the
fitness tests over the shipped configs: every episode has a page under a unique slug and every
card's ``before`` label means exactly one episode."""

from datetime import date

from algotrade.config.site.regime.cards import load_cards
from algotrade.config.site.regime.episodes import load_episodes
from algotrade.services.read.context import StoreContext
from algotrade.services.read.guide.episode import before_episode, load_guide_episode
from tests.unit.services.read.guide.conftest import ADV, SHIPPED


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
