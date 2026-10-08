"""The dataloaders: one loader call per distinct arguments for a whole batch of instruments
(``features``: one ``load_feature_values`` per distinct ``names``; the pane objects alike; no
N+1), each key's own result or error."""

import asyncio
from collections.abc import Sequence

import pytest

from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments import features, holdings
from algotrade.services.read.instruments.catalogue import UnknownFeatureError
from algotrade_api.graphql import loaders
from algotrade_api.graphql.loaders import Loaders
from tests.apps.api.graphql.conftest import Graph

CLOSE = "rollup.price_stats@v2.close"
SECTOR = "instrument.sector"


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[list[str], tuple[str, ...]]]:
    seen: list[tuple[list[str], tuple[str, ...]]] = []
    real = features.load_feature_values

    def counting(ctx: ReadContext, ids: Sequence[str], names: Sequence[str]):  # type: ignore[no-untyped-def]
        seen.append((list(ids), tuple(names)))
        return real(ctx, ids, names)

    monkeypatch.setattr(loaders, "load_feature_values", counting)
    return seen


def test_one_read_for_every_instrument_asking_the_same_names(
    graph: Graph, calls: list[tuple[list[str], tuple[str, ...]]]
) -> None:
    query = """query($n: [FeatureName!]!, $m: [FeatureName!]!) {
      a: instrument(key: "AAA") { features(names: $n) { value } }
      b: instrument(key: "BBB") { features(names: $n) { value } }
      c: instrument(key: "CCC") { features(names: $m) { value } }
    }"""
    body = graph(query, {"n": [CLOSE], "m": [SECTOR, CLOSE]})
    assert "errors" not in body
    assert [v["value"] for v in body["data"]["b"]["features"]] == [102.0]
    # (top-level fields resolve in threads, so the order the siblings asked in is not fixed)
    assert sorted((sorted(ids), names) for ids, names in calls) == [
        (["EQ:AAA", "EQ:BBB"], (CLOSE,)),
        (["EQ:CCC"], (SECTOR, CLOSE)),
    ]


def test_an_error_is_the_result_of_each_key_that_asked(ctx: ReadContext) -> None:
    keys = [("EQ:AAA", ("rollup.nope@v1.x",)), ("EQ:AAA", (CLOSE,))]
    bad, good = asyncio.run(loaders._feature_values(ctx, keys))
    assert isinstance(bad, UnknownFeatureError)
    assert isinstance(good, tuple) and good[0].name == CLOSE


def test_loaders_are_per_read_context(ctx: ReadContext) -> None:
    assert Loaders(ctx).features is not Loaders(ctx).features


def test_a_pane_object_is_read_once_for_every_instrument_asking_it(
    graph: Graph, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[list[str]] = []

    def counting(ctx: ReadContext, ids: Sequence[str], top: int):  # type: ignore[no-untyped-def]
        seen.append(list(ids))
        return holdings.load_holdings(ctx, ids, top)

    monkeypatch.setattr(loaders, "load_holdings", counting)
    query = """{
      a: instrument(key: "BULL") { holdings { total } }
      b: instrument(key: "AAA") { holdings { total } }
    }"""
    found = graph(query)
    assert "errors" not in found
    assert found["data"] == {"a": {"holdings": {"total": 40}}, "b": {"holdings": None}}
    assert seen == [["EQ:BULL", "EQ:AAA"]]


def test_a_failing_batch_is_the_error_of_each_key(ctx: ReadContext) -> None:
    def failing(ctx: ReadContext, ids: Sequence[str]) -> dict[str, object]:
        raise ValueError("boom")

    found = asyncio.run(loaders.batched(failing, ctx, [("EQ:AAA",), ("EQ:BBB",)]))
    assert [str(e) for e in found] == ["boom", "boom"]
