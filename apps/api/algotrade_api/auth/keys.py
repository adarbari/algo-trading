"""The Supabase project's signing keys (its JWKS), cached by ``kid`` (ADR 0040).

Fetched once at startup and kept: ``key_for`` refetches at most once per call, when the set is
older than ``max_age`` or the ``kid`` is unknown (a rotated key), and never more often than
``cooldown`` (an outage or a forged ``kid`` cannot turn every request into a fetch). A failed
fetch keeps the keys we have and logs a warning; it never raises. The fetch is injected (tests
never open a socket); the default is PyJWT's ``PyJWKClient`` over the project's JWKS URL."""

import logging
import threading
import time
from collections.abc import Callable, Mapping
from typing import Any

from jwt import PyJWK, PyJWKClient, PyJWKSet
from jwt.exceptions import PyJWKSetError, PyJWTError

log = logging.getLogger(__name__)

Fetch = Callable[[], Mapping[str, Any]]  # the JWKS document ({"keys": [...]})
Clock = Callable[[], float]
JWKS_PATH = "/auth/v1/.well-known/jwks.json"
FETCH_TIMEOUT_S = 5


def jwks_fetch(supabase_url: str) -> Fetch:
    """The project's JWKS over HTTPS (PyJWT's client, its own cache off: ``KeySet`` caches)."""
    client = PyJWKClient(f"{supabase_url}{JWKS_PATH}", cache_jwk_set=False, timeout=FETCH_TIMEOUT_S)
    return client.fetch_data


def parse_keys(document: Mapping[str, Any]) -> dict[str, PyJWK]:
    """The usable keys of a JWKS document by ``kid`` (a key without one cannot be named);
    an empty set is no keys."""
    try:
        found = PyJWKSet.from_dict(dict(document)).keys
    except PyJWKSetError:
        return {}
    return {k.key_id: k for k in found if k.key_id}


class KeySet:
    """The JWKS, cached by ``kid`` (thread-safe: requests resolve in the threadpool)."""

    def __init__(
        self,
        fetch: Fetch,
        max_age: float = 600.0,
        cooldown: float = 30.0,
        clock: Clock = time.monotonic,
    ) -> None:
        self._fetch = fetch
        self._max_age = max_age
        self._cooldown = cooldown
        self._clock = clock
        self._keys: dict[str, PyJWK] = {}
        self._fetched: float | None = None  # the last successful fetch
        self._tried: float | None = None  # the last attempt, successful or not
        self._lock = threading.Lock()

    def refresh(self) -> bool:
        """Fetch the set now; on failure keep the keys we have and log. True: fetched."""
        with self._lock:
            return self._refresh(self._clock())

    def key_for(self, kid: str) -> PyJWK | None:
        """The key named ``kid``, refetching once first when the set is stale or ``kid`` is
        unknown (and the cooldown has passed); ``None``: no such key."""
        with self._lock:
            now = self._clock()
            stale = self._fetched is None or now - self._fetched >= self._max_age
            cooled = self._tried is None or now - self._tried >= self._cooldown
            if cooled and (stale or kid not in self._keys):
                self._refresh(now)
            return self._keys.get(kid)

    def _refresh(self, now: float) -> bool:
        self._tried = now
        try:
            keys = parse_keys(self._fetch())
        except (PyJWTError, OSError, ValueError, TypeError) as exc:
            kept = len(self._keys)
            log.warning("JWKS fetch failed (%s); keeping %d keys", type(exc).__name__, kept)
            return False
        self._keys, self._fetched = keys, now
        return True
