"""``PUT`` / ``DELETE /preferences/views/{scope}/view`` (a user's views of a table, read back by
GraphQL ``Query.view``)."""

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

ALICE = {"X-Act-For": "alice"}
SITE = {"X-Act-For": "site"}


VIEW = "/preferences/views/screener:vrp/view"
CLOSE = "rollup.price_stats@v2.close"
BODY = {"columns": [CLOSE], "sort": f"-{CLOSE}", "decisions": ["QUALIFIED", "WATCH"]}
READ = """query View($scope: String!, $name: String) {
  view(scope: $scope, name: $name) {
    scope name saved columns sort decisions names narrowColumns filters
  }
}"""


def read(client: TestClient, name: str | None = None) -> dict[str, Any]:
    body = client.post("/graphql", json={"query": READ, "variables": {
        "scope": "screener:vrp", "name": name}}).json()  # fmt: skip
    view = body["data"]["view"]
    view["narrow_columns"] = view.pop("narrowColumns")  # the REST body's spelling
    return view  # type: ignore[no-any-return]


def test_a_view_is_saved_per_user_read_back_and_keeps_other_preferences(
    writer_client: TestClient, root: Path
) -> None:
    prefs = root / "users" / "local" / "preferences.toml"
    assert read(writer_client) == {
        "scope": "screener:vrp", "name": None, "saved": False, "columns": [], "sort": None,
        "decisions": [], "names": [], "narrow_columns": [], "filters": "",
    }  # fmt: skip
    saved = writer_client.put(VIEW, json=BODY)
    assert (saved.status_code, saved.json()) == (
        200,
        {
            "scope": "screener:vrp",
            "name": None,
            "saved": True,
            "names": [],
            "narrow_columns": [],
            "filters": "",
            **BODY,
        },
    )
    assert read(writer_client) == saved.json()
    text = prefs.read_text()
    assert CLOSE in text and '[views."screener:vrp".view]' in text
    assert writer_client.put(VIEW, json=BODY, headers={"X-Act-For": "bob"}).status_code == 200
    assert (root / "users" / "bob" / "preferences.toml").exists()  # bob's own file
    cleared = writer_client.put(VIEW, json={"columns": [], "sort": None, "decisions": []})
    assert cleared.json()["sort"] is None and cleared.json()["columns"] == []


def test_a_view_carries_its_filters_and_an_unknown_id_is_kept(
    writer_client: TestClient, root: Path
) -> None:
    f = "decision:QUALIFIED,WATCH;!no_such_filter:1..5;dte:..14"  # no_such_filter: no definition
    saved = writer_client.put(VIEW, json={**BODY, "filters": f})
    assert (saved.status_code, saved.json()["filters"]) == (200, f)
    assert read(writer_client)["filters"] == f
    assert writer_client.put(VIEW, json=BODY).json()["filters"] == ""  # absent: none
    assert read(writer_client)["filters"] == ""


def test_a_view_stored_without_filters_reads_with_none(
    writer_client: TestClient, root: Path
) -> None:
    prefs = root / "users" / "local" / "preferences.toml"
    prefs.parent.mkdir(parents=True)
    prefs.write_text('[views."screener:vrp".view]\ncolumns = []\ndecisions = ["WATCH"]\n')
    legacy = read(writer_client)
    assert (legacy["saved"], legacy["decisions"], legacy["filters"]) == (True, ["WATCH"], "")


def test_a_view_saved_under_the_old_layout_moves_on_the_next_write(
    writer_client: TestClient, root: Path
) -> None:
    prefs = root / "users" / "local" / "preferences.toml"
    prefs.parent.mkdir(parents=True)
    prefs.write_text(
        '[screeners.vrp.view]\ncolumns = ["rollup.price_stats@v2.close"]\ndecisions = []\n'
        '[screeners.vrp.views.Mine]\ncolumns = []\ndecisions = ["WATCH"]\n'
    )
    assert read(writer_client)["columns"] == [CLOSE]  # read where it was saved
    writer_client.put(VIEW, json=BODY)  # any write moves it
    text = prefs.read_text()
    assert "[screeners" not in text and '[views."screener:vrp".views.Mine]' in text
    assert read(writer_client)["names"] == ["Mine"]
    assert read(writer_client, "Mine")["decisions"] == ["WATCH"]


def test_a_view_is_checked_before_it_is_saved(writer_client: TestClient, root: Path) -> None:
    refused = (
        {**BODY, "columns": ["feature.no_such"]},
        {**BODY, "columns": [CLOSE, CLOSE]},
        {**BODY, "decisions": ["qualified"]},
        {**BODY, "decisions": ["WATCH", "WATCH"]},
        {**BODY, "sort": " "},
        {**BODY, "narrow_columns": ["name", "name"]},
        {**BODY, "narrow_columns": [" name"]},
        {**BODY, "narrow_columns": [""]},
        {**BODY, "narrow_columns": [f"c{i}" for i in range(41)]},
        {**BODY, "filters": "decision"},
        {**BODY, "filters": "a:1;;b:2"},
        {**BODY, "filters": ":1"},
        {**BODY, "filters": "a:" + "x" * 2000},
        {**BODY, "filters": "a:1\n"},
    )
    for body in refused:
        assert writer_client.put(VIEW, json=body).status_code == 400, body
    for scope in ("screener:nope", "vrp", "explore:vrp", "screener:Bad Id"):
        url = f"/preferences/views/{scope}/view"
        assert writer_client.put(url, json=BODY).status_code == 400, scope
    assert writer_client.put(VIEW, json=BODY, headers=SITE).status_code == 400
    assert not (root / "users").exists()


