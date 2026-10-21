"""Read-your-writes of ``POST /features/user`` (ADR 0077 decision 16): a saved user feature is in
the caller's next ``FeatureCatalogue`` read (cached per user), not in another user's."""

from fastapi.testclient import TestClient

from tests.contract.api.read_your_writes.conftest import Gate

CATALOGUE = "query FeatureCatalogue { catalogue { name kind } }"
BODY = {
    "name": "hv_pct",
    "expr": "price_stats.hv20 * 100",
    "dtype": "float",
    "unit": "pct_points",
    "description": "hv20 in percent",
    "null_meaning": "hv20 is null",
}


def names(rows: list[dict[str, str]]) -> set[str]:
    return {r["name"] for r in rows}


def test_a_saved_user_feature_is_in_the_next_catalogue(
    gate: Gate, writer_client: TestClient, trader_client: TestClient
) -> None:
    c = writer_client
    assert not any("hv_pct" in n for n in names(gate.warm(c, CATALOGUE)))
    assert not any("hv_pct" in n for n in names(gate.warm(trader_client, CATALOGUE)))
    assert c.post("/features/user", json=BODY).status_code == 201
    assert any("hv_pct" in n for n in names(gate.fresh(c, CATALOGUE)))
    assert not any("hv_pct" in n for n in names(gate.warm(trader_client, CATALOGUE)))
