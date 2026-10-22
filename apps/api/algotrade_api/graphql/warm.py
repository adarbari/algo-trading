"""Keeps the read cache warm ahead of the pages (ADR 0037): a task of the served API that, at
start and after every publish (polled every ``WARM_EVERY_S``), reads into the shared result
cache what every caller shares: the market tables' whole history
(``warm_market_frames``) and the event copies' validation (``warm_event_copies``), so the
regime page's charts slice a cached frame instead of reading 14 000 partitions on a
request (20 s a table cold), and the
session's regime that every page shows (3 to 5 s on the first page after a publish), the Ideas
table and the edge desk (the home page), the Admin Ingestion page's 10-session grid, the
session's run summaries (the stored screen rows, counted once) that every screener page and the
Builder's preview read (1.6 s on
the first one after a publish), the Builder's first preview of every screen on the Screeners
list (its field frame and the picks of its saved run), and the signal timing of every
reference episode (the regime page's History).
The read runs in the read pool (``off_loop``) like any request's, taking one of its threads;
a failing step is logged and the others still run; the next publish tries again.
Each step's log line carries the process footprint (``ops/footprint.py``), so a step that grows
the API shows up in the log (one warm once took it to 36 GB, docs/perf/api-memory.md).

The read model's loaders are not the pages' answers: a page's first request still runs its
resolvers (a second or two for Ideas, the screener results, the catalogue). So after the home
steps the warmer replays, in process, the operations the API has served (``OperationLog``:
document, variables, caller; seeded at start with the web's page-load operations,
``seed_operations``) through ``replay``, filling the response cache for the new published
state before any user asks; the long market frames come after, not before."""

import asyncio
import json
import logging
import threading
import time
from collections.abc import Awaitable, Callable, Hashable
from functools import partial
from pathlib import Path
from typing import Any

from algotrade.config.edges.document import MECHANISM_KINDS
from algotrade.config.site.regime.episodes import load_episodes
from algotrade.services.read.context import ReadContext
from algotrade.services.read.edge_desk.desk import load_edge_desk
from algotrade.services.read.events.stored import warm_event_copies
from algotrade.services.read.guide.edges.index import load_guide_edge_index
from algotrade.services.read.guide.edges.mechanism import load_guide_mechanism
from algotrade.services.read.guide.index import load_guide_index
from algotrade.services.read.market.history import warm_market_frames
from algotrade.services.read.ops.ingestion import load_completeness
from algotrade.services.read.regime.regime import load_regime
from algotrade.services.read.regime.timeline import load_episode_signals
from algotrade.services.read.screens.hits import load_screener_hits
from algotrade.services.read.screens.ideas import FIRST_PAGE, load_ideas
from algotrade.services.read.screens.runs import run_summaries
from algotrade.services.read.screens.screeners import load_screeners
from algotrade_api.graphql.offload import off_loop
from algotrade_api.ops.footprint import OwnFootprint

WARM_EVERY_S = 60.0
INGESTION_SESSIONS = 10  # the Admin Ingestion grid's window (entities/ingestion SESSIONS)

PAUSE_POLL_S = 0.02  # how often a paused step looks whether the requests are done
PAUSE_BUDGET_S = 120.0  # all the waiting one ``finish`` may do: steady traffic never starves it

log = logging.getLogger(__name__)
_footprint = OwnFootprint()  # MB of this process, re-read at most every few seconds


type Step = tuple[str, Callable[[], object]]
type ExtraSteps = Callable[[ReadContext], list[Step]]


class Pacer:
    """Lets requests go first: ``__call__`` blocks (in the warming thread) while ``busy()``,
    polling every ``PAUSE_POLL_S``, until the requests are done or the waiting spent by this
    pacer reaches ``budget_s`` (then it returns at once: the warm still completes). A step's
    threads hold the GIL, so a request met mid-step is slow; the pause is between steps and
    between a step's chunks (market frames: one table each)."""

    def __init__(self, busy: Callable[[], bool], budget_s: float = PAUSE_BUDGET_S) -> None:
        self._busy = busy
        self._left = budget_s
        self._tick = threading.Event()  # never set: a wait that is a sleep

    def __call__(self) -> None:
        while self._left > 0 and self._busy():
            self._tick.wait(PAUSE_POLL_S)
            self._left -= PAUSE_POLL_S


