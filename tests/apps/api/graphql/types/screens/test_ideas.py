"""``Query.ideas``, ``Query.screeners`` and ``Query.view`` over the golden API store
(``tests/helpers/api_store.py``): the site preset ``vrp_scanner`` ran on END; ``premium`` has
stored results but no config, so it is no screener (and picks nothing)."""

from pathlib import Path

from fastapi.testclient import TestClient

from algotrade.config.user import UserContext
from algotrade.services.explore.store import store_over
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import FileConfigStore
from algotrade_api.deps import ApiSettings
from algotrade_api.main import create_app
from tests.apps.api.graphql.conftest import Graph

IDEAS = """query Ideas($limit: Int!, $names: [FeatureName!]!, $date: Date) {
  ideas(limit: $limit, date: $date) {
    session priority total
    screeners {
      screener { id owner scope name version latestRun { runId } notRun { code } }
      run { runId status configVersion picked decisions { decision count } }
      notRun { code detail }
      picked
      top { rank instrumentId instrument { symbol } }
    }
    items {
      rank instrumentId
      instrument { symbol features(names: $names) { name value unknown { code } } }
      picks {
        configId decision score reasons flags
        criteria { id field outcome value distance }
        columns { name value }
      }
    }
  }
}"""
NAMES = ["rollup.earnings@v1.next_earnings_date", "rollup.earnings@v1.last_earnings_date"]


def test_ideas_rank_the_runs_of_the_session_with_every_pick(graph: Graph) -> None:
    body = graph(IDEAS, {"limit": 10, "names": NAMES})
    assert "errors" not in body, body
    ideas = body["data"]["ideas"]
    assert (ideas["session"], ideas["priority"], ideas["total"]) == ("2022-11-23", [], 2)
    [screener] = ideas["screeners"]
    assert screener["screener"] == {
        "id": "vrp_scanner", "owner": "site", "scope": "site", "name": "VRP", "version": 3,
        "latestRun": {"runId": screener["run"]["runId"]}, "notRun": None,
    }  # fmt: skip
    run = screener["run"]
    assert (run["status"], run["configVersion"], run["picked"]) == ("complete", 1, 2)
    assert {d["decision"]: d["count"] for d in run["decisions"]} == {
        "QUALIFIED": 1, "WATCH": 1, "REJECT": 1
    }  # fmt: skip
    assert (screener["picked"], screener["notRun"]) == (2, None)
    assert [t["instrument"]["symbol"] for t in screener["top"]] == ["AAA", "BBB"]
    first, second = ideas["items"]
    assert (first["rank"], first["instrument"]["symbol"]) == (1, "BBB")  # score 90 > 80
    assert second["instrument"]["symbol"] == "AAA"
    [pick] = second["picks"]
    assert (pick["configId"], pick["flags"]) == ("vrp_scanner", ["leveraged_inverse"])
    assert pick["columns"] == [{"name": "spread", "value": 0.05}]
    assert pick["criteria"] == [
        {"id": "iv30", "field": "feature.vrp_iv30", "outcome": "PASS", "value": 0.62,
         "distance": None}
    ]  # fmt: skip
    earnings = {f["name"]: f for f in second["instrument"]["features"]}
    assert earnings[NAMES[0]]["value"] == "2022-12-01"
    assert first["picks"][0]["criteria"][0]["outcome"] == "NEAR"
    assert first["instrument"]["features"][0]["unknown"]["code"] in {"NO_ROW", "NULL"}


def test_an_earlier_session_has_its_own_runs_and_limit_caps(graph: Graph) -> None:
    before = graph(IDEAS, {"limit": 10, "names": [], "date": "2022-11-22"})["data"]["ideas"]
    assert before["session"] == "2022-11-22"
    assert [i["instrument"]["symbol"] for i in before["items"]] == ["BBB", "CCC"]
    nothing = graph(IDEAS, {"limit": 10, "names": [], "date": "2021-01-04"})["data"]["ideas"]
    assert (nothing["items"], nothing["total"]) == ([], 0)
    assert nothing["screeners"][0]["notRun"]["code"] == "NOT_RUN"
    over = graph(IDEAS, {"limit": 5000, "names": []})
    assert over["data"]["ideas"] is None
    assert over["errors"][0]["extensions"]["code"] == "BAD_REQUEST"


def test_screeners_and_a_view(graph: Graph) -> None:
    body = graph(
        "{ screeners { id name latestRun { picked } notRun { code } }"
        ' view(scope: "screener:vrp_scanner") { scope saved columns names }'
        ' missing: view(scope: "screener:nope") { scope } }'
    )
    assert body["data"]["screeners"] == [
        {"id": "vrp_scanner", "name": "VRP", "latestRun": {"picked": 2}, "notRun": None}
    ]
    assert body["data"]["view"] == {
        "scope": "screener:vrp_scanner", "saved": False, "columns": [], "names": []
    }  # fmt: skip
    assert body["data"]["missing"] is None


def test_an_empty_store_has_no_ideas_not_an_error(tmp_path: Path) -> None:
    store = store_over(MemoryBackend(), FileConfigStore(tmp_path), UserContext("local"))
    client = TestClient(create_app(ApiSettings("memory://", "config"), store))
    query = '{ ideas(limit: 5) { total } screeners { id } view(scope: "x") { scope } }'
    body = client.post("/graphql", json={"query": query}).json()
    assert body == {"data": {"ideas": None, "screeners": [], "view": None}}
