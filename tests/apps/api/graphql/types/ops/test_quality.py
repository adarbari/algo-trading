"""``Query.{quality,verification}`` over the golden API store: the session's data-quality checks
and live verification, UNKNOWN (never an earlier session's) for a session they did not run for."""

from tests.apps.api.graphql.conftest import Graph

CHECKS = """query Q($date: Date) {
  quality(date: $date) {
    session runId status finishedAt checks { name status detail } unknown { code detail }
  }
  verification(date: $date) {
    session runIds instruments counts byCheck { check counts } failing unknown { code detail }
  }
}"""


def test_the_latest_session(graph: Graph) -> None:
    body = graph(CHECKS)
    assert "errors" not in body
    quality, verification = body["data"]["quality"], body["data"]["verification"]
    assert (quality["session"], quality["status"], quality["unknown"]) == (
        "2022-11-23",
        "complete",
        None,
    )
    assert [c["name"] for c in quality["checks"]] == ["bars_fresh", "chains_stale"]
    assert verification["counts"] == {"PASS": 1, "WARN": 1, "FAIL": 2, "NA": 1}
    assert [c["check"] for c in verification["byCheck"]] == ["low", "close", "div_yield"]
    assert verification["failing"][0]["symbol"] == "BBB"


def test_a_session_they_did_not_run_for_is_unknown(graph: Graph) -> None:
    body = graph(CHECKS, {"date": "2022-11-22"})
    assert "errors" not in body
    quality, verification = body["data"]["quality"], body["data"]["verification"]
    assert quality["unknown"]["code"] == "NOT_RUN" and quality["checks"] == []
    assert verification["unknown"]["code"] == "NO_PARTITION"
    assert verification["session"] == "2022-11-22" and verification["failing"] == []
