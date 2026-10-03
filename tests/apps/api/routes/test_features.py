from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient


def test_catalogue_lists_instrument_and_rollup_fields(client: TestClient) -> None:
    catalogue = {f["name"]: f for f in client.get("/features").json()}
    hv20 = catalogue["rollup.price_stats@v2.hv20"]
    assert (hv20["dtype"], hv20["version"], hv20["group"], hv20["key"]) == (
        "float32",
        2,
        "price_stats@v2",
        "price_stats.hv20@v2",
    )
    assert hv20["kind"] != "instrument" and hv20["unit"] and hv20["null_meaning"]
    assert hv20["inputs"]
    assert catalogue["instrument.sector"]["source"] == "instruments/company"
    label = catalogue["feature.liquidity_class"]
    assert (label["kind"], label["source"], label["key"], label["group"]) == (
        "label", "expression", "liquidity_class@v1", None,
    )  # fmt: skip
    assert label["categories"] == ["HIGH", "MEDIUM", "LOW", "UNKNOWN"] and label["inputs"]
    assert catalogue["feature.div_yield"]["source"] == "rollups/instrument/div_yield@v1"
    assert hv20["licence"] == "open" and catalogue["instrument.sector"]["licence"] == "open"


def test_catalogue_is_the_callers_site_plus_their_own_features(
    client: TestClient, user_client: Callable[[str], TestClient]
) -> None:
    site = {f["name"]: f for f in client.get("/features").json()}
    assert (site["feature.liquidity_class"]["scope"], site["feature.liquidity_class"]["owner"]) == (
        "site", None,
    )  # fmt: skip
    assert "feature.hv20_pct" not in site
    alice = {f["name"]: f for f in user_client("alice").get("/features").json()}
    mine = alice["feature.hv20_pct"]
    assert (mine["scope"], mine["owner"], mine["source"], mine["inputs"]) == (
        "user", "alice", "expression", ["price_stats.hv20@v2"],
    )  # fmt: skip
    assert set(alice) - set(site) == {"feature.hv20_pct"}
    bob = user_client("bob")
    assert "feature.hv20_pct" not in {f["name"] for f in bob.get("/features").json()}
    assert bob.get("/features/feature.hv20_pct/distribution").status_code == 404
    spread = user_client("alice").get("/features/feature.hv20_pct/distribution").json()
    assert (spread["count"], spread["nulls"]) == (4, 1)


def test_numeric_distribution(client: TestClient) -> None:
    body = client.get("/features/rollup.price_stats@v2.hv20/distribution").json()
    assert (body["session"], body["count"], body["nulls"]) == ("2022-11-23", 4, 1)
    assert body["quantiles"]["0.5"] == pytest.approx(0.21)
    assert sum(b["count"] for b in body["histogram"]) == 3
    earlier = client.get(
        "/features/rollup.price_stats@v2.hv20/distribution", params={"date": "2022-11-22"}
    ).json()
    assert earlier["session"] == "2022-11-22"


def test_categorical_distribution(client: TestClient) -> None:
    body = client.get("/features/instrument.security_type/distribution").json()
    assert {c["value"]: c["count"] for c in body["categories"]} == {"COMMON_STOCK": 3, "ETF": 1}
    label = client.get("/features/feature.liquidity_class/distribution").json()
    assert label["session"] == "2022-11-23"
    assert {c["value"]: c["count"] for c in label["categories"]} == {
        "HIGH": 2, "MEDIUM": 1, "LOW": 1,
    }  # fmt: skip
    earlier = client.get("/features/feature.liquidity_class/distribution",
                         params={"date": "2022-11-22"}).json()  # fmt: skip
    assert earlier["session"] == "2022-11-22"  # no option liquidity that day: UNKNOWN
    assert {c["value"] for c in earlier["categories"]} == {"UNKNOWN"}
    pct = client.get("/features/feature.pct_from_high_52w/distribution").json()
    assert (pct["count"], pct["nulls"]) == (4, 4)  # no 52-week range stored
    assert client.get("/features/feature.near_52w/distribution", params={"date": "2020-01-01"}
                      ).status_code == 404  # fmt: skip


def test_distribution_not_found(client: TestClient) -> None:
    assert client.get("/features/rollup.nope@v1.x/distribution").status_code == 404
    unstored = "/features/rollup.earnings@v1.earnings_time/distribution"
    assert client.get(unstored).status_code == 404
