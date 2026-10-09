"""The response cache of ``POST /graphql`` (owner decision 2026-10-09): the serialized JSON of
an error-free query, kept until the next publish and served again, with a strong ``ETag`` so a
browser revalidates with ``If-None-Match`` and gets a 304 without the operation running.

The key (``response_key``) is the published state (``StoreReader.visible_seq()``), the writes
the API itself served since it started (``WriteEpoch``: a user-config write changes what the
caller's next read answers without a publish), a hash of the operation document, its variables,
the caller's role AND user id (ADR 0056: an admin's answer carries causes a trader must never
read, and most reads are the user's own). An operation named in ``SHARED_OPERATIONS`` is
declared the same for every caller of a role and is keyed on the role alone; none is declared
yet, so every entry is the user's. ``ResponseCache`` is an LRU bounded by bytes
(``MAX_BYTES``, a constant) and by age (``TTL_S``: a write made outside this process, such as a
CLI config edit, is seen within it). Only queries are cached (the schema has no mutation) and
only answers without ``errors``; the cache lives in one process, which is the only process the
API runs as."""

import hashlib
import json
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send

from algotrade.config.site.users import UserRecord

MAX_BYTES = 100 * 1024 * 1024
TTL_S = 300.0
# Operations (by ``operationName``) whose answer is the same for every caller of a role.
SHARED_OPERATIONS: frozenset[str] = frozenset()


class WriteEpoch:
    """A counter of the writes this API served: ``CountWrites`` moves it, every cache key holds
    it, so a user's save is never answered from before it."""

    def __init__(self) -> None:
        self.value = 0


class CountWrites:
    """ASGI middleware moving a ``WriteEpoch`` around every PUT, POST or DELETE that is not the
    ``/graphql`` read itself (before and after, so a read racing a write never keeps a key the
    write's result could reach)."""

    def __init__(self, app: ASGIApp, epoch: WriteEpoch, graphql_path: str = "/graphql") -> None:
        self.app = app
        self.epoch = epoch
        self.path = graphql_path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope["method"] in ("PUT", "POST", "DELETE")
            and scope["path"] != self.path
        ):
            self.epoch.value += 1
            try:
                await self.app(scope, receive, send)
            finally:
                self.epoch.value += 1
            return
        await self.app(scope, receive, send)


def response_key(
    seq: int, epoch: int, viewer: UserRecord, document: str, variables: Any, name: str | None
) -> str:
    """The hex digest identifying one cacheable answer (also its ``ETag`` value)."""
    who = (
        viewer.role.value if name in SHARED_OPERATIONS else f"{viewer.role.value}:{viewer.user_id}"
    )
    text = json.dumps(variables, sort_keys=True, separators=(",", ":"), default=str)
    parts = (str(seq), str(epoch), who, hashlib.sha256(document.encode()).hexdigest(), text)
    return hashlib.sha256("\x00".join(parts).encode()).hexdigest()


class ResponseCache:
    """Serialized responses by key: LRU by bytes, entries older than ``ttl_s`` dropped."""

    def __init__(
        self,
        max_bytes: int = MAX_BYTES,
        ttl_s: float = TTL_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max = max_bytes
        self._ttl = ttl_s
        self._clock = clock
        self._items: OrderedDict[str, tuple[float, bytes]] = OrderedDict()
        self._held = 0
        self._lock = threading.Lock()

    @property
    def held(self) -> int:
        """Bytes of the bodies kept."""
        return self._held

    def get(self, key: str) -> bytes | None:
        with self._lock:
            found = self._items.get(key)
            if found is None:
                return None
            at, body = found
            if self._clock() - at > self._ttl:
                del self._items[key]
                self._held -= len(body)
                return None
            self._items.move_to_end(key)
            return body

    def put(self, key: str, body: bytes) -> None:
        """Keeps ``body`` (never one bigger than the whole bound), evicting the least recently
        used until the bytes fit."""
        if len(body) > self._max:
            return
        with self._lock:
            old = self._items.pop(key, None)
            if old is not None:
                self._held -= len(old[1])
            self._items[key] = (self._clock(), body)
            self._held += len(body)
            while self._held > self._max:
                _, (_, dropped) = self._items.popitem(last=False)
                self._held -= len(dropped)
