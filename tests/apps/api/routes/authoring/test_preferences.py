"""``PUT /preferences/ideas`` (the priority is checked and saved) and ``PUT`` / ``DELETE
/preferences/views/{scope}/view`` (a user's views of a table, read back by GraphQL
``Query.view``)."""

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

URL = "/preferences/ideas"
ALICE = {"X-Act-For": "alice"}
SITE = {"X-Act-For": "site"}


def test_saves_the_priority_of_site_presets_and_keeps_other_preferences(
    writer_client: TestClient, root: Path
) -> None:
    prefs = root / "users" / "alice" / "preferences.toml"
    prefs.parent.mkdir(parents=True)
    prefs.write_text('[theme]\nname = "dark"\n')
    saved = writer_client.put(URL, json={"priority": ["vrp"]}, headers=ALICE)
    assert (saved.status_code, saved.json()) == (200, {"priority": ["vrp"]})
    text = prefs.read_text()
    assert 'priority = ["vrp"]' in text and 'name = "dark"' in text


def test_unknown_duplicate_or_site_users_are_refused(writer_client: TestClient, root: Path) -> None:
    for body in ({"priority": ["nope"]}, {"priority": ["vrp", "vrp"]}, {"priority": ["Bad Id"]}):
        assert writer_client.put(URL, json=body, headers=ALICE).status_code == 400
    site = writer_client.put(URL, json={"priority": []}, headers=SITE)
    assert site.status_code == 400
    assert not (root / "users").exists()


VIEW = "/preferences/views/screener:vrp/view"
CLOSE = "rollup.price_stats@v2.close"
BODY = {"columns": [CLOSE], "sort": f"-{CLOSE}", "decisions": ["QUALIFIED", "WATCH"]}
READ = """query View($scope: String!, $name: String) {
  view(scope: $scope, name: $name) { scope name saved columns sort decisions names narrowColumns }
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
        "decisions": [], "names": [], "narrow_columns": [],
    }  # fmt: skip
    writer_client.put("/preferences/ideas", json={"priority": ["vrp"]})
    saved = writer_client.put(VIEW, json=BODY)
    assert (saved.status_code, saved.json()) == (
        200,
        {
            "scope": "screener:vrp",
            "name": None,
            "saved": True,
            "names": [],
            "narrow_columns": [],
            **BODY,
        },
    )
    assert read(writer_client) == saved.json()
    text = prefs.read_text()
    assert 'priority = ["vrp"]' in text and CLOSE in text and '[views."screener:vrp".view]' in text
    assert writer_client.put(VIEW, json=BODY, headers={"X-Act-For": "bob"}).status_code == 200
    assert (root / "users" / "bob" / "preferences.toml").exists()  # bob's own file
    cleared = writer_client.put(VIEW, json={"columns": [], "sort": None, "decisions": []})
    assert cleared.json()["sort"] is None and cleared.json()["columns"] == []


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
    writer_client.put("/preferences/ideas", json={"priority": ["vrp"]})  # any write moves it
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
