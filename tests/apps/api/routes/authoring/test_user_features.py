"""``POST /features/user``: a checked user feature, then in the user's catalogue."""

from pathlib import Path

from fastapi.testclient import TestClient

ALICE = {"X-Act-For": "alice"}  # an admin writing for another declared user

BODY = {
    "name": "hv_pct",
    "expr": "price_stats.hv20 * 100",
    "dtype": "float",
    "unit": "pct_points",
    "description": "hv20 in percent",
    "null_meaning": "hv20 is null",
}


def test_saves_a_checked_user_feature(writer_client: TestClient, root: Path) -> None:
    saved = writer_client.post("/features/user", json=BODY, headers=ALICE)
    assert saved.status_code == 201
    assert saved.json() | {"inputs": []} == {
        "name": "hv_pct",
        "field": "feature.hv_pct",
        "theme": "builder",
        "dtype": "float",
        "kind": "expression",
        "inputs": [],
    }
    assert (root / "users" / "alice" / "features" / "builder.toml").is_file()


def test_an_invalid_formula_is_never_saved(writer_client: TestClient, root: Path) -> None:
    bad = writer_client.post("/features/user", json=BODY | {"expr": "nope.x * 2"}, headers=ALICE)
    assert bad.status_code == 400
    assert not (root / "users").exists()
