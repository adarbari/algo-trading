"""FMP's probe endpoints, and the key staying out of every URL, message and raw path."""

import http.server
import threading
import tomllib
import traceback
import urllib.error
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest

from algotrade.config.site.settings import SourcesSettings
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.framework.run import IngestRun
from algotrade_sources.framework import registry
from algotrade_sources.framework.base import FetchRequest, Source
from algotrade_sources.framework.http import (
    GaveUpError,
    Http,
    HttpError,
    RetryPolicy,
    urllib_transport,
    with_query_param,
)
from algotrade_sources.framework.registry import build_sources
from algotrade_sources.vendors.fmp.probe import BROAD_SYMBOL, ENDPOINTS, PROBE_SYMBOL
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import task_ctx

KEY = "k3y-d0-n0t-l34k-9f2c"
TARGETS = (REPO_ROOT / "tests/fixtures/sources/fmp/price_target_consensus_aapl.json").read_bytes()
SITE = REPO_ROOT / "config" / "site" / "sources.toml"


def built(tmp_path: Path, name: str = "fmp_targets") -> Source:
    """The registry's own build of an FMP source (its transport is what the test patches)."""
    settings = SourcesSettings.from_document(tomllib.loads(SITE.read_text()))
    env = {"ALGOTRADE_FMP_API_KEY": KEY}.get
    return build_sources(settings, env, [name], tmp_path).sources[name]


def test_the_probe_names_one_endpoint_each_for_a_mega_cap_and_a_scope_mid_cap() -> None:
    names = {"quote", "estimates_annual", "estimates_quarter", "price_targets"}
    names |= {"ratings_summary", "grades"}
    assert set(ENDPOINTS) == names | {f"{n}@broad" for n in names}
    for name, url in ENDPOINTS.items():
        symbol = BROAD_SYMBOL if name.endswith("@broad") else PROBE_SYMBOL
        assert f"symbol={symbol}" in url and "apikey" not in url  # the transport adds the key
    assert (PROBE_SYMBOL, BROAD_SYMBOL) == ("AAPL", "CHWY")


def test_the_broad_name_is_in_the_event_scope_list() -> None:
    scope = tomllib.loads((REPO_ROOT / "config/site/events/scope.toml").read_text())
    assert BROAD_SYMBOL in {entry["symbol"] for entry in scope["name"]}


def test_the_registry_adds_the_key_to_the_query_and_the_source_never_sees_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []
    monkeypatch.setattr(
        registry, "urllib_transport", lambda headers=None: lambda url: seen.append(url) or TARGETS
    )
    source = built(tmp_path)
    assert source.fetch(FetchRequest("AAPL")) == TARGETS
    assert seen == [
        f"https://financialmodelingprep.com/stable/price-target-consensus?symbol=AAPL&apikey={KEY}"
    ]


def test_a_refused_request_exception_never_contains_the_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing(headers: dict[str, str] | None = None) -> Callable[[str], bytes]:
        def get(url: str) -> bytes:
            assert KEY in url  # the transport is the one place that holds it
            raise HttpError(402, body=b"Premium Query Parameter")

        return get

    monkeypatch.setattr(registry, "urllib_transport", failing)
    source = built(tmp_path)
    with pytest.raises(HttpError) as raised:
        source.fetch(FetchRequest("AAPL"))
    assert KEY not in str(raised.value) and KEY not in repr(raised.value)


@pytest.mark.parametrize(
    "error",
    [HttpError(503), urllib.error.URLError("connection reset"), TimeoutError("timed out")],
)
def test_a_request_given_up_on_never_names_the_key(error: Exception) -> None:
    def transport(url: str) -> bytes:
        assert KEY in url
        raise error

    http = Http(
        with_query_param(transport, "apikey", KEY),
        RetryPolicy(tries=2),
        sleep=lambda s: None,
    )
    with pytest.raises(GaveUpError) as raised:
        http.get("https://financialmodelingprep.com/stable/quote?symbol=AAPL")
    text = f"{raised.value} {raised.value!r} {raised.value.__cause__!r}"
    assert KEY not in text and "apikey" not in text


def test_the_raw_file_of_a_fetch_is_named_by_the_symbol_never_the_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(registry, "urllib_transport", lambda headers=None: lambda url: TARGETS)
    source = built(tmp_path / "limits")
    writer = StoreWriter(LocalBackend(tmp_path / "data"))
    with IngestRun(task_ctx(writer), "t", date(2026, 10, 16)) as run:
        run.fetch(source, FetchRequest("AAPL"))
    paths = [str(p) for p in (tmp_path / "data").rglob("*") if p.is_file()]
    assert any("source=fmp" in p for p in paths)
    assert not [p for p in paths if KEY in p or "apikey" in p.lower()]


@pytest.mark.allow_localhost
def test_the_real_transport_stack_never_prints_the_key_of_a_refused_request() -> None:
    """urllib's own HTTPError, through ``urllib_transport`` + ``with_query_param``: no field the
    traceback or the message prints carries the URL's query."""

    class Refuse(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(402)
            self.end_headers()
            self.wfile.write(b"Premium Query Parameter")

        def log_message(self, *args: object) -> None:
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Refuse)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        get = with_query_param(urllib_transport(), "apikey", KEY)
        with pytest.raises(HttpError) as raised:
            get(f"http://127.0.0.1:{server.server_port}/stable/quote?symbol=AAPL")
    finally:
        server.shutdown()
        server.server_close()
    printed = "".join(traceback.format_exception(raised.value))
    assert raised.value.status == 402 and raised.value.body == b"Premium Query Parameter"
    assert KEY not in printed and "apikey" not in printed
    assert raised.value.__cause__ is None  # urllib's HTTPError holds the keyed URL: not chained