def _run(steps: list[Step], pause: Callable[[], None] | None = None) -> None:
    for name, step in steps:  # one failing step does not stop (or repeat) the others
        if pause is not None:
            pause()
        started = time.monotonic()
        try:
            step()
        except Exception:
            log.exception("warming the read cache: %s failed", name)
        else:
            mb = _footprint()
            seconds = time.monotonic() - started
            if mb is None:  # the probe warns once; the line stays without the figure
                log.info("warmed %s in %.1f s", name, seconds)
            else:
                log.info("warmed %s in %.1f s, footprint %.0f MB", name, seconds, mb)


def home_steps(ctx: ReadContext) -> list[Step]:
    """What the home page (Ideas) and the shell around every page read, a few seconds in all on a
    cold store: the API finishes them (``CacheWarmer.warm_home``) before it accepts a request, so
    the first visit after a start is served from the cache."""
    return [
        # first: a second in all, and a slow home must not leave the Guide cold
        ("guide", lambda: warm_guide(ctx)),  # the Guide's index, Edges index and mechanisms
        # the resolved screeners (18 TOML configs): the regime strip, status strip and Ideas read it
        ("screeners", lambda: load_screeners(ctx)),
        (
            "run summaries",
            lambda: run_summaries(ctx),
        ),  # every screener page's and the preview's runs
        ("regime", lambda: load_regime(ctx)),
        ("ideas", lambda: load_ideas(ctx, FIRST_PAGE)),  # the Ideas page, home of every login
        ("edge desk", lambda: load_edge_desk(ctx)),
        # the Explore detail pane's hits of any ticker are a lookup in this index (hits.py)
        ("screener hits", lambda: load_screener_hits(ctx, [])),
    ]


def warm_guide(ctx: ReadContext) -> None:
    """The Guide's built pages: the index, the Edges index and each mechanism's page (0.5 s of
    TOML parsing each, cold), so the first visit after a start is served from the cache."""
    load_guide_index(ctx)
    load_guide_edge_index(ctx)
    for kind in MECHANISM_KINDS:
        load_guide_mechanism(ctx, kind)


def warm(
    ctx: ReadContext,
    extra: ExtraSteps | None = None,
    home: bool = True,
    pause: Callable[[], None] | None = None,
) -> None:
    """Read what every page shares for ``ctx``'s session and published state (``home_steps``
    first, unless ``home`` is False because the caller read them already: seconds, not the
    market frames' minutes, stand between a publish and the home page), then the steps
    ``extra`` names for it (the Builder's first preview of each screen: the API wires them in,
    this layer reads only the read model), the market frames and the episodes."""
    steps = home_steps(ctx) if home else []
    # the Admin Ingestion page's 10-session grid (3 s cold: 4300 partitions): not a home step, the
    # start does not wait for it
    steps.append(("ingestion grid", lambda: load_completeness(ctx, INGESTION_SESSIONS)))
    if extra is not None:
        try:
            steps.extend(extra(ctx))  # a second or two each
        except Exception:
            log.exception("warming the read cache: the extra steps failed")
    frames = (
        partial(warm_market_frames, ctx)
        if pause is None
        else partial(warm_market_frames, ctx, pause=pause)
    )
    steps.append(("market frames", frames))
    # the event copies' per-day validation (a digest per stored day, 1 to 2 s cold for fund_nav)
    steps.append(("event copies", lambda: warm_event_copies(ctx)))
    try:
        for episode in load_episodes(ctx.configs).episodes:  # the regime page's History
            steps.append(
                (f"episode {episode.key}", partial(load_episode_signals, ctx, episode.key))
            )
    except Exception:
        log.exception("warming the read cache: the episodes failed")
    _run(steps, pause)


