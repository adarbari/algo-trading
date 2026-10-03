"""Minimal HTTP transport with polite retries. Injected into sources so tests need no network."""

import random
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

DEFAULT_USER_AGENT = "algotrade-ingestion/0.1 (+https://github.com/adarbari/algo-trading)"
# api.nasdaq.com rejects non-browser user agents.
BROWSER_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) algotrade-ingestion/0.1"


class HttpError(Exception):
    def __init__(self, status: int, retry_after: float | None = None) -> None:
        self.status = status
        self.retry_after = retry_after
        super().__init__(f"HTTP {status}")


type Transport = Callable[[str], bytes]
type Sleep = Callable[[float], None]


def urllib_transport(
    user_agent: str = DEFAULT_USER_AGENT,
    timeout: float = 60.0,
    headers: dict[str, str] | None = None,
) -> Transport:
    """``headers`` carry credentials (e.g. ``Authorization``) so keys never appear in URLs."""
    all_headers = {"User-Agent": user_agent, **(headers or {})}

    def get(url: str) -> bytes:
        request = urllib.request.Request(url, headers=all_headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body: bytes = response.read()
                return body
        except urllib.error.HTTPError as exc:
            header = exc.headers.get("Retry-After") if exc.headers else None
            retry = float(header) if header and header.isdigit() else None
            raise HttpError(exc.code, retry) from exc

    return get


@dataclass(frozen=True)
class RetryPolicy:
    tries: int = 7
    base_delay: float = 1.5
    max_delay: float = 60.0
    # Only 404 means "no such chain". 403 may mean we are blocked, so it must surface as an
    # error, never as "this ticker has no options" (fail closed).
    give_up_statuses: frozenset[int] = frozenset({404})


def get_with_retry(
    transport: Transport, url: str, policy: RetryPolicy, sleep: Sleep = time.sleep
) -> bytes | None:
    """Fetch ``url``. Returns ``None`` for give-up statuses (e.g. 404: no such chain).

    429 honours Retry-After or backs off exponentially; other failures back off linearly.
    """
    last: Exception | None = None
    for attempt in range(policy.tries):
        try:
            return transport(url)
        except HttpError as exc:
            if exc.status in policy.give_up_statuses:
                return None
            last = exc
            if exc.status == 429:
                sleep(exc.retry_after or min(policy.max_delay, 5 * 2**attempt))
                continue
        except (OSError, TimeoutError) as exc:
            last = exc
        sleep(min(policy.max_delay, policy.base_delay * (attempt + 1) + random.uniform(0, 0.5)))
    raise RuntimeError(f"giving up on {url}: {last}")


class MinInterval:
    """Space requests at least ``seconds`` apart (vendor rate limits, e.g. 5 per minute)."""

    def __init__(
        self, seconds: float, sleep: Sleep = time.sleep, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.seconds, self._sleep, self._clock = seconds, sleep, clock
        self._last: float | None = None

    def wait(self) -> None:
        now = self._clock()
        if self._last is not None and now - self._last < self.seconds:
            self._sleep(self.seconds - (now - self._last))
            now = self._clock()
        self._last = now
