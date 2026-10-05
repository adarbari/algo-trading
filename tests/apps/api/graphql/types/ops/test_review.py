"""``Query.{figiReview,leverageReview}`` over the golden API store: the owner's review lists."""

from tests.apps.api.graphql.conftest import Graph

REVIEW = """{
  figiReview { session source items }
  leverageReview { session source items }
}"""


def test_review_lists(graph: Graph) -> None:
    body = graph(REVIEW)
    assert "errors" not in body
    figi, leveraged = body["data"]["figiReview"], body["data"]["leverageReview"]
    assert figi["source"].startswith("universe_build-")
    assert [r["symbol"] for r in figi["items"]] == ["BBB"]
    assert [r["symbol"] for r in leveraged["items"]] == ["CCC"]
    assert leveraged["source"] == "instruments/reference"
