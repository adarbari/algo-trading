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
