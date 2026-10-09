"""How much one request may ask for: depth, aliases, tokens, and the list caps."""

from typing import Any

import pytest
from graphql import GraphQLError

from algotrade_api.graphql import limits
from algotrade_api.graphql.limits import MAX_ALIASES, MAX_NAMES, MAX_TOKENS, MaxItems
from tests.apps.api.graphql.conftest import Graph


def _bad_request(body: dict[str, Any], words: str) -> None:
    assert body["data"] is None or "errors" in body, body
    found = [e for e in body["errors"] if words in e["message"]]
    assert found, body["errors"]
    assert found[0]["extensions"]["code"] == "BAD_REQUEST"


def test_too_deep(graph: Graph, monkeypatch: pytest.MonkeyPatch) -> None:
    # Today's graph is four levels deep (instrument > features > info > name): a lower cap
    # shows the limiter at work (the extension reads the cap per request).
    assert limits.MAX_DEPTH == 8
    query = '{ instrument(key: "AAA") { features(names: []) { info { name } } } }'
    assert "errors" not in graph(query)
    monkeypatch.setattr(limits, "MAX_DEPTH", 2)
    # another document: the first answer is in the response cache, which a patched cap bypasses
    _bad_request(graph(query + " # capped"), "exceeds maximum operation depth of 2")


def test_too_many_aliases(graph: Graph) -> None:
    aliases = " ".join(f"s{i}: session {{ date }}" for i in range(MAX_ALIASES + 1))
    _bad_request(graph(f"{{ {aliases} }}"), "aliases")


def test_too_many_tokens(graph: Graph) -> None:
    fields = " ".join(["date"] * MAX_TOKENS)
    _bad_request(graph(f"{{ session {{ {fields} }} }}"), "token")


def test_too_many_feature_names(graph: Graph) -> None:
    names = [f"instrument.c{i}" for i in range(MAX_NAMES + 1)]
    query = 'query($n: [FeatureName!]!) { instrument(key: "AAA") { features(names: $n) { name } } }'
    _bad_request(graph(query, {"n": names}), f"names: at most {MAX_NAMES}, got {MAX_NAMES + 1}")


@pytest.mark.parametrize("value", [1000, None, list(range(1000))])
def test_max_items_lets_values_within_the_cap_through(value: Any) -> None:
    cap = MaxItems("first", 1000)
    echo = cap.resolve(lambda source, info, **kw: kw, None, None, first=value)  # type: ignore[arg-type]
    assert echo == {"first": value}


@pytest.mark.parametrize("value", [1001, list(range(1001))])
def test_max_items_refuses_before_the_resolver_runs(value: Any) -> None:
    called: list[bool] = []
    cap = MaxItems("first", 1000)
    with pytest.raises(GraphQLError, match="first: at most 1000, got 1001"):
        cap.resolve(lambda *a, **kw: called.append(True), None, None, first=value)  # type: ignore[arg-type]
    assert called == []
