from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext
from algotrade.services.read.screens.screeners import (
    ScreenColumn,
    ScreenCriterion,
    Screener,
    load_screener,
    load_screeners,
)
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


def test_criteria_and_display_columns_in_spec_order(reader: StoreReader) -> None:
    doc = {
        "id": "cols", "kind": "screener", "impl": "rules", "version": 1,
        "selection": "all_active",
        "criteria": {
            "price": {"field": "rollup.price_stats@v2.close", "op": "gt", "value": 5},
            "adv": {"field": "rollup.price_stats@v2.adv_usd_20d", "op": "gte", "value": 1},
        },
        "columns": {"close": "rollup.price_stats@v2.close"},
    }  # fmt: skip
    found = load_screener(context(reader, {("me", "screeners", "cols@1"): doc}), "cols")
    assert found is not None
    assert found.criteria == (
        ScreenCriterion("price", "rollup.price_stats@v2.close", "hard", "gt", 5),
        ScreenCriterion("adv", "rollup.price_stats@v2.adv_usd_20d", "hard", "gte", 1),
    )
    assert found.display_columns == (ScreenColumn("close", "rollup.price_stats@v2.close"),)


def test_criteria_carry_the_configs_op_and_threshold(reader: StoreReader) -> None:
    """The web reads each rule from here, not from the untyped resolved config (whose criteria
    sit under ``rules``): op and value are the config's, a list stays a tuple, none is None."""
    doc = {
        "id": "ops", "kind": "screener", "impl": "rules", "version": 1,
        "selection": "all_active",
        "criteria": {
            "band": {"field": "rollup.price_stats@v2.close", "op": "between", "value": [5, 10]},
            "kind": {"field": "instrument.security_type", "op": "in", "value": ["ETF", "ADR"]},
            "has": {"field": "instrument.sector", "op": "not_null"},
        },
    }  # fmt: skip
    found = load_screener(context(reader, {("me", "screeners", "ops@1"): doc}), "ops")
    assert found is not None
    assert [(c.id, c.op, c.value) for c in found.criteria] == [
        ("band", "between", (5, 10)),
        ("kind", "in", ("ETF", "ADR")),
        ("has", "not_null", None),
    ]
