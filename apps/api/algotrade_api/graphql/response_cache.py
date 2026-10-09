"""The response cache of ``POST /graphql`` (owner decision 2026-10-09): the serialized JSON of
an error-free query, kept until the next publish and served again without running it. There is
no ``ETag`` / 304: a browser does not revalidate a POST and the web client sends no
``If-None-Match``, so only the server-side cache is kept.

Every operation the web sends is in exactly one of four groups (a test fails a new one until it
is classified; the safe default is not cached): ``SHARED_OPERATIONS`` (published tables and
configs, the same for every caller of a role: market and regime history, prices, Guide index),
``USER_OPERATIONS`` (published tables and configs that depend on the caller's catalogue or
configs: user features, the Guide's field entries), ``RUN_OPERATIONS`` (they also read run
records or jobs: nightly runs, ingestion, screener runs and results, ideas, edges, status) and
``NEVER_CACHED`` (the text model's usage, which reads the clock, and the caller's identity). The
key (``response_key``) is the published state (``StoreReader.visible_seq()``), the writes the
API itself served since it started (``WriteEpoch``, moved by ``CountWrites`` after
the routes that write: a config save changes the caller's next read without a publish), a hash
of the operation document, its variables and the caller's role. A ``RUN_OPERATIONS`` key also
holds the runs generation (``StoreReader.runs_generation()``: it moves on every saved run
record, a job's too, which a publish does not cover: a failed job's record, an on-request run),
read before the answer is computed like ``visible_seq`` (ADR 0022); an operation whose loader
reads the clock (``CLOSED_SESSION_OPERATIONS``: the ingestion grid's "last closed session")
also holds that session. A ``SHARED_OPERATIONS`` entry does not hold the user id; every other
cached one does. The role is always in the key (ADR 0056: an admin's answer carries causes a
trader must never read). ``ResponseCache`` is an LRU bounded by bytes (``MAX_BYTES``, a
constant) and by age (``TTL_S``: a write made outside this process, such as a CLI config edit,
is seen within it). Only queries (the schema has no mutation), only answers without
``errors``; the cache lives in one process, which is the only process the API runs as."""

import hashlib
import json
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from datetime import date
from functools import lru_cache
from typing import Any

from graphql import GraphQLError, OperationDefinitionNode, parse
from starlette.types import ASGIApp, Receive, Scope, Send

from algotrade.config.site.users import UserRecord

MAX_BYTES = 100 * 1024 * 1024
TTL_S = 300.0
# Operations (by name) whose answer is the same for every caller of a role.
SHARED_OPERATIONS: frozenset[str] = frozenset(
    {
        "MarketHistory",
        "RegimeEpisodes",
        "RegimeBands",
        "RegimeSignals",
        "GuideIndex",
        "InstrumentPrices",
        "OptionQuotes",
        "EtfHoldings",
        "InstrumentEvents",
    }
)
# Operations over published tables and configs that depend on the caller's catalogue or
# configs (user features, the Guide's field entries): cached per user.
USER_OPERATIONS: frozenset[str] = frozenset(
    {
        "Regime",
        "FeatureTable",
        "FeatureDistribution",
        "FeatureCatalogue",
        "FeatureCatalogueDetail",
        "InstrumentFacts",
        "InstrumentFeatureValues",
        "InstrumentHistory",
        "ComparePrices",
        "Day",
        "EventCalendar",
        "InstrumentEventStudy",
        "TableView",
        "GuideEpisode",
        "GuideField",
        "GuideHelpField",
        "GuideIndicator",
        "GuidePlaybook",
        "GuideSituation",
        "GuideStartPage",
        "GuideTerm",
        "GuideSearch",
        "GuideEntries",
        "OptionChain",  # stored chains and features: no live source
        "Verification",  # the stored verification/ibkr partition: no call to IBKR
    }
)
# Operations that also read run records or jobs: cached per user, keyed on the runs generation.
RUN_OPERATIONS: frozenset[str] = frozenset(
    {
        "IdeasPage",
        "StatusStrip",
        "ScreenerConfigs",
        "ScreenerRuns",
        "ScreenerTrackRecords",
        "EdgesPage",
        "IngestionCompleteness",
        "NightlyRuns",
        "QualityChecks",
        "ScreenerResults",
        "ScreenerPicks",
        "InstrumentScreenerHits",
        "MyScreens",
        "ScreenDetail",
        "ScreenVersions",
        "HarnessRuns",
        "HarnessRun",
        "RunRecord",
        "RunItems",
        "EvaluationSplit",
        "FigiReview",
        "LeverageReview",
        "IngestionCell",
    }
)
# The run operations whose loader reads the clock (``load_completeness``: the last session the
# exchange closed): the closed session is in their key too.
CLOSED_SESSION_OPERATIONS: frozenset[str] = frozenset({"IngestionCompleteness", "StatusStrip"})
# Never kept: the text model's usage (it reads the clock, unkeyed) and the caller's identity
# (answered inline, no context opened). A new operation is never in this group by default: the
# classification test fails until it is placed.
NEVER_CACHED: frozenset[str] = frozenset({"LlmUsage", "Viewer"})
# The route packages whose endpoints write (configs, screen results, evaluations); a preview,
# a draft or an explain POST writes nothing the cache keys on.
WRITE_PACKAGES = (
    "algotrade_api.routes.authoring",
    "algotrade_api.routes.screens",
    "algotrade_api.routes.edges",
)


