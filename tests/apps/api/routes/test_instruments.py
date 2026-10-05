from datetime import date

import pandas as pd
from fastapi.testclient import TestClient

from algotrade.config.site.settings import IbkrSettings
from algotrade.services.explore.store import ReadStore
from algotrade.services.live.quotes import LiveQuotes
from algotrade_api.deps import ApiSettings
from algotrade_api.main import create_app


def test_detail_by_id_or_ticker(client: TestClient) -> None:
    by_id = client.get("/instruments/EQ:AAA").json()
    by_ticker = client.get("/instruments/aaa").json()
    assert by_id == by_ticker
    assert by_id["reference"]["symbol"] == "AAA"
    assert by_id["company"]["sector"] == "Technology"
    assert by_id["reference"]["description"] == "AAA makes widgets."
    assert by_id["reference"]["description_source"] == "massive_overview"
    assert by_id["reference"]["homepage_url"] == "https://aaa.example"
    assert by_id["reference"]["total_employees"] == 1200
    assert by_id["features"]["rollup.price_stats@v2.close"] == 101.0
    assert by_id["feature_sessions"]["iv30@v1"] == "2022-11-23"
    assert by_id["features"]["feature.liquidity_class"] == "HIGH"
    assert by_id["features"]["feature.option_tier"] == "A"
    assert by_id["feature_sessions"]["expressions"] == "2022-11-23"


def test_detail_without_company_and_unknown_instrument(client: TestClient) -> None:
    bbb = client.get("/instruments/BBB").json()
    assert bbb["company"] is None
    assert bbb["reference"]["description"] is None  # nothing stored: the key is still there
    assert client.get("/instruments/NOPE").status_code == 404


def test_bars_are_split_adjusted_unless_asked(client: TestClient) -> None:
    window = {"from": "2022-05-27", "to": "2022-06-02"}
    adjusted = client.get("/instruments/AAA/bars", params=window).json()
    raw = client.get("/instruments/AAA/bars", params={**window, "adjust": "none"}).json()
    assert adjusted["adjustment"] == "splits"
    before = [b for b in adjusted["items"] if b["session_date"] < "2022-06-01"]
    raw_before = [b for b in raw["items"] if b["session_date"] < "2022-06-01"]
    assert before and before[0]["close"] == raw_before[0]["close"] / 2
    assert client.get("/instruments/AAA/bars", params={"adjust": "x"}).status_code == 422


def test_bars_default_to_the_last_year_and_empty_outside_data(client: TestClient) -> None:
    body = client.get("/instruments/AAA/bars").json()
    assert (body["start"], body["end"]) == ("2021-11-23", "2022-11-23")
    assert len(body["items"]) > 200
    empty = client.get("/instruments/AAA/bars", params={"from": "2010-01-01", "to": "2010-02-01"})
    assert empty.json()["items"] == []


def test_events_across_tables(client: TestClient) -> None:
    events = client.get("/instruments/AAA/events").json()
    assert [e["table"] for e in events] == ["events/split", "events/dividend"]
    assert events[0]["values"]["ratio"] == 2.0
    later = client.get("/instruments/AAA/events", params={"from": "2022-07-01"}).json()
    assert [e["table"] for e in later] == ["events/dividend"]


def test_feature_series(client: TestClient) -> None:
    names = "rollup.price_stats@v2.close,rollup.price_stats@v2.hv20"
    body = client.get("/instruments/AAA/features", params={"names": names}).json()
    assert body["names"] == names.split(",")
    assert [i["session_date"] for i in body["items"]] == ["2022-11-22", "2022-11-23"]
    assert body["items"][1]["rollup.price_stats@v2.close"] == 101.0
    every = client.get("/instruments/AAA/features").json()
    assert len(every["names"]) > 20 and "feature.liquidity_class" in every["names"]
    label = client.get("/instruments/BBB/features", params={"names": "feature.liquidity_class"})
    assert [i["feature.liquidity_class"] for i in label.json()["items"]] == ["UNKNOWN", "MEDIUM"]
    ratio = client.get("/instruments/BBB/features", params={"names": "feature.iv_hv_ratio"})
    assert [i["feature.iv_hv_ratio"] for i in ratio.json()["items"]] == [None, None]  # no IV


