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
from algotrade.services.read.context import ResultCache, StoreContext, open_stores
from algotrade.services.read.guide.edges.edge import load_guide_edge
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


class Patched:
    """The shipped site store with ``OWN`` mentioned in one mechanism text, one edge's thesis
    and one set-aside edge's plain reason, plus the user ``trader``'s feature file."""

    def __init__(self) -> None:
        self._shipped = FileConfigStore(REPO_ROOT / "config")

    def load(self, scope: str, kind: str, name: str) -> Any:
        if (scope, kind, name) == ("trader", "features", "mine"):
            return MINE
        doc = self._shipped.load(scope, kind, name)
        if doc is None or scope != "site":
            return doc
        doc = dict(doc)
        if (kind, name) == ("guide_mechanisms", MECHANISM):
            doc["dont"] = f"Do not trade {OWN} alone."
        if (kind, name) == ("edges", EDGE):
            doc["thesis"] = f"Winners keep winning; see {OWN}."
        if (kind, name) == ("edges", SET_ASIDE):
            doc["plain_reason"] = f"Needs more history than {OWN} has."
        return doc

    def names(self, scope: str, kind: str) -> list[str]:
        if (scope, kind) == ("trader", "features"):
            return ["mine"]
        return self._shipped.names(scope, kind)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._shipped, name)


MECHANISM, EDGE, SET_ASIDE = "forced_flows", "momentum_12_1", "c13_iv_term_structure_straddles"


def _answers(ctx: StoreContext) -> list[str]:
    index = load_guide_edge_index(ctx)
    return [
        repr(load_guide_index(ctx)),
        repr(index),
        repr(load_guide_mechanism(ctx, MECHANISM)),
        repr(load_guide_edge(ctx, EDGE)),
    ]


def test_two_users_with_different_features_share_one_cached_guide_answer() -> None:
    """The role-wide cache holds one answer: ``trader`` (who has ``OWN``) fills it first, ``other``
    reads it back; both equal a fresh compute for the site user, with no ``OWN`` link."""
    reader, store, cache = StoreReader(MemoryBackend()), Patched(), ResultCache()

    def ctx(user: str, cache: ResultCache) -> StoreContext:
        return open_stores(reader, store, UserContext(user), cache)  # type: ignore[arg-type]

    trader = ctx("trader", cache)
    assert trader.features.feature(OWN) is not None
    first = _answers(trader)
    assert _answers(ctx("other", cache)) == first
    assert first == _answers(ctx(SITE_USER, ResultCache()))
    for page in (
        load_guide_mechanism(trader, MECHANISM),
        load_guide_edge(trader, EDGE),
    ):
        assert page is not None
    mechanism = load_guide_mechanism(trader, MECHANISM)
    assert mechanism is not None and OWN in mechanism.dont.text and OWN not in mechanism.dont.fields
    edge = load_guide_edge(trader, EDGE)
    assert edge is not None and OWN in edge.thesis.text and OWN not in edge.thesis.fields
    assert OWN in repr(load_guide_edge_index(trader))  # the plain reason is in the answer ...
    assert f"field='{OWN}'" not in repr(load_guide_edge_index(trader))  # ... unlinked