class CacheWarmer:
    """Warms ``open_ctx()`` (``begin``: the home steps, ``replay``, ``finish``: the rest) whenever
    its session (or the newer one it discloses) or published state is new;
    ``run`` polls until cancelled (the app's lifespan starts and cancels it)."""

    def __init__(
        self,
        open_ctx: Callable[[], ReadContext],
        every_s: float = WARM_EVERY_S,
        extra: ExtraSteps | None = None,
        replay: Callable[[], Awaitable[int]] | None = None,
        stale: Callable[[], str | None] | None = None,
        busy: Callable[[], bool] | None = None,
    ):
        self._busy = busy
        self._stale = stale
        self._stale_logged: str | None = None
        self._replay = replay
        self._open_ctx = open_ctx
        self._extra = extra
        self._every_s = every_s
        self._warmed: Hashable | None = None

    def warm_home(self) -> None:
        """Read the home page's steps now (blocking): the app's start waits for it."""
        _run(home_steps(self._open_ctx()))

    async def replay_operations(self) -> None:
        """Replay the served operations into the response cache (``replay``), logged and never
        raising: a page asked before it is warm just computes."""
        if self._replay is None:
            return
        started = time.monotonic()
        try:
            count = await self._replay()
        except Exception:
            log.exception("replaying the served operations failed")
        else:
            log.info("replayed %d operations in %.1f s", count, time.monotonic() - started)

    def begin(self) -> tuple[ReadContext, Hashable] | None:
        """When the session or the published state moved since the last warm, read the home
        steps and return what ``finish`` needs; else ``None``. Blocking: the store's reads."""
        reason = self._stale() if self._stale is not None else None
        if reason is not None:  # configs ahead of this process's code: warming would only fail
            if reason != self._stale_logged:
                log.warning("not warming the read cache until the restart: %s", reason)
                self._stale_logged = reason
            return None
        ctx = self._open_ctx()
        # the session moves with the nightly's run records too (ADR 0062), not only on a publish
        state = (ctx.session.date, ctx.session.newer, ctx.reader.visible_seq())
        if state == self._warmed:
            return None
        _run(home_steps(ctx))
        return ctx, state

    def finish(self, pending: tuple[ReadContext, Hashable]) -> None:
        """The rest of the warm (``warm``) for what ``begin`` returned. Blocking."""
        ctx, state = pending
        if self._busy is None:
            warm(ctx, self._extra, home=False)
        else:  # the rest runs after the API serves: a request goes before each step
            warm(ctx, self._extra, home=False, pause=Pacer(self._busy))
        self._warmed = state

    async def run(self) -> None:
        """Warm in the read pool, then wait ``every_s``; forever, until cancelled."""
        while True:
            try:
                pending = await off_loop(self.begin)
                if pending is not None:
                    await self.replay_operations()  # before the market frames' minutes
                    await off_loop(self.finish, pending)
            except Exception:  # a store mid-publish or empty: the next poll tries again
                log.exception("warming the read cache failed")
            await asyncio.sleep(self._every_s)


def seed_operations(path: Path) -> list[tuple[str, Any]]:
    """The (document, variables) pairs of the page-load operations in the capture file
    ``path`` (``make api-latency-capture``: what each route of the web app sends), in page
    order, once each; none when the file is absent or unreadable (the log then fills as pages
    are served)."""
    try:
        pages = json.loads(path.read_text())["pages"]
    except (OSError, ValueError, KeyError):
        return []
    seen: dict[str, tuple[str, Any]] = {}
    for operations in pages.values():
        for op in operations:
            query = op.get("query")
            if isinstance(query, str):
                variables = op.get("variables") or {}
                ident = json.dumps([query, variables], sort_keys=True)
                seen.setdefault(ident, (query, variables))
    return list(seen.values())
