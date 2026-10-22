"""Shared Guide prose links against the SITE catalogue only (ADR 0051; ADR 0077 decision 23).

Fix for: every Guide loader linked site prose against the CALLER's catalogue, so a user feature
named like a dotted mention in site prose became a link in an answer cached under a role-wide
key (it leaked that the user has such a feature and gave every other viewer of the role a dead
link). The shared Guide answers must be byte-equal for any two users."""

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from algotrade.config.user import SITE_USER, UserContext
from algotrade.data import StoreReader
from algotrade.services.read.context import StoreContext, open_stores
from algotrade.services.read.guide.edges.index import load_guide_edge_index
from algotrade.services.read.guide.edges.mechanism import load_guide_mechanism
from algotrade.services.read.guide.index import load_guide_index
from algotrade.services.read.guide.situation import load_guide_situation
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import FileConfigStore, MemoryConfigStore
from tests.conftest import REPO_ROOT
from tests.unit.services.read.guide.conftest import DOCUMENTS, GUIDE

MINE = {
    "own_ratio": {
        "expr": "price_stats.close",
        "dtype": "float",
        "unit": "usd",
        "description": "d",
        "null_meaning": "n",
    }
}
OWN = "feature.own_ratio"


def _documents() -> Mapping[tuple[str, str, str], Mapping[str, Any]]:
    guide = deepcopy(GUIDE)
    guide["situation"][0]["signs"] = f"Few trades; compare {OWN} here."
    return {
        **DOCUMENTS,
        ("site", "field_guide", "liquidity"): guide,
        ("trader", "features", "mine"): MINE,
    }


def _open(documents: Mapping[tuple[str, str, str], Mapping[str, Any]], user: str) -> StoreContext:
    return open_stores(
        StoreReader(MemoryBackend()), MemoryConfigStore(documents), UserContext(user)
    )


def test_a_user_feature_named_in_site_prose_is_not_a_link() -> None:
    trader = _open(_documents(), "trader")
    assert trader.features.feature(OWN) is not None  # the trader does have it
    page = load_guide_situation(trader, "thin-name")
    assert page is not None
    assert OWN in page.signs.text and page.signs.fields == ()


def test_two_users_with_different_features_get_equal_shared_guide_answers() -> None:
    shipped = FileConfigStore(REPO_ROOT / "config")
    own = {("trader", "features", "mine"): MINE}

    class Plus:
        """The shipped store plus one user's feature file."""

        def load(self, scope: str, kind: str, name: str) -> Any:
            return own.get((scope, kind, name)) or shipped.load(scope, kind, name)

        def names(self, scope: str, kind: str) -> list[str]:
            return (
                ["mine"] if (scope, kind) == ("trader", "features") else shipped.names(scope, kind)
            )

        def __getattr__(self, name: str) -> Any:
            return getattr(shipped, name)

    def answers(user: str) -> list[str]:
        ctx = open_stores(StoreReader(MemoryBackend()), Plus(), UserContext(user))  # type: ignore[arg-type]
        index = load_guide_edge_index(ctx)
        mechanism = load_guide_mechanism(ctx, index.mechanisms[0].id) if index.mechanisms else None
        return [repr(load_guide_index(ctx)), repr(index), repr(mechanism)]

    assert answers("trader") == answers("other") == answers(SITE_USER)
