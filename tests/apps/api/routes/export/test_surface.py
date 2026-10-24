"""``GET /files/{surface}.csv`` (ADR 0082 decision 6): the file has the rows the page's loader
serves for the same ``f``, a personal value is ``LICENCE`` to a non-holder over HTTP too, the
notice is the first line, one audit line is logged per export, a refused filter is a 403, an
unknown surface a 404, and the route is authenticated like every other."""

import csv
import io
import logging
import os
import subprocess
import sys
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from algotrade.config.site.users import Role, UserRecord
from algotrade.config.user import UserContext
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade_api.deps import ApiSettings
from algotrade_api.main import create_app
from tests.helpers.api_store import StubAuthenticator, store_over
from tests.unit.services.read.screens.conftest import CONFIGS, screens_store

Make = Callable[[str, Role], TestClient]


@pytest.fixture
def make() -> Make:
    backend: MemoryBackend = screens_store()

    def build(user: str, role: Role) -> TestClient:
        app = create_app(
            ApiSettings("memory://", "config"),
            store_over(backend, MemoryConfigStore(dict(CONFIGS)), UserContext(user)),
            authenticator=StubAuthenticator(UserRecord(user, role)),
        )
        return TestClient(app)

    return build


def rows(text: str) -> list[dict[str, str]]:
    return list(
        csv.DictReader(io.StringIO("".join(x for x in text.splitlines(True) if x[0] != "#")))
    )


def test_a_personal_value_is_licence_over_http_for_a_non_holder(make: Make) -> None:
    mine = make("me", Role.TRADER).get("/files/screener_results.csv", params={"screener": "alpha"})
    theirs = make("trader", Role.TRADER).get(
        "/files/screener_results.csv", params={"screener": "alpha"}
    )
    assert mine.status_code == theirs.status_code == 200
    assert mine.headers["content-type"].startswith("text/csv")
    assert any("iv30=high" in r["metrics"] for r in rows(mine.text))
    assert "high" not in theirs.text and "iv30=LICENCE" in theirs.text
    assert theirs.text.startswith("# algotrade export, session ")
    assert "for the holder's own use, not for redistribution" in theirs.text.splitlines()[0]


def test_f_filters_the_file_and_one_audit_line_is_logged(
    make: Make, caplog: pytest.LogCaptureFixture
) -> None:
    client = make("me", Role.TRADER)
    with caplog.at_level(logging.INFO, logger="algotrade_api.export"):
        every = client.get("/files/screener_results.csv", params={"screener": "alpha"})
        some = client.get(
            "/files/screener_results.csv", params={"screener": "alpha", "f": "decision:REJECT"}
        )
    assert {r["decision"] for r in rows(some.text)} == {"REJECT"}
    assert len(rows(some.text)) < len(rows(every.text))
    lines = [r.getMessage() for r in caplog.records if r.name == "algotrade_api.export"]
    assert len(lines) == 2 and lines[1].startswith("export viewer=me surface=screener_results ")
    assert f"rows={len(rows(some.text))}" in lines[1] and "licences=" in lines[1]


def test_refused_filter_unknown_surface_and_missing_screener(make: Make) -> None:
    client = make("me", Role.TRADER)
    assert client.get("/files/ideas.csv", params={"f": "nope:1"}).status_code == 403
    assert client.get("/files/nothing.csv").status_code == 404
    assert client.get("/files/screener_results.csv").status_code in (400, 422)


def test_the_file_needs_the_caller_to_be_let_in() -> None:
    class Refuse:
        def authenticate(self, request: object) -> UserRecord:
            from algotrade_api.auth.protocol import UnauthenticatedError  # noqa: PLC0415

            raise UnauthenticatedError("no token")

    app = create_app(
        ApiSettings("memory://", "config"),
        store_over(screens_store(), MemoryConfigStore(dict(CONFIGS)), UserContext("me")),
        authenticator=Refuse(),
    )
    assert TestClient(app).get("/files/ideas.csv").status_code == 401


def test_the_audit_logger_is_configured_by_the_app_not_by_the_test_harness() -> None:
    """Fix for: the audit line was never written in production (the server configures only its own
    loggers, the root is WARNING with no handler): importing the API (as the server does) gives
    the audit logger a handler and INFO; checked in a fresh interpreter, so no test fixture (the
    ``caplog`` level) can mask it."""
    probe = (
        "import logging, algotrade_api.main;"
        "a = logging.getLogger('algotrade_api.export');"
        "print(a.getEffectiveLevel() == logging.INFO and a.isEnabledFor(logging.INFO)"
        " and bool(a.handlers))"
    )
    run = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=True,
        env=dict(os.environ),
    )
    assert run.stdout.strip() == "True"
