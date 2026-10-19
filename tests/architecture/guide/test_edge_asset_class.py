"""A site edge whose universe is a hand-listed symbol set with no ``security_type`` rule declares
its ``asset_class`` (ADR 0051): the Guide cannot tell stocks from funds by a ticker list, and a
type rule added to the universe would change the edge's hash."""

from algotrade.config.edges.document import ASSET_CLASSES
from algotrade.config.edges.loading import load_edges
from algotrade.config.strategy.schema import Selection
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT


def test_a_hand_listed_symbol_universe_declares_its_asset_class() -> None:
    edges = load_edges(FileConfigStore(REPO_ROOT / "config"))
    missing = []
    for e in edges:
        if not isinstance(e.universe, Selection):
            continue
        fields = {r.field for r in e.universe.where.rules()}
        listed = "instrument.symbol" in fields and "instrument.security_type" not in fields
        if listed and e.asset_class not in ASSET_CLASSES:
            missing.append(e.id)
    assert missing == [], f"declare asset_class in the edge documents: {missing}"
