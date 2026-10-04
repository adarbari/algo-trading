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
        "screener_id": "vrp", "saved": False, "columns": [], "sort": None, "decisions": [],
    }  # fmt: skip
    writer_client.put(URL, json={"priority": ["vrp"]})
    saved = writer_client.put(VIEW, json=BODY)
    assert (saved.status_code, saved.json()) == (200, {"screener_id": "vrp", "saved": True, **BODY})
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