@lru_cache(maxsize=256)
def operation_name(document: str) -> str | None:
    """The name of the one operation in ``document`` (``None``: none, several, or not valid)."""
    try:
        names = [
            d.name.value if d.name else ""
            for d in parse(document).definitions
            if isinstance(d, OperationDefinitionNode)
        ]
    except GraphQLError:
        return None
    return (names[0] or None) if len(names) == 1 else None


def cacheable(document: str) -> bool:
    """Whether the operation in ``document`` is one whose answers are kept."""
    name = operation_name(document)
    return name in SHARED_OPERATIONS or name in USER_OPERATIONS or name in RUN_OPERATIONS


class WriteEpoch:
    """A counter of the writes this API served: ``CountWrites`` moves it, every cache key holds
    it, so a user's save is never answered from before it."""

    def __init__(self) -> None:
        self.value = 0


class CountWrites:
    """ASGI middleware moving a ``WriteEpoch`` after every PUT, POST or DELETE that a route of
    ``WRITE_PACKAGES`` served (the route is read from the scope once the router has matched
    it). Counted after the write, so a read that raced it keeps a key nobody asks for again."""

    def __init__(self, app: ASGIApp, epoch: WriteEpoch) -> None:
        self.app = app
        self.epoch = epoch

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in ("PUT", "POST", "DELETE"):
            await self.app(scope, receive, send)
            return
        try:
            await self.app(scope, receive, send)
        finally:
            module = getattr(getattr(scope.get("route"), "endpoint", None), "__module__", "")
            if module.startswith(WRITE_PACKAGES):
                self.epoch.value += 1


def response_key(
    seq: int,
    epoch: int,
    viewer: UserRecord,
    document: str,
    variables: Any,
    name: str | None,
    runs: tuple[int, int] = (0, 0),
    closed: date | None = None,
) -> str:
    """The hex digest identifying one cacheable answer. ``runs`` (the runs generation) is part
    of a ``RUN_OPERATIONS`` key, ``closed`` of a ``CLOSED_SESSION_OPERATIONS`` one."""
    who = (
        viewer.role.value if name in SHARED_OPERATIONS else f"{viewer.role.value}:{viewer.user_id}"
    )
    text = json.dumps(variables, sort_keys=True, separators=(",", ":"), default=str)
    parts = [str(seq), str(epoch), who, hashlib.sha256(document.encode()).hexdigest(), text]
    if name in RUN_OPERATIONS:
        parts.append(f"runs:{runs[0]}:{runs[1]}")
    if name in CLOSED_SESSION_OPERATIONS:
        parts.append(f"closed:{closed}")
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
