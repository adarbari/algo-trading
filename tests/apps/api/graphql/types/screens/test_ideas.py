"""``Query.ideas``, ``Query.screeners`` and ``Query.view`` over the golden API store
(``tests/helpers/api_store.py``): the site preset ``vrp_scanner`` ran on END; ``premium`` has
stored results but no config, so it is no screener (and picks nothing)."""

from pathlib import Path

from fastapi.testclient import TestClient

from algotrade.config.user import UserContext
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import FileConfigStore
from algotrade_api.deps import ApiSettings
from algotrade_api.main import create_app
from tests.apps.api.graphql.conftest import Graph
from tests.helpers.api_store import as_user, store_over

IDEAS = """query Ideas($first: Int!, $after: String, $names: [FeatureName!]!, $date: Date) {
  ideas(first: $first, after: $after, date: $date) {
    session priority total hasMore nextCursor pausedTotal
    paused { instrumentId instrument { symbol }
             result { configId decision reasons regime sizeMultiplier } }
    screeners {
      screener { id owner scope name version latestRun { runId } notRun { code } }
      run { runId status configVersion picked paused regime decisions { decision count } }
      notRun { code kind }
      picked
      top { rank instrumentId instrument { symbol } }
    }
    items {
      rank instrumentId regime sizeMultiplier
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
    body = graph(IDEAS, {"first": 10, "names": NAMES})
    assert "errors" not in body, body
    ideas = body["data"]["ideas"]
    assert (ideas["session"], ideas["priority"], ideas["total"]) == ("2022-11-23", [], 2)
    [screener] = [s for s in ideas["screeners"] if s["screener"]["id"] == "vrp_scanner"]
    assert len(ideas["screeners"]) == 92  # the other ninety-one site presets: NOT_RUN
    assert screener["screener"] == {
        "id": "vrp_scanner", "owner": "site", "scope": "site", "name": "VRP", "version": 4,
        "latestRun": {"runId": screener["run"]["runId"]}, "notRun": None,
    }  # fmt: skip
    run = screener["run"]
    assert (run["status"], run["configVersion"], run["picked"]) == ("complete", 1, 2)
    assert (run["paused"], run["regime"]) == (1, "CAUTION")  # CCC: held back, not picked
    assert {d["decision"]: d["count"] for d in run["decisions"]} == {
        "QUALIFIED": 1, "WATCH": 1, "PAUSED": 1
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
    assert (second["regime"], second["sizeMultiplier"]) == ("CAUTION", 0.75)
    assert ideas["pausedTotal"] == 1
    [held] = ideas["paused"]  # shown with its reason, never hidden
    assert (held["instrumentId"], held["instrument"]["symbol"]) == ("EQ:CCC", "CCC")
    assert held["result"] == {
        "configId": "vrp_scanner", "decision": "PAUSED", "regime": "CAUTION",
        "sizeMultiplier": 0.75,
        "reasons": "regime=CAUTION: vrp_scanner pauses in CAUTION",
    }  # fmt: skip
    earnings = {f["name"]: f for f in second["instrument"]["features"]}
    assert earnings[NAMES[0]]["value"] == "2022-12-01"
    assert first["picks"][0]["criteria"][0]["outcome"] == "NEAR"
    assert first["instrument"]["features"][0]["unknown"]["code"] in {"NO_ROW", "NULL"}


def test_an_earlier_session_has_its_own_runs_and_limit_caps(graph: Graph) -> None:
    before = graph(IDEAS, {"first": 10, "names": [], "date": "2022-11-22"})["data"]["ideas"]
    assert before["session"] == "2022-11-22"
    assert [i["instrument"]["symbol"] for i in before["items"]] == ["BBB", "CCC"]
    nothing = graph(IDEAS, {"first": 10, "names": [], "date": "2021-01-04"})["data"]["ideas"]
    assert (nothing["items"], nothing["total"]) == ([], 0)
    assert nothing["screeners"][0]["notRun"]["code"] == "NOT_RUN"
    over = graph(IDEAS, {"first": 5000, "names": []})
    assert over["data"]["ideas"] is None
    assert over["errors"][0]["extensions"]["code"] == "BAD_REQUEST"


def test_ideas_come_in_pages_by_an_opaque_cursor(graph: Graph) -> None:
    one = graph(IDEAS, {"first": 1, "names": []})["data"]["ideas"]
    assert [i["instrument"]["symbol"] for i in one["items"]] == ["BBB"]
    assert (one["total"], one["hasMore"], one["pausedTotal"], len(one["paused"])) == (2, True, 1, 1)
    assert isinstance(one["nextCursor"], str)
    two = graph(IDEAS, {"first": 1, "after": one["nextCursor"], "names": []})["data"]["ideas"]
    assert [(i["rank"], i["instrument"]["symbol"]) for i in two["items"]] == [(2, "AAA")]
    assert (two["hasMore"], two["nextCursor"], two["total"]) == (False, None, 2)
    assert (two["pausedTotal"], two["paused"]) == (1, [])  # the paused section is page one's
    bad = graph(IDEAS, {"first": 1, "after": "garbage", "names": []})
    assert bad["data"]["ideas"] is None
    assert bad["errors"][0]["extensions"]["code"] == "BAD_REQUEST"
    # the default page is 50 and the cap 100
    assert graph(IDEAS, {"first": 101, "names": []})["errors"][0]["extensions"]["code"] == (
        "BAD_REQUEST"
    )


def test_screeners_and_a_view(graph: Graph) -> None:
    body = graph(
        "{ screeners { id name latestRun { picked } notRun { code } }"
        ' view(scope: "screener:vrp_scanner") { scope saved columns names }'
        ' missing: view(scope: "screener:nope") { scope } }'
    )
    screeners = {s["id"]: s for s in body["data"]["screeners"]}
    assert len(screeners) == 92  # vrp_scanner and ninety-one other presets
    assert screeners["vrp_scanner"] == {
        "id": "vrp_scanner", "name": "VRP", "latestRun": {"picked": 2}, "notRun": None
    }  # fmt: skip
    assert screeners["breakout"]["notRun"] == {"code": "NOT_RUN"}
    assert body["data"]["view"] == {
        "scope": "screener:vrp_scanner", "saved": False, "columns": [], "names": []
    }  # fmt: skip
    assert body["data"]["missing"] is None


def test_an_empty_store_has_no_ideas_not_an_error(tmp_path: Path) -> None:
    store = store_over(MemoryBackend(), FileConfigStore(tmp_path), UserContext("local"))
    client = TestClient(
        create_app(ApiSettings("memory://", "config"), store, authenticator=as_user())
    )
    query = '{ ideas(first: 5) { total } screeners { id } view(scope: "x") { scope } }'
    body = client.post("/graphql", json={"query": query}).json()
    assert body == {"data": {"ideas": None, "screeners": [], "view": None}}
