"""Every error in a response carries ``extensions.code``, mapped from the exception."""

import pytest
from graphql import GraphQLError

from algotrade.core.model.errors import ConfigurationError, MissingDataError
from algotrade.services.read.context import NotFoundError
from algotrade.services.read.instruments.catalogue import UnknownFeatureError
from algotrade_api.graphql.errors import code_of
from tests.apps.api.graphql.conftest import FACTS, Graph


@pytest.mark.parametrize(
    ("original", "code"),
    [
        (None, "BAD_REQUEST"),
        (GraphQLError("inner"), "BAD_REQUEST"),
        (UnknownFeatureError("x"), "UNKNOWN_FEATURE"),
        (NotFoundError("x"), "NOT_FOUND"),
        (MissingDataError("t", "unreadable", "hint"), "NO_DATA"),
        (ConfigurationError("x"), "BAD_REQUEST"),
        (ValueError("x"), "BAD_REQUEST"),
        (RuntimeError("x"), "INTERNAL"),
    ],
)
def test_codes_by_exception(original: Exception | None, code: str) -> None:
    assert code_of(GraphQLError("failed", original_error=original)) == code


def test_a_name_outside_the_catalogue_is_unknown_feature(graph: Graph) -> None:
    body = graph(FACTS, {"key": "AAA", "names": ["rollup.nope@v1.x"]})
    [error] = body["errors"]
    assert error["extensions"]["code"] == "UNKNOWN_FEATURE"
    assert "rollup.nope@v1.x" in error["message"]
    assert body["data"]["instrument"] is None  # features is non-null: the error nulls its parent
    assert body["data"]["session"] is not None  # the rest of the response stands


def test_a_malformed_feature_name_is_a_bad_request(graph: Graph) -> None:
    body = graph(FACTS, {"key": "AAA", "names": ["close"]})
    [error] = body["errors"]
    assert error["extensions"]["code"] == "BAD_REQUEST"
    assert "'close' is not a feature name" in error["message"]
    literal = graph('{ instrument(key: "AAA") { features(names: ["bad name"]) { name } } }')
    assert literal["errors"][0]["extensions"]["code"] == "BAD_REQUEST"


def test_a_parse_error_is_a_bad_request(graph: Graph) -> None:
    body = graph("{ session { date ")
    assert body["data"] is None
    assert body["errors"][0]["extensions"]["code"] == "BAD_REQUEST"
