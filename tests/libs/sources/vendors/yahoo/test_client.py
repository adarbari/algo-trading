"""Yahoo's transport over a fake ``YfData``: error mapping, one lazy session, and no import of
``yfinance`` until the first request."""

import os
import subprocess
import sys
from types import SimpleNamespace
from typing import Any

import pytest

from algotrade_sources.framework.http import HttpError, RetryPolicy, get_with_retry
from algotrade_sources.vendors.yahoo.client import refused, url, yahoo_transport


class FakeSession:
    def __init__(self, outcome: Any) -> None:
        self.outcome, self.requests = outcome, []

    def get(self, url_: str, params: dict[str, str] | None = None, timeout: float = 30) -> Any:
        self.requests.append((url_, params, timeout))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def answer(status: int, body: bytes = b"{}", headers: dict[str, str] | None = None) -> Any:
    return SimpleNamespace(status_code=status, content=body, headers=headers or {})


def transport(outcome: Any) -> tuple[Any, FakeSession, list[str]]:
    fake, dirs = FakeSession(outcome), []

    def make(cache_dir: str) -> FakeSession:
        dirs.append(cache_dir)
        return fake

    return yahoo_transport({}, "var/cache/test", make), fake, dirs


def test_the_url_query_becomes_params_and_the_body_is_returned() -> None:
    get, fake, dirs = transport(answer(200, b'{"quoteSummary": {}}'))
    assert get(url("ARX")) == b'{"quoteSummary": {}}'
    base, params, _ = fake.requests[0]
    assert base == "https://query2.finance.yahoo.com/v10/finance/quoteSummary/ARX"
    assert params == {
        "modules": (
            "financialData,earningsTrend,recommendationTrend,calendarEvents,upgradeDowngradeHistory"
        ),
        "formatted": "false",
    }
    get(url("ARX"))
    assert dirs == ["var/cache/test"]  # one session, built once, with the configured cache dir


def test_a_non_200_answer_is_an_http_error_with_its_body_and_retry_after() -> None:
    get, _, _ = transport(answer(429, b"slow down", {"Retry-After": "7"}))
    with pytest.raises(HttpError) as caught:
        get(url("ARX"))
    assert (caught.value.status, caught.value.retry_after, caught.value.body) == (
        429, 7.0, b"slow down",
    )  # fmt: skip


def test_a_404_is_refused_and_a_401_is_an_error_to_retry() -> None:
    for status, rejected in ((404, True), (401, False)):
        get, _, _ = transport(answer(status, b"x"))
        with pytest.raises(HttpError) as caught:
            get(url("ARX"))
        assert refused(caught.value) is rejected


def test_a_connection_error_is_transient_and_retried() -> None:
    attempts = []

    class Flaky(FakeSession):
        def get(self, url_: str, params: Any = None, timeout: float = 30) -> Any:
            attempts.append(1)
            if len(attempts) == 1:
                raise ConnectionError("reset")  # curl_cffi's errors are OSErrors too
            return answer(200, b"ok")

    get = yahoo_transport({}, "x", lambda cache: Flaky(None))
    assert get_with_retry(get, url("ARX"), RetryPolicy(tries=2), sleep=lambda s: None) == b"ok"
    assert len(attempts) == 2


def test_yfinance_rate_limit_is_a_429_and_any_other_failure_an_os_error() -> None:
    class YFRateLimitError(Exception):
        pass

    get, _, _ = transport(YFRateLimitError("too many"))
    with pytest.raises(HttpError) as caught:
        get(url("ARX"))
    assert caught.value.status == 429
    get, _, _ = transport(ValueError("boom"))
    with pytest.raises(OSError, match="ValueError: boom"):
        get(url("ARX"))


def test_importing_the_registry_does_not_import_yfinance() -> None:
    code = (
        "import sys; import algotrade_sources.framework.registry as r; "
        "r.SOURCES['yahoo_analyst']; assert 'yfinance' not in sys.modules, 'imported'"
    )
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}  # this worktree's code
    argv = [sys.executable, "-c", code]
    done = subprocess.run(argv, check=False, capture_output=True, text=True, env=env)
    assert done.returncode == 0, done.stderr