def test_feature_series_rejects_unknown_or_reference_fields(client: TestClient) -> None:
    bad = client.get("/instruments/AAA/features", params={"names": "rollup.nope@v1.x"})
    assert bad.status_code == 404
    ref = client.get("/instruments/AAA/features", params={"names": "instrument.symbol"})
    assert ref.status_code == 404


def test_chain_with_quotes_status_and_our_iv(client: TestClient) -> None:
    body = client.get("/chains/AAA").json()
    assert (body["underlying_id"], body["session"], body["status"]) == (
        "EQ:AAA",
        "2022-11-23",
        "OK",
    )
    assert body["expiries"] == ["2022-12-23", "2023-01-22"]
    assert body["strikes"][0] == 80.0
    assert len(body["quotes"]) == 2 * 9 * 2
    assert body["underlying"]["iv30"] == 25.0
    assert body["our_iv"]["iv30"] == 0.24
    one = client.get("/chains/AAA", params={"expiry": "2022-12-23"}).json()
    assert {q["expiry"] for q in one["quotes"]} == {"2022-12-23"}


def test_chain_not_found(client: TestClient) -> None:
    assert client.get("/chains/BBB").status_code == 404  # no chain for BBB
    assert client.get("/chains/AAA", params={"date": "2020-01-02"}).status_code == 404


def test_live_chain_serves_the_stored_chain_when_live_quotes_are_off(client: TestClient) -> None:
    body = client.get("/chains/AAA/live", params={"expiry": "2022-12-23"}).json()
    assert (body["source"], body["status"], body["delayed"]) == ("stored", "DISABLED", True)
    assert body["strikes"] == [80.0, 85.0, 90.0, 95.0, 100.0, 105.0, 110.0, 115.0, 120.0]
    assert len(body["quotes"]) == 18 and body["quotes"][0]["instrument_id"].endswith("C80")
    named = client.get("/chains/AAA/live?expiry=2022-12-23&strikes=100&strikes=95").json()
    assert named["strikes"] == [95.0, 100.0]


def test_live_chain_errors(client: TestClient) -> None:
    assert client.get("/chains/AAA/live").status_code == 422  # the expiry is required
    assert client.get("/chains/AAA/live", params={"expiry": "2022-12-30"}).status_code == 404
    assert client.get("/chains/BBB/live", params={"expiry": "2022-12-23"}).status_code == 404
    bad = client.get("/chains/AAA/live", params={"expiry": "2022-12-23", "strikes": 81})
    assert bad.status_code == 400 and "not in the stored chain" in bad.json()["detail"]


def test_live_chain_from_a_feed(explore: tuple[ReadStore, dict[str, str]]) -> None:
    class Feed:
        market_data_type = 1

        def quotes(self, symbol: str, expiry: date, strikes: list[float]) -> pd.DataFrame:
            return pd.DataFrame(
                [{"strike": k, "right": r, "listed": True, "conid": 1, "bid": 2.0, "ask": 2.1,
                  "last": 2.05, "close": 2.0, "volume": 9.0, "iv": 0.25, "delta": 0.5}
                 for k in strikes for r in ("C", "P")]
            )  # fmt: skip

        def close(self) -> None:
            return None

    live = LiveQuotes(Feed(), None, IbkrSettings(live_strikes=2))
    with TestClient(create_app(ApiSettings("memory://", "config"), explore[0], live=live)) as app:
        body = app.get("/chains/AAA/live", params={"expiry": "2022-12-23"}).json()
    assert (body["source"], body["status"], body["delayed"]) == ("ibkr", "LIVE", False)
    assert body["strikes"] == [95.0, 100.0] and body["quotes"][0]["last"] == 2.05
