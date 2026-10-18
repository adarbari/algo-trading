"""The FINRA sources against hand-built payloads (no network): the filter POST, the pager,
and both normalisations."""

import json
from datetime import UTC, datetime

import pytest

from algotrade_sources.framework.base import FetchRequest
from algotrade_sources.framework.http import RetryPolicy
from algotrade_sources.vendors.finra import client
from algotrade_sources.vendors.finra.short_interest import TABLE as INTEREST
from algotrade_sources.vendors.finra.short_interest import FinraShortInterest
from algotrade_sources.vendors.finra.short_volume import TABLE as VOLUME
from algotrade_sources.vendors.finra.short_volume import FinraShortVolume
from tests.helpers.finra import payloads
from tests.helpers.ingest_fakes import http_for


def test_the_url_filter_becomes_the_post_body(monkeypatch: pytest.MonkeyPatch) -> None:
    posted: list[tuple[str, dict]] = []

    def fake_post(user_agent: str, headers: dict[str, str] | None = None, **_: object):
        def post(url: str, body: bytes) -> bytes:
            posted.append((url, json.loads(body)))
            return b"[]"

        return post

    monkeypatch.setattr(client, "json_post_transport", fake_post)
    get = client.query_transport({})
    get(client.url("consolidatedShortInterest", "settlementDate", "2026-09-30", 5000))
    assert posted == [
        (
            f"{client.HOST}/consolidatedShortInterest",
            {
                "limit": 5000,
                "offset": 5000,
                "compareFilters": [
                    {
                        "compareType": "EQUAL",
                        "fieldName": "settlementDate",
                        "fieldValue": "2026-09-30",
                    }
                ],
            },
        )
    ]


def test_a_partition_is_read_page_by_page(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client, "PAGE", 2)
    rows = [{"n": i} for i in range(5)]
    offsets: list[int] = []

    def transport(url: str) -> bytes:
        offset = int(url.split("offset=")[1].split("&", maxsplit=1)[0])
        offsets.append(offset)
        return json.dumps(rows[offset : offset + 2]).encode()

    payload = client.read_partition(http_for(transport), "d", "f", "v")
    assert payload is not None and json.loads(payload) == rows
    assert offsets == [0, 2, 4]  # the short third page ends the read


def test_an_empty_partition_is_nothing_there() -> None:
    http = http_for(lambda url: b"", RetryPolicy(tries=1))
    assert client.read_partition(http, "d", "f", "v") is None


def test_a_page_that_is_not_a_list_is_an_error() -> None:
    with pytest.raises(ValueError, match="expected a JSON list"):
        client.read_partition(http_for(lambda url: b'{"message": "x"}'), "d", "f", "v")


def test_short_interest_rows() -> None:
    source = FinraShortInterest(http_for(lambda url: payloads.short_interest()))
    request = FetchRequest("2026-09-30")
    payload = source.fetch(request)
    assert payload is not None
    frame = source.normalize(request, payload).tables[INTEREST]  # type: ignore[union-attr]
    assert frame["symbol"].tolist() == ["AAA", "BBB", "OTCX"]
    aaa = frame.iloc[0]
    assert aaa["short_position"] == 5_240_309 and aaa["change_shares"] == 161_680
    assert aaa["days_to_cover"] == pytest.approx(1.78)
    assert aaa["ts"] == datetime(2026, 9, 30, tzinfo=UTC)
    assert "known_from" not in frame.columns  # the task decides it (schedule.py)
    assert frame["revision_flag"].isna().tolist() == [True, True, False]
    assert frame["average_daily_volume"].tolist() == [2_950_874, 0, 3]


def test_short_volume_sums_the_facilities() -> None:
    source = FinraShortVolume(http_for(lambda url: payloads.short_volume()))
    request = FetchRequest("2026-10-16")
    payload = source.fetch(request)
    assert payload is not None
    frame = source.normalize(request, payload).tables[VOLUME]  # type: ignore[union-attr]
    assert frame["symbol"].tolist() == ["AAA", "BBB"]  # the blank symbol is dropped
    aaa = frame.iloc[0]
    assert (aaa["short_volume"], aaa["short_exempt_volume"], aaa["total_volume"]) == (500, 5, 1500)
    assert aaa["facilities"] == 2 and frame.iloc[1]["facilities"] == 1
    assert aaa["ts"] == datetime(2026, 10, 16, tzinfo=UTC)


def test_an_empty_payload_normalizes_to_no_rows() -> None:
    for source, table in (
        (FinraShortInterest(http_for(lambda url: b"[]")), INTEREST),
        (FinraShortVolume(http_for(lambda url: b"[]")), VOLUME),
    ):
        key = "2026-10-16"
        assert source.normalize(FetchRequest(key), b"[]").tables[table].empty  # type: ignore[union-attr]
