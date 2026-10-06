"""Vendor HTTP (responsibility ``vendor-http``): transport, polite retries, a cap on total
retry time per request and a circuit breaker per vendor.

Sources fetch through one ``Http`` client each, built by ``sources/framework/registry.py``: the
transport (headers carry credentials), the vendor's shared ``Limiter`` (every attempt waits
on it), the ``RetryPolicy`` and the vendor's ``CircuitBreaker``. Tests build ``Http`` around
a fake transport, so no test needs the network.
"""

import gzip
import random
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, Protocol

DEFAULT_USER_AGENT = "algotrade-ingestion/0.1 (+https://github.com/adarbari/algo-trading)"
# api.nasdaq.com rejects non-browser user agents.
BROWSER_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) algotrade-ingestion/0.1"


class HttpError(Exception):
    """``body`` keeps the start of the error response (decompressed) so a source can tell a
    missing object from a block (see ``RetryPolicy.not_found``)."""

    def __init__(self, status: int, retry_after: float | None = None, body: bytes = b"") -> None:
        self.status = status
        self.retry_after = retry_after
        self.body = body
        super().__init__(f"HTTP {status}")


type Transport = Callable[[str], bytes]
type Sleep = Callable[[float], None]


def urllib_transport(
    user_agent: str = DEFAULT_USER_AGENT,
    timeout: float = 60.0,
    headers: dict[str, str] | None = None,
) -> Transport:
    """``headers`` carry credentials (e.g. ``Authorization``) so keys never appear in URLs.
    Responses may come gzip-compressed (SEC company facts: ~10x smaller); bodies are returned
    decompressed, as the vendor sent them before encoding."""
    all_headers = {"User-Agent": user_agent, "Accept-Encoding": "gzip", **(headers or {})}

    def get(url: str) -> bytes:
        request = urllib.request.Request(url, headers=all_headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body: bytes = response.read()
                encoding = (response.headers.get("Content-Encoding") or "").lower()
                return gzip.decompress(body) if encoding == "gzip" else body
        except urllib.error.HTTPError as exc:
            header = exc.headers.get("Retry-After") if exc.headers else None
            retry = float(header) if header and header.isdigit() else None
            raise HttpError(exc.code, retry, _error_body(exc)) from exc

    return get


type JsonTransport = Callable[[str, bytes], bytes]


def json_post_transport(
    user_agent: str = DEFAULT_USER_AGENT,
    timeout: float = 60.0,
    headers: dict[str, str] | None = None,
) -> JsonTransport:
    """POST a JSON body to a URL and return the response body (a text model's chat endpoint,
    ADR 0041). ``headers`` carry credentials, as for ``urllib_transport``; a non-2xx answer is
    an ``HttpError`` with the start of the body."""
    all_headers = {
        "User-Agent": user_agent,
        "Content-Type": "application/json",
        "Accept": "application/json",
        **(headers or {}),
    }

    def post(url: str, body: bytes) -> bytes:
        request = urllib.request.Request(url, data=body, headers=all_headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                answer: bytes = response.read()
                return answer
        except urllib.error.HTTPError as exc:
            header = exc.headers.get("Retry-After") if exc.headers else None
            retry = float(header) if header and header.isdigit() else None
            raise HttpError(exc.code, retry, _error_body(exc)) from exc

    return post


def _error_body(exc: urllib.error.HTTPError) -> bytes:
    try:
        body = exc.read(4096)
        if (exc.headers.get("Content-Encoding") or "").lower() == "gzip":
            body = gzip.decompress(body)
        return body[:1024]
    except (OSError, EOFError):
        return b""


@dataclass(frozen=True)
class RetryPolicy:
    tries: int = 7
    base_delay: float = 1.5
    max_delay: float = 60.0
    # Only 404 means "no such chain". 403 may mean we are blocked, so it must surface as an
    # error, never as "this ticker has no options" (fail closed).
    give_up_statuses: frozenset[int] = frozenset({404})
    max_total_s: float | None = None  # cap on time spent retrying one request
    # A vendor-specific test for error responses that mean "no such object" (e.g. Cboe's CDN
    # answers a missing chain with S3's 403 AccessDenied). Such a response returns None and
    # does not count towards the circuit breaker. Anything it does not match stays an error.
    not_found: Callable[[HttpError], bool] | None = None

    def gives_up(self, exc: HttpError) -> bool:
        return exc.status in self.give_up_statuses or (
            self.not_found is not None and self.not_found(exc)
        )


class CircuitOpenError(RuntimeError):
    """The vendor failed too many requests in a row this run; remaining items fail fast."""


class CircuitBreaker:
    """Opens after ``threshold`` consecutive 403 / 5xx responses from one vendor (a block or
    an outage) and stays open for the rest of the run, so the remaining items fail at once
    with a clear status instead of each burning its retries. ``threshold <= 0``: never opens."""

    def __init__(self, name: str, threshold: int) -> None:
        self.name, self.threshold = name, threshold
        self._failures = 0
        self._lock = threading.Lock()

    @property
    def open(self) -> bool:
        return 0 < self.threshold <= self._failures

    def check(self) -> None:
        if self.open:
            raise CircuitOpenError(
                f"{self.name}: circuit open after {self._failures} consecutive 403/5xx "
                "responses; skipping the rest of this run"
            )

    def record(self, status: int | None) -> None:
        """One response: ``None`` = success, else the HTTP status."""
        with self._lock:
            if status is not None and (status == 403 or status >= 500):
                self._failures += 1
            else:
                self._failures = 0


class Pacer(Protocol):
    """A vendor limiter (``sources/framework/limiter.py``) as a fixed pace: wait for a slot,
    or hold every process (session sources such as IB Gateway use only this)."""

    def wait(self) -> float: ...

    def hold(self, seconds: float) -> None: ...


class AdaptivePacer(Pacer, Protocol):
    """What HTTP fetches use: every attempt waits on the limiter and reports how it went, so
    the pace adapts (Retry-After holds, back-off, error-rate slowdown, recovery)."""

    def throttled(self, seconds: float) -> None: ...

    def record(self, outcome: Literal["ok", "missing", "error"]) -> None: ...


def get_with_retry(
    transport: Transport,
    url: str,
    policy: RetryPolicy,
    sleep: Sleep = time.sleep,
    *,
    limiter: AdaptivePacer | None = None,
    breaker: CircuitBreaker | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> bytes | None:
    """Fetch ``url``. Returns ``None`` for give-up statuses (e.g. 404: no such chain).

    Every attempt waits on ``limiter`` and reports its outcome to it. A 429 waits out
    Retry-After (or an exponential back-off): through ``limiter.throttled`` when there is a
    limiter, so every thread and process holds, else by sleeping here. Other failures back off
    linearly. Gives up after ``policy.tries`` attempts, or when the next wait would pass
    ``policy.max_total_s``, or when ``breaker`` opens.
    """
    started = clock()
    last_error: Exception | None = None
    for attempt in range(policy.tries):
        if breaker is not None:
            breaker.check()
        if limiter is not None:
            limiter.wait()
        pause = True  # sleep here before the next attempt (False: the limiter holds instead)
        try:
            body = transport(url)
        except HttpError as exc:
            missing = policy.gives_up(exc)
            if breaker is not None:
                breaker.record(None if missing else exc.status)
            if missing:
                _report(limiter, "missing")
                return None
            last_error = exc
            delay, pause = _backoff(exc, policy, attempt, limiter)
        except (OSError, TimeoutError) as exc:
            last_error, delay = exc, _linear(policy, attempt)
            _report(limiter, "error")
        else:
            if breaker is not None:
                breaker.record(None)
            _report(limiter, "ok")
            return body
        if attempt + 1 == policy.tries:
            break
        if policy.max_total_s is not None and clock() - started + delay > policy.max_total_s:
            raise RuntimeError(f"giving up on {url} after {clock() - started:.0f}s: {last_error}")
        if pause:
            sleep(delay)
    raise RuntimeError(f"giving up on {url}: {last_error}")


def _backoff(
    exc: HttpError, policy: RetryPolicy, attempt: int, limiter: AdaptivePacer | None
) -> tuple[float, bool]:
    """(delay before the next attempt, whether to sleep it here). A 429 waits out Retry-After
    (else an exponential back-off) through the limiter, which holds every process; other
    errors back off linearly here."""
    if exc.status != 429:
        _report(limiter, "error")
        return _linear(policy, attempt), True
    delay = exc.retry_after or min(policy.max_delay, 5 * 2**attempt)
    if limiter is None:
        return delay, True
    limiter.throttled(delay)
    return delay, False


def _report(limiter: AdaptivePacer | None, outcome: Literal["ok", "missing", "error"]) -> None:
    if limiter is not None:
        limiter.record(outcome)


def _linear(policy: RetryPolicy, attempt: int) -> float:
    return min(policy.max_delay, policy.base_delay * (attempt + 1) + random.uniform(0, 0.5))


@dataclass
class Http:
    """What a source fetches through. Built by the registry; sources never pace themselves."""

    transport: Transport
    policy: RetryPolicy = field(default_factory=RetryPolicy)
    limiter: AdaptivePacer | None = None
    breaker: CircuitBreaker | None = None
    sleep: Sleep = time.sleep

    def get(self, url: str) -> bytes | None:
        return get_with_retry(
            self.transport,
            url,
            self.policy,
            self.sleep,
            limiter=self.limiter,
            breaker=self.breaker,
        )

    def cool_down(self, seconds: float) -> None:
        """Ask the vendor's limiter (shared across processes) to pause new requests."""
        if self.limiter is not None:
            self.limiter.hold(seconds)
