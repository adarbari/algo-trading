"""``/chains/{id}/live``: live quotes of one expiry, the stored chain as the fallback."""

from datetime import date

import pandas as pd
from fastapi.testclient import TestClient

from algotrade.config.site.settings import IbkrSettings
from algotrade.services.explore.store import ReadStore
from algotrade.services.live.quotes import LiveQuotes
from algotrade_api.deps import ApiSettings
from algotrade_api.main import create_app


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
