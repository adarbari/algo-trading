"""``PUT /preferences/ideas``: the priority is checked, saved, and read back by ``/ideas``."""

from pathlib import Path

from fastapi.testclient import TestClient

URL = "/preferences/ideas?user=alice"


def test_saves_the_priority_of_site_presets_and_keeps_other_preferences(
    writer_client: TestClient, root: Path
) -> None:
    prefs = root / "users" / "alice" / "preferences.toml"
    prefs.parent.mkdir(parents=True)
    prefs.write_text('[theme]\nname = "dark"\n')
    saved = writer_client.put(URL, json={"priority": ["vrp"]})
    assert (saved.status_code, saved.json()) == (200, {"priority": ["vrp"]})
    text = prefs.read_text()
    assert 'priority = ["vrp"]' in text and 'name = "dark"' in text


def test_unknown_duplicate_or_site_users_are_refused(writer_client: TestClient, root: Path) -> None:
    for body in ({"priority": ["nope"]}, {"priority": ["vrp", "vrp"]}, {"priority": ["Bad Id"]}):
        assert writer_client.put(URL, json=body).status_code == 400
    assert (
        writer_client.put("/preferences/ideas?user=site", json={"priority": []}).status_code == 400
    )
    assert not (root / "users").exists()


VIEW = "/preferences/screeners/vrp/view?user=alice"
CLOSE = "rollup.price_stats@v2.close"
BODY = {"columns": [CLOSE], "sort": f"-{CLOSE}", "decisions": ["QUALIFIED", "WATCH"]}


def test_a_view_is_saved_per_user_read_back_and_keeps_other_preferences(
    writer_client: TestClient, root: Path
) -> None:
    prefs = root / "users" / "alice" / "preferences.toml"
    assert writer_client.get(VIEW).json() == {
        "screener_id": "vrp", "name": None, "saved": False, "columns": [], "sort": None,
        "decisions": [], "names": [],
    }  # fmt: skip
    writer_client.put(URL, json={"priority": ["vrp"]})
    saved = writer_client.put(VIEW, json=BODY)
    assert (saved.status_code, saved.json()) == (
        200,
        {"screener_id": "vrp", "name": None, "saved": True, "names": [], **BODY},
    )
    assert writer_client.get(VIEW).json() == saved.json()
    text = prefs.read_text()
    assert 'priority = ["vrp"]' in text and CLOSE in text
    assert writer_client.get("/preferences/screeners/vrp/view?user=bob").json()["saved"] is False
    cleared = writer_client.put(VIEW, json={"columns": [], "sort": None, "decisions": []})
    assert cleared.json()["sort"] is None and cleared.json()["columns"] == []


def test_a_view_is_checked_before_it_is_saved(writer_client: TestClient, root: Path) -> None:
    refused = (
        {**BODY, "columns": ["feature.no_such"]},
        {**BODY, "columns": [CLOSE, CLOSE]},
        {**BODY, "decisions": ["qualified"]},
        {**BODY, "decisions": ["WATCH", "WATCH"]},
        {**BODY, "sort": " "},
    )
    for body in refused:
        assert writer_client.put(VIEW, json=body).status_code == 400, body
    unknown = "/preferences/screeners/nope/view?user=alice"
    assert writer_client.put(unknown, json=BODY).status_code == 400
    assert writer_client.put(VIEW.replace("alice", "site"), json=BODY).status_code == 400
    assert writer_client.get(unknown).status_code == 404
    assert not (root / "users").exists()


def test_named_views_sit_beside_the_default_and_can_be_removed(
    writer_client: TestClient, root: Path
) -> None:
    prefs = root / "users" / "alice" / "preferences.toml"
    writer_client.put(VIEW, json=BODY)  # the default view
    review = {"columns": [], "sort": "-score", "decisions": ["QUALIFIED"]}
    saved = writer_client.put(f"{VIEW}&name=VRP%20review", json=review)
    assert saved.status_code == 200
    assert (saved.json()["name"], saved.json()["names"]) == ("VRP review", ["VRP review"])
    writer_client.put(f"{VIEW}&name=Earnings", json={**review, "sort": None})
    named = writer_client.get(f"{VIEW}&name=VRP%20review").json()
    assert (named["saved"], named["sort"], named["names"]) == (
        True,
        "-score",
        ["Earnings", "VRP review"],
    )
    assert writer_client.get(VIEW).json()["columns"] == [CLOSE]  # the default is untouched
    assert writer_client.get(f"{VIEW}&name=nope").json()["saved"] is False
    assert '"VRP review"' in prefs.read_text()
    left = writer_client.delete(f"{VIEW}&name=VRP%20review")
    assert (left.status_code, left.json()) == (200, {"names": ["Earnings"]})
    assert writer_client.get(f"{VIEW}&name=VRP%20review").json()["saved"] is False
    assert writer_client.delete(f"{VIEW}&name=VRP%20review").status_code == 404
    assert writer_client.delete(VIEW).status_code == 422  # a name is required


def test_view_names_are_checked(writer_client: TestClient, root: Path) -> None:
    for name in ("", " x", "x ", "a" * 41, "tab\there"):
        assert writer_client.put(VIEW, json=BODY, params={"name": name}).status_code == 400, name
    assert not (root / "users").exists()
