"""``load_guide_index``: sections in the file's order with their entry counts, theme groups
with guided-field counts, intents by field count, situations with the fields they fool, the
playbooks by family; the regime indicators and episodes as the shipped config holds them."""

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.read.context import StoreContext, open_stores
from algotrade.services.read.guide.index import (
    GuideIntent,
    GuidePlaybook,
    GuideSituationEntry,
    GuideTheme,
    load_guide_index,
)
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT
from tests.unit.services.read.guide.conftest import stores


def test_the_index_counts_what_the_guide_holds(ctx: StoreContext) -> None:
    index = load_guide_index(ctx)
    assert [(s.id, s.entries) for s in index.sections] == [
        ("fields", 2), ("playbooks", 2), ("glossary", 0),
    ]  # fmt: skip
    assert index.sections[0].title == "Fields" and index.sections[0].purpose == "Every field."
    tradeable, chart = index.theme_groups
    assert tradeable.themes == (GuideTheme("liquidity", 1), GuideTheme("volume", 0))
    assert chart.themes == (GuideTheme("momentum and trend", 1),)
    # "liquid": two fields; each other intent one; ties A-Z.
    assert index.intents == (GuideIntent("liquid", 2), GuideIntent("very liquid", 1))
    assert index.situations == (GuideSituationEntry("thin name", 2, "thin-name"),
                                GuideSituationEntry("takeover", 1, "takeover"))  # fmt: skip
    (trend,) = index.families
    assert (trend.id, trend.title, trend.playbooks) == (
        "trend",
        "Trend",
        (GuidePlaybook("alpha", "Alpha"),),
    )
    assert index.indicators == () and index.episodes == ()  # no regime files here


def test_an_empty_store_has_an_empty_index() -> None:
    index = load_guide_index(stores({}))
    assert (index.sections, index.theme_groups, index.intents, index.families) == ((), (), (), ())


def test_the_shipped_index() -> None:
    configs = FileConfigStore(REPO_ROOT / "config")
    shipped = open_stores(StoreReader(MemoryBackend()), configs, UserContext("local"))
    index = load_guide_index(shipped)
    counts = {s.id: s.entries for s in index.sections}
    assert counts["regime"] == len(index.indicators) + len(index.episodes) > 0
    assert counts["playbooks"] == sum(len(f.playbooks) for f in index.families)
    assert counts["playbooks"] == len(configs.names("site", "screeners"))
    assert index.indicators[0].key == "curve_10y3m" and index.indicators[0].plain_name
    assert all(e.key and e.name for e in index.episodes)
    assert [i.fields for i in index.intents] == sorted(
        (i.fields for i in index.intents), reverse=True
    )
