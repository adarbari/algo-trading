from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext
from algotrade.services.read.screens.screeners import Screener, load_screener, load_screeners
from tests.unit.services.read.screens.conftest import context


def test_one_screener_per_id_the_users_own_config_first(ctx: ReadContext) -> None:
    found = {s.id: s for s in load_screeners(ctx)}
    assert list(found) == ["alpha", "beta", "gamma"]
    assert (found["alpha"].owner, found["alpha"].scope, found["alpha"].name) == (
        "site", "site", "Alpha"
    )  # fmt: skip
    beta = found["beta"]  # me's own beta wins over the site preset of the same id
    assert (beta.owner, beta.scope, beta.name, beta.version) == ("me", "me", "My beta", 2)
    assert found["gamma"].name == "gamma"  # no name: the id
    assert beta.hash


def test_another_user_sees_the_presets(reader: StoreReader) -> None:
    others = load_screeners(context(reader, user="you"))
    assert [(s.id, s.owner) for s in others] == [("alpha", "site"), ("beta", "site")]


def test_only_rule_screens_that_resolve(reader: StoreReader) -> None:
    docs = {
        ("site", "strategies", "trend"): {"id": "trend", "kind": "strategy", "impl": "sma"},
        ("me", "screeners", "broken@1"): {"id": "broken", "kind": "screener", "impl": "rules"},
    }
    ctx = context(reader, docs)
    assert [s.id for s in load_screeners(ctx)] == ["alpha", "beta", "gamma"]
    assert load_screener(ctx, "trend") is None
    assert load_screener(ctx, "broken") is None
    assert load_screener(ctx, "nope") is None
    assert isinstance(load_screener(ctx, "alpha"), Screener)
