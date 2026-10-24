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
``NEVER_CACHED`` (the Describe-it request ranking, which reads the clock, and the caller's
identity). The
key (``response_key``) is the published state (``StoreReader.visible_seq()``), the caller's
config generation (``storage/configs/generation.py``, bumped inside every config write: a save
changes the caller's next read without a publish, in any process; an admin's key holds every
user's, ADR 0077 decision 15), a hash
of the operation document, its variables and the caller's role. A ``RUN_OPERATIONS`` key also
holds the runs generation (``StoreReader.runs_generation()``: it moves on every saved run
record, a job's too, which a publish does not cover: a failed job's record, an on-request run),
read before the answer is computed like ``visible_seq`` (ADR 0022); an operation whose loader
reads the clock (``CLOSED_SESSION_OPERATIONS``: the ingestion grid's "last closed session")
also holds that session. Every other key holds the session a read with no date serves
(``served_token``: its date and the newer incomplete session's, ADR 0062) instead: a nightly
workflow completing flips the pages without a publish, while a job's checkpoint record, which
changes no session, evicts nothing. A ``SHARED_OPERATIONS`` entry does not hold the user id; every
other cached one does. The role is always in the key (ADR 0056: an admin's answer carries causes a
trader must never read). ``ResponseCache`` is an LRU bounded by bytes (``MAX_BYTES``, a
constant) and by age: after ``TTL_S`` an entry is *stale*, not gone (stale-while-revalidate:
``get_stale`` still serves it while the router recomputes it in the background, so the first
page after an idle spell costs nothing), and after ``HARD_TTL_S`` it is dropped. The age only
matters for a write made outside this process, such as a CLI config edit, which the next read
after ``TTL_S`` serves stale once and the one after it sees; every in-process change is in the
key. ``OperationLog`` remembers the operations (document, variables, caller) the API served,
so the warmer replays them in process after a start seed and after every publish
(``warm.py``). Only queries (the schema has no mutation), only answers without
``errors``; the cache lives in one process, which is the only process the API runs as. The
body kept is the gzip-compressed one (``schema._served`` sends it as is to a client that
accepts gzip), so the byte bound counts compressed bytes."""

import hashlib
import json
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import Any

from graphql import FieldNode, GraphQLError, OperationDefinitionNode, parse

from algotrade.config.site.users import UserRecord

MAX_BYTES = 100 * 1024 * 1024
TTL_S = 300.0  # an entry older than this is stale: served once more, recomputed behind it
HARD_TTL_S = 24 * 3600.0  # beyond this an entry is dropped, not served
LOG_MAX = 512  # operations the log remembers (a page sends a dozen, per user)
# Operations (by name) whose answer is the same for every caller of a role.
SHARED_OPERATIONS: frozenset[str] = frozenset(
    {
        "MarketHistory",  # per-name values: the key carries the viewer's licence set
        "RegimeEpisodes",
        "RegimeBands",
        "RegimeSignals",
        "GuideIndex",
        "GuideMechanism",
        "GuideMechanisms",
        "GuideScreenerEdges",
        "GuideScreenerIndex",  # site presets and Guide files: the same for every caller
        "GuideScreenerCategory",
        "GuideEdge",
        "GuideEdgeIndex",  # site edge documents and mechanism files: the same for every caller
        "InstrumentPrices",
        "OptionQuotes",
        "EtfHoldings",
        "InstrumentEvents",
        "SessionDate",
    }
)
# The SHARED_OPERATIONS read from the current serving release (ADR 0077 decision 23): stored
# tables only, no run record, no catalogue. Listed with a reason and a test in
# ``architecture/release_shared_ops.toml`` (``tests/architecture/api/test_release_reads.py``).
RELEASE_SHARED_OPERATIONS: frozenset[str] = frozenset(
    {
        "InstrumentPrices",
        "MarketHistory",
        "InstrumentEvents",
        "EtfHoldings",
        "RegimeBands",
        "RegimeSignals",
        "RegimeEpisodes",
    }
)
# The field tree a release operation's document may select, every dotted path of the web's own
# document (``apps/web/src/shared/api/generated/graphql/gql.ts``; a test keeps them equal). The
# key of a release answer is role-wide, so it may hold nothing of the caller: a document named
# like a listed operation that selects any field outside its tree (a ``viewer``, a user's
# ``features``), or uses an alias, a directive or a fragment, is answered live and never kept.
RELEASE_FIELDS: dict[str, frozenset[str]] = {
    "InstrumentPrices": frozenset(
        {
            "instrument",
            "instrument.instrumentId",
            "instrument.prices",
            "instrument.prices.bars",
            "instrument.prices.bars.close",
            "instrument.prices.bars.session",
            "instrument.prices.bars.volume",
            "instrument.prices.end",
            "instrument.prices.start",
        }
    ),
    "MarketHistory": frozenset(
        {
            "market",
            "market.history",
            "market.history.bucketSessions",
            "market.history.name",
            "market.history.points",
            "market.history.points.session",
            "market.history.points.value",
            "market.history.segments",
            "market.history.segments.end",
            "market.history.segments.start",
            "market.history.segments.value",
        }
    ),
    "InstrumentEvents": frozenset(
        {
            "instrument",
            "instrument.events",
            "instrument.events.date",
            "instrument.events.kind",
            "instrument.events.table",
            "instrument.events.ts",
            "instrument.events.values",
            "instrument.instrumentId",
        }
    ),
    "EtfHoldings": frozenset(
        {
            "instrument",
            "instrument.holdings",
            "instrument.holdings.asOf",
            "instrument.holdings.items",
            "instrument.holdings.items.assetClass",
            "instrument.holdings.items.instrument",
            "instrument.holdings.items.instrument.symbol",
            "instrument.holdings.items.name",
            "instrument.holdings.items.rank",
            "instrument.holdings.items.symbol",
            "instrument.holdings.items.weight",
            "instrument.holdings.source",
            "instrument.holdings.total",
            "instrument.instrumentId",
            "instrument.isEtf",
        }
    ),
    "RegimeBands": frozenset(
        {
            "regime",
            "regime.bands",
            "regime.bands.end",
            "regime.bands.label",
            "regime.bands.start",
        }
    ),
    "RegimeSignals": frozenset(
        {
            "regime",
            "regime.episodes",
            "regime.episodes.key",
            "regime.episodes.signals",
            "regime.episodes.signals.gate",
            "regime.episodes.signals.gate.clearedDay",
            "regime.episodes.signals.gate.firstKnownDay",
            "regime.episodes.signals.gate.flaggedDay",
            "regime.episodes.signals.gate.flaggedDayFromTrough",
            "regime.episodes.signals.gate.indicator",
            "regime.episodes.signals.gate.kind",
            "regime.episodes.signals.gate.neverFired",
            "regime.episodes.signals.gate.state",
            "regime.episodes.signals.gate.unknownReason",
            "regime.episodes.signals.gate.unknownReason.cause",
            "regime.episodes.signals.gate.unknownReason.cause.links",
            "regime.episodes.signals.gate.unknownReason.cause.links.level",
            "regime.episodes.signals.gate.unknownReason.cause.links.message",
            "regime.episodes.signals.gate.unknownReason.cause.links.runId",
            "regime.episodes.signals.gate.unknownReason.cause.links.status",
            "regime.episodes.signals.gate.unknownReason.cause.links.subject",
            "regime.episodes.signals.gate.unknownReason.code",
            "regime.episodes.signals.gate.unknownReason.guideTerm",
            "regime.episodes.signals.gate.unknownReason.kind",
            "regime.episodes.signals.gate.unknownReason.kindText",
            "regime.episodes.signals.indicators",
            "regime.episodes.signals.indicators.clearedDay",
            "regime.episodes.signals.indicators.firstKnownDay",
            "regime.episodes.signals.indicators.flaggedDay",
            "regime.episodes.signals.indicators.flaggedDayFromTrough",
            "regime.episodes.signals.indicators.indicator",
            "regime.episodes.signals.indicators.kind",
            "regime.episodes.signals.indicators.neverFired",
            "regime.episodes.signals.indicators.state",
            "regime.episodes.signals.indicators.unknownReason",
            "regime.episodes.signals.indicators.unknownReason.cause",
            "regime.episodes.signals.indicators.unknownReason.cause.links",
            "regime.episodes.signals.indicators.unknownReason.cause.links.level",
            "regime.episodes.signals.indicators.unknownReason.cause.links.message",
            "regime.episodes.signals.indicators.unknownReason.cause.links.runId",
            "regime.episodes.signals.indicators.unknownReason.cause.links.status",
            "regime.episodes.signals.indicators.unknownReason.cause.links.subject",
            "regime.episodes.signals.indicators.unknownReason.code",
            "regime.episodes.signals.indicators.unknownReason.guideTerm",
            "regime.episodes.signals.indicators.unknownReason.kind",
            "regime.episodes.signals.indicators.unknownReason.kindText",
        }
    ),
    "RegimeEpisodes": frozenset(
        {
            "regime",
            "regime.episodes",
            "regime.episodes.cause",
            "regime.episodes.key",
            "regime.episodes.kind",
            "regime.episodes.knownFrom",
            "regime.episodes.name",
            "regime.episodes.nasdaqDrawdown",
            "regime.episodes.nberEnd",
            "regime.episodes.nberStart",
            "regime.episodes.notes",
            "regime.episodes.peak",
            "regime.episodes.recession",
            "regime.episodes.recovered",
            "regime.episodes.spxDrawdown",
            "regime.episodes.trough",
            "regime.recessions",
            "regime.recessions.announcedEnd",
            "regime.recessions.announcedStart",
            "regime.recessions.end",
            "regime.recessions.start",
        }
    ),
}
# Operations over published tables and configs that depend on the caller's catalogue or
# configs (user features, the Guide's field entries): cached per user.
USER_OPERATIONS: frozenset[str] = frozenset(
    {
        "Regime",
        "RegimeSources",  # the same read as Regime, its provenance part
        "PublishedEdge",
        "EdgeBuilder",  # the viewer's own edge document and the site files: config_generation
        "FeatureTable",
        "FeatureDistribution",
        "FeatureCatalogue",
        "FeatureCatalogueDetail",
        "InstrumentFacts",
        "FilterSet",  # the filters the caller may use: a data licence withholds some (ADR 0082)
        "InstrumentFeatureValues",
        "InstrumentHistory",
        "ComparePrices",
        "EventCalendar",
        "InstrumentEventStudy",
        "InstrumentEventList",  # the chart's event list: events and study with source pages
        "TableView",
        "GuideField",
        "GuideHelpField",
        "GuideScreener",
        "GuideSituation",
        "GuideSearch",
        "GuideEntries",
        "OptionChain",  # stored chains and features: no live source
        "Verification",  # the stored verification/ibkr partition: no call to IBKR
        "LlmUsage",  # the usage log: a logged call publishes a partition; TODAY_OPERATIONS
    }
)
# The operations whose loader reads the exchange date now (``load_llm_usage``'s "today"): that
# date is in their key too, so the first read after midnight is not the day before's.
TODAY_OPERATIONS: frozenset[str] = frozenset({"LlmUsage"})
# Operations that also read run records or jobs: cached per user, keyed on the runs generation.
RUN_OPERATIONS: frozenset[str] = frozenset(
    {
        "IdeasPage",
        "StatusStrip",
        "DataStatus",
        "ScreenerConfigs",
        "ScreenerRuns",
        "ScreenerTrackRecords",
        "ScreenerEdges",
        "EdgesPage",
        "EdgeDetail",  # one edge in full (verdict, runs, definition): the edge page
        "EdgeDocument",  # one edge's document for the builder: no verdict, no runs
        "EdgeDesk",  # the paper record plus the official run it is judged against
        "EdgePaper",
        "EdgeCompare",  # the viewer's edge against its parent: evaluation run records
        "EdgeTrades",  # the verdict basis's ledger (a run's rows) and the paper record
        "EdgeVariantGrid",
        # the sections of an edge's result: the official run's stored series, the verdict's basis
        # and the paper record for the session
        "EdgeResultBasis",
        "EdgeResultCurve",
        "EdgeResultDrawdown",
        "EdgeResultRollingStarts",
        "EdgeResultMonthly",
        "EdgeResultDecay",
        "EdgeResultCosts",
        "EdgeResultCapacity",
        "EdgeResultRegimes",
        "EdgeResultHorizons",
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
        "AdminScreenerRuns",
        "AdminScreenerRun",
        "RunRecord",
        "RunItems",
        "FigiReview",
        "LeverageReview",
        "IngestionCell",
    }
)
# The run operations whose loader reads the clock (``load_completeness_window``: the last
# session the exchange closed): the closed session is in their key too.
CLOSED_SESSION_OPERATIONS: frozenset[str] = frozenset({"IngestionCompleteness", "StatusStrip"})
# Never kept: the caller's identity
# (answered inline, no context opened) and the caller's own missing-feature requests (a draft
# POST records them, and a draft writes nothing the cache keys on; the window reads the clock).
# A new operation is never in this group by default: the classification test fails until it is
# placed.
NEVER_CACHED: frozenset[str] = frozenset(
    {"AcceptedFormulas", "FeatureRequests", "Viewer", "MyFeatureRequests"}
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


@lru_cache(maxsize=256)
def release_selects_only(name: str, document: str) -> bool:
    """Whether ``document`` (the operation ``name``) selects only the field tree
    ``RELEASE_FIELDS`` allows it, at every depth, with no alias, directive or fragment, a single
    query operation: deny by default (a field not in the tree is a caller-dependent field until
    shown otherwise)."""
    allowed = RELEASE_FIELDS.get(name)
    try:
        definitions = parse(document).definitions
    except GraphQLError:
        return False
    operations = [d for d in definitions if isinstance(d, OperationDefinitionNode)]
    if allowed is None or len(operations) != 1 or len(definitions) != 1 or operations[0].directives:
        return False
    return _within(operations[0].selection_set, "", allowed)


def _within(selections: Any, prefix: str, allowed: frozenset[str]) -> bool:
    for node in selections.selections:
        if not isinstance(node, FieldNode) or node.alias is not None or node.directives:
            return False
        path = prefix + node.name.value
        if path not in allowed:
            return False
        if node.selection_set is not None and not _within(node.selection_set, path + ".", allowed):
            return False
    return True


def cacheable(document: str) -> bool:
    """Whether the operation in ``document`` is one whose answers are kept."""
    name = operation_name(document)
    return name in SHARED_OPERATIONS or name in USER_OPERATIONS or name in RUN_OPERATIONS


def response_key(
    seq: int,
    viewer: UserRecord,
    document: str,
    variables: Any,
    name: str | None,
    runs: tuple[int, int] = (0, 0),
    closed: date | None = None,
    served: str = "",
    today: date | None = None,
    generation: int = 0,
    release: str | None = None,
) -> str:
    """The hex digest identifying one cacheable answer. ``runs`` (the runs generation) is part
    of a ``RUN_OPERATIONS`` key, ``closed`` of a ``CLOSED_SESSION_OPERATIONS`` one, ``served``
    (``served_token``: the default session) of every key (ADR 0062); ``generation`` is the
    viewer's config generation (``storage/configs/generation.py``, ADR 0077 decision 15), part of
    every key that holds the user (a ``SHARED_OPERATIONS`` one does not). ``release`` (the id of
    the serving release the answer is read from, ADR 0077 decision 23): the key of a
    ``RELEASE_SHARED_OPERATIONS`` operation is then that id, the role, the document, the
    variables and the licences alone: no sequence, no served session, no runs generation, so a
    commit, a restatement or a saved run record does not evict it."""
    if release is not None and name in RELEASE_SHARED_OPERATIONS:
        text = json.dumps(variables, sort_keys=True, separators=(",", ":"), default=str)
        licences = ",".join(sorted(viewer.licences))
        document_hash = hashlib.sha256(document.encode()).hexdigest()
        parts = ["release", release, viewer.role.value, document_hash, text, f"licences:{licences}"]
        return hashlib.sha256("\x00".join(parts).encode()).hexdigest()
    who = (
        viewer.role.value if name in SHARED_OPERATIONS else f"{viewer.role.value}:{viewer.user_id}"
    )
    text = json.dumps(variables, sort_keys=True, separators=(",", ":"), default=str)
    licences = ",".join(sorted(viewer.licences))  # what a viewer may see differs (ADR 0069)
    parts = [str(seq), who, hashlib.sha256(document.encode()).hexdigest(), text]
    parts.append(f"licences:{licences}")
    if name not in SHARED_OPERATIONS:
        parts.append(f"config:{generation}")
    parts.append(f"session:{served}")
    if name in RUN_OPERATIONS:
        parts.append(f"runs:{runs[0]}:{runs[1]}")
    if name in CLOSED_SESSION_OPERATIONS:
        parts.append(f"closed:{closed}")
    if name in TODAY_OPERATIONS:
        parts.append(f"today:{today}")
    return hashlib.sha256("\x00".join(parts).encode()).hexdigest()


def served_token(session: Any) -> str:
    """What of the default ``Session`` an answer can depend on: its date and the newer
    incomplete session's date, state and public kind (ADR 0062)."""
    newer = session.newer
    if newer is None:
        return str(session.date)
    return f"{session.date}:{newer.date}:{newer.state}:{newer.kind}"


class ResponseCache:
    """Serialized responses by key (the router stores them gzip-compressed once, off the event
    loop, so a hit is served without compressing; ``held`` counts the bytes stored): LRU by
    bytes, entries older than ``ttl_s`` dropped."""

    def __init__(
        self,
        max_bytes: int = MAX_BYTES,
        ttl_s: float = TTL_S,
        hard_ttl_s: float = HARD_TTL_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max = max_bytes
        self._ttl = ttl_s
        self._hard_ttl = hard_ttl_s
        self._clock = clock
        self._items: OrderedDict[str, tuple[float, bytes]] = OrderedDict()
        self._held = 0
        self._lock = threading.Lock()

    @property
    def held(self) -> int:
        """Bytes of the bodies kept."""
        return self._held

    def get(self, key: str) -> bytes | None:
        """The body of a fresh entry (younger than ``ttl_s``)."""
        return self._read(key, self._ttl)

    def get_stale(self, key: str) -> bytes | None:
        """The body of an entry past ``ttl_s`` but within ``hard_ttl_s`` (``None`` for a fresh
        one: ``get`` serves that; the caller recomputes behind the stale answer)."""
        found = self._read(key, self._hard_ttl)
        if found is None or self._read(key, self._ttl) is not None:
            return None
        return found

    def _read(self, key: str, limit: float) -> bytes | None:
        with self._lock:
            found = self._items.get(key)
            if found is None:
                return None
            at, body = found
            age = self._clock() - at
            if age > self._hard_ttl:
                del self._items[key]
                self._held -= len(body)
                return None
            if age > limit:
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


@dataclass(frozen=True)
class Served:
    """One operation the API served (or was seeded with): what the warmer replays."""

    viewer: UserRecord
    document: str
    variables: Any


class OperationLog:
    """The operations served, newest last, bounded by ``LOG_MAX``: one entry per caller,
    document and variables. Touched on the event loop only."""

    def __init__(self, max_items: int = LOG_MAX) -> None:
        self._max = max_items
        self._items: OrderedDict[tuple[str, str, str], Served] = OrderedDict()

    def note(self, viewer: UserRecord, document: str, variables: Any) -> None:
        text = json.dumps(variables, sort_keys=True, separators=(",", ":"), default=str)
        ident = (
            f"{viewer.role.value}:{viewer.user_id}",
            hashlib.sha256(document.encode()).hexdigest(),
            text,
        )
        self._items.pop(ident, None)
        self._items[ident] = Served(viewer, document, variables)
        while len(self._items) > self._max:
            self._items.popitem(last=False)

    def discard(self, op: Served) -> None:
        """Forget ``op`` (it failed: replaying it again every publish would only fail again)."""
        text = json.dumps(op.variables, sort_keys=True, separators=(",", ":"), default=str)
        ident = (
            f"{op.viewer.role.value}:{op.viewer.user_id}",
            hashlib.sha256(op.document.encode()).hexdigest(),
            text,
        )
        self._items.pop(ident, None)

    def items(self) -> list[Served]:
        """The remembered operations, oldest first (the order pages first asked for them)."""
        return list(self._items.values())