def test_named_views_sit_beside_the_default_and_can_be_removed(
    writer_client: TestClient, root: Path
) -> None:
    prefs = root / "users" / "local" / "preferences.toml"
    writer_client.put(VIEW, json=BODY)  # the default view
    review = {"columns": [], "sort": "-score", "decisions": ["QUALIFIED"]}
    saved = writer_client.put(f"{VIEW}?name=VRP%20review", json=review)
    assert saved.status_code == 200
    assert (saved.json()["name"], saved.json()["names"]) == ("VRP review", ["VRP review"])
    writer_client.put(f"{VIEW}?name=Earnings", json={**review, "sort": None})
    named = read(writer_client, "VRP review")
    assert (named["saved"], named["sort"], named["names"]) == (
        True,
        "-score",
        ["Earnings", "VRP review"],
    )
    assert read(writer_client)["columns"] == [CLOSE]  # the default is untouched
    assert read(writer_client, "nope")["saved"] is False
    assert '"VRP review"' in prefs.read_text()
    left = writer_client.delete(f"{VIEW}?name=VRP%20review")
    assert (left.status_code, left.json()) == (200, {"names": ["Earnings"]})
    assert read(writer_client, "VRP review")["saved"] is False
    assert writer_client.delete(f"{VIEW}?name=VRP%20review").status_code == 404
    assert writer_client.delete(VIEW).status_code == 422  # a name is required


def test_view_names_are_checked(writer_client: TestClient, root: Path) -> None:
    for name in ("", " x", "x ", "a" * 41, "tab\there"):
        assert writer_client.put(VIEW, json=BODY, params={"name": name}).status_code == 400, name
    assert not (root / "users").exists()


def test_narrow_columns_are_saved_read_back_and_optional(writer_client: TestClient) -> None:
    body = {**BODY, "narrow_columns": ["name", "criterion:vrp", CLOSE]}
    saved = writer_client.put(VIEW, json=body)
    assert saved.json()["narrow_columns"] == body["narrow_columns"]
    assert read(writer_client)["narrow_columns"] == body["narrow_columns"]
    old_client = writer_client.put(VIEW, json=BODY)  # no key: an old client keeps the phone's
    assert old_client.status_code == 200
    assert old_client.json()["narrow_columns"] == body["narrow_columns"]
    cleared = writer_client.put(VIEW, json={**BODY, "narrow_columns": []})  # an empty list clears
    assert cleared.json()["narrow_columns"] == []


def test_a_surface_with_a_filter_bar_keeps_views_and_an_unknown_one_is_refused(
    writer_client: TestClient,
) -> None:
    url = "/preferences/views/surface:ideas/view"
    body = {"columns": [], "sort": None, "decisions": [], "filters": "decision:QUALIFIED"}
    assert writer_client.put(url, json=body).status_code == 200
    assert writer_client.put(url, json=body, params={"name": "Qualified"}).status_code == 200
    seen = writer_client.post("/graphql", json={"query": READ, "variables": {
        "scope": "surface:ideas", "name": "Qualified"}}).json()["data"]["view"]  # fmt: skip
    assert (seen["saved"], seen["filters"], seen["names"]) == (
        True, "decision:QUALIFIED", ["Qualified"]
    )  # fmt: skip
    assert writer_client.put("/preferences/views/surface:nope/view", json=body).status_code == 400


APPEARANCE = "/preferences/appearance"
READ_THEME = "query Appearance { appearance { theme } }"


def read_theme(client: TestClient) -> str:
    return client.post("/graphql", json={"query": READ_THEME}).json()["data"]["appearance"]["theme"]  # type: ignore[no-any-return]


def test_the_theme_is_saved_per_user_read_back_and_keeps_the_views(
    writer_client: TestClient, root: Path
) -> None:
    prefs = root / "users" / "local" / "preferences.toml"
    assert read_theme(writer_client) == "system"  # nothing stored: the OS decides
    writer_client.put(VIEW, json=BODY)
    saved = writer_client.put(APPEARANCE, json={"theme": "dark"})
    assert (saved.status_code, saved.json()) == (200, {"theme": "dark"})
    assert read_theme(writer_client) == "dark"
    text = prefs.read_text()
    assert "[appearance]" in text and 'theme = "dark"' in text and CLOSE in text
    assert read(writer_client)["columns"] == [CLOSE]  # the view is still there
    writer_client.put(VIEW, json=BODY)  # a views write keeps the theme
    assert read_theme(writer_client) == "dark"
    bob = {"X-Act-For": "bob"}
    assert writer_client.put(APPEARANCE, json={"theme": "light"}, headers=bob).status_code == 200
    assert (root / "users" / "bob" / "preferences.toml").exists()
    assert read_theme(writer_client) == "dark"  # bob's own file


def test_a_malformed_stored_theme_reads_as_system(writer_client: TestClient, root: Path) -> None:
    prefs = root / "users" / "local" / "preferences.toml"
    prefs.parent.mkdir(parents=True)
    prefs.write_text('[appearance]\ntheme = "sepia"\n')
    assert read_theme(writer_client) == "system"


def test_a_theme_is_checked_before_it_is_saved(writer_client: TestClient, root: Path) -> None:
    for body in ({"theme": "sepia"}, {"theme": "Dark"}, {"theme": ""}):
        assert writer_client.put(APPEARANCE, json=body).status_code == 400, body
    assert writer_client.put(APPEARANCE, json={}).status_code == 422
    assert not (root / "users" / "local" / "preferences.toml").exists()
