import ipaddress
import os
import socket
import subprocess
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, settings

from algotrade.data import StoreReader
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from algotrade_api.deps import ReadStore
from algotrade_ingestion.tasks.maintenance.golden import load_golden
from algotrade_ingestion.tasks.reference import reference_diff
from algotrade_sources.framework.base import FixtureSource
from algotrade_sources.framework.registry import fixture_source
from tests.helpers.api_store import api_store
from tests.helpers.ingest_fakes import task_ctx

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = REPO_ROOT / "datasets" / "golden"

# HYPOTHESIS_PROFILE=nightly runs far more examples on the scheduled workflow.
settings.register_profile("dev", max_examples=30, deadline=None)
settings.register_profile("ci", max_examples=100, deadline=None, print_blob=True)
settings.register_profile(
    "nightly", max_examples=1000, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))


@pytest.fixture(autouse=True)
def strict_reference_events(monkeypatch: pytest.MonkeyPatch) -> None:
    """A universe build that would write two ``events/reference_change`` rows under one key
    fails the test instead of being deduplicated (production keeps one and counts it)."""
    monkeypatch.setattr(reference_diff, "STRICT", True)


@pytest.fixture(scope="session")
def golden_source() -> FixtureSource:
    """The committed golden CSVs, as the source registry builds them."""
    return fixture_source("synthetic", GOLDEN_DIR)


@pytest.fixture(scope="session")
def golden_reader(golden_source: FixtureSource) -> StoreReader:
    """The golden datasets loaded through the real ingestion job into an in-memory store."""
    backend = MemoryBackend()
    load_golden(task_ctx(StoreWriter(backend)), golden_source)
    return StoreReader(backend)


@pytest.fixture(scope="session")
def api_golden(golden_source: FixtureSource) -> tuple[ReadStore, dict[str, str]]:
    """The golden store plus one session of everything a page shows (API and read-model tests)
    -> (the store, the run ids the tests look up)."""
    return api_store(golden_source)


@pytest.fixture(scope="session")
def golden_url(tmp_path_factory: pytest.TempPathFactory, golden_source: FixtureSource) -> str:
    """A local (Parquet) fixture store with the golden datasets, for CLI tests."""
    root = tmp_path_factory.mktemp("golden-store")
    load_golden(task_ctx(StoreWriter(LocalBackend(root))), golden_source)
    return f"file://{root}"


@pytest.fixture(autouse=True)
def _no_live_vendor_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never reach live vendors, even if a developer's .env holds real keys."""
    monkeypatch.setenv("ALGOTRADE_MASSIVE_API_KEY", "")
    monkeypatch.setenv("ALGOTRADE_SEC_CONTACT", "")
    monkeypatch.setenv("ALGOTRADE_FRED_API_KEY", "")
    monkeypatch.setenv("ALGOTRADE_TIINGO_API_KEY", "")


os.environ["ALGOTRADE_LLM"] = "off"  # the whole run, before any fixture: no real model call


@pytest.fixture(autouse=True)
def _no_real_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """No real model call in a test, ever (owner rule 2026-10-08; ADR 0041 amendment). Two
    layers: ``ALGOTRADE_LLM=off`` makes ``open_text_model`` return ``None`` whatever a
    ``llm.local.toml`` or ``.env`` holds, and starting any process whose program is ``claude``
    (the ``claude-cli`` provider's child, which does its own networking and so escapes the socket
    guard) raises. Tests of the adapter inject a fake runner."""
    monkeypatch.setenv("ALGOTRADE_LLM", "off")
    real_init = subprocess.Popen.__init__

    def init(self: "subprocess.Popen[Any]", args: Any, *a: Any, **kw: Any) -> None:
        first = args if isinstance(args, str | bytes | os.PathLike) else (list(args) or [""])[0]
        words = os.fsdecode(first).split() if kw.get("shell") else [os.fsdecode(first)]
        if words and Path(words[0]).name == "claude":
            raise RuntimeError(
                "a real Claude CLI call is refused in tests (owner rule 2026-10-08): "
                "inject a fake runner into ClaudeCli"
            )
        real_init(self, args, *a, **kw)

    monkeypatch.setattr(subprocess.Popen, "__init__", init)


def _is_loopback(host: object) -> bool:
    if host in ("localhost", b"localhost"):
        return True
    try:
        return ipaddress.ip_address(
            host.decode() if isinstance(host, bytes) else str(host)
        ).is_loopback
    except ValueError:
        return False


@pytest.fixture(autouse=True)
def _block_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """CI never calls the network: a real socket connection fails the test. Unix sockets are
    fine; ``@pytest.mark.allow_localhost`` allows loopback (a test's own server);
    ``@pytest.mark.allow_network`` allows anything."""
    if request.node.get_closest_marker("allow_network"):
        return
    loopback_ok = request.node.get_closest_marker("allow_localhost") is not None
    real_connect, real_connect_ex = socket.socket.connect, socket.socket.connect_ex

    def _check(sock: socket.socket, address: object) -> None:
        if sock.family == getattr(socket, "AF_UNIX", None):
            return
        host = address[0] if isinstance(address, tuple) and address else address
        if loopback_ok and _is_loopback(host):
            return
        sock.close()  # a client that only catches OSError would leak it
        raise RuntimeError(
            f"network blocked in tests: connect to {address!r}; mark the test "
            "@pytest.mark.allow_localhost (own loopback server) or use a recorded fixture"
        )

    def connect(self: socket.socket, address: object) -> None:
        _check(self, address)
        real_connect(self, address)

    def connect_ex(self: socket.socket, address: object) -> int:
        _check(self, address)
        return real_connect_ex(self, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
