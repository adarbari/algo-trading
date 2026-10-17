"""Keeps the read cache warm ahead of the pages (ADR 0037): a task of the served API that, at
start and after every publish (polled every ``WARM_EVERY_S``), reads into the shared result
cache what every caller shares: the market tables' whole history (``warm_market_frames``), so
the regime page's charts slice a cached frame instead of reading 14 000 partitions on a
request (20 s a table cold), and the status strip's one-session completeness grid and the
session's regime that every page shows (3 to 5 s on the first page after a publish), the Ideas
table and the edge desk (the home page), the Admin Ingestion page's 10-session grid, the
session's stored screen rows that every screener page and the Builder's preview read (1.6 s on
the first one after a publish), the Builder's first preview of every screen on the Screeners
list (its field frame and the picks of its saved run), and the signal timing of every
reference episode (the regime page's History).
The read runs in the read pool (``off_loop``) like any request's, taking one of its threads;
a failing step is logged and the others still run; the next publish tries again."""

import asyncio
import logging
import time
from collections.abc import Callable, Hashable
from functools import partial

from algotrade.config.site.regime.episodes import load_episodes
from algotrade.services.read.context import ReadContext
from algotrade.services.read.edge_desk.desk import load_edge_desk
from algotrade.services.read.market.history import warm_market_frames
from algotrade.services.read.ops.ingestion import load_completeness
from algotrade.services.read.regime.regime import load_regime
from algotrade.services.read.regime.timeline import load_episode_signals
from algotrade.services.read.screens.ideas import load_ideas
from algotrade.services.read.screens.runs import screen_rows
from algotrade.services.read.screens.screeners import load_screeners
from algotrade_api.graphql.offload import off_loop

WARM_EVERY_S = 60.0
IDEAS_LIMIT = 200  # the Ideas page's request (entities/idea IDEAS_LIMIT)
INGESTION_SESSIONS = 10  # the Admin Ingestion grid's window (entities/ingestion SESSIONS)

log = logging.getLogger(__name__)


type Step = tuple[str, Callable[[], object]]
type ExtraSteps = Callable[[ReadContext], list[Step]]


def _run(steps: list[Step]) -> None:
    for name, step in steps:  # one failing step does not stop (or repeat) the others
        started = time.monotonic()
        try:
            step()
        except Exception:
            log.exception("warming the read cache: %s failed", name)
        else:
            log.info("warmed %s in %.1f s", name, time.monotonic() - started)


def home_steps(ctx: ReadContext) -> list[Step]:
    """What the home page (Ideas) and the shell around every page read, a few seconds in all on a
    cold store: the API finishes them (``CacheWarmer.warm_home``) before it accepts a request, so
    the first visit after a start is served from the cache."""
    return [
        # the resolved screeners (18 TOML configs): the regime strip, status strip and Ideas read it
        ("screeners", lambda: load_screeners(ctx)),
        ("screen rows", lambda: screen_rows(ctx)),  # the screener pages' and the preview's runs
        ("completeness", lambda: load_completeness(ctx, 1)),  # the status strip's grid
        ("regime", lambda: load_regime(ctx)),
        ("ideas", lambda: load_ideas(ctx, IDEAS_LIMIT)),  # the Ideas page, home of every login
        ("edge desk", lambda: load_edge_desk(ctx)),
    ]


def warm(ctx: ReadContext, extra: ExtraSteps | None = None) -> None:
    """Read what every page shares for ``ctx``'s session and published state (``home_steps``
    first: seconds, not the market frames' minutes, stand between a publish and the home page),
    then the steps ``extra`` names for it (the Builder's first preview of each screen: the API
    wires them in, this layer reads only the read model), the market frames and the episodes."""
    steps = home_steps(ctx)
    # the Admin Ingestion page's 10-session grid (3 s cold: 4300 partitions): not a home step, the
    # start does not wait for it
    steps.append(("ingestion grid", lambda: load_completeness(ctx, INGESTION_SESSIONS)))
    if extra is not None:
        try:
            steps.extend(extra(ctx))  # a second or two each
        except Exception:
            log.exception("warming the read cache: the extra steps failed")
    steps.append(("market frames", lambda: warm_market_frames(ctx)))
    try:
        for episode in load_episodes(ctx.configs).episodes:  # the regime page's History
            steps.append(
                (f"episode {episode.key}", partial(load_episode_signals, ctx, episode.key))
            )
    except Exception:
        log.exception("warming the read cache: the episodes failed")
    _run(steps)


class CacheWarmer:
    """Calls ``warm`` on ``open_ctx()`` whenever its session (or the newer one it discloses) or
    published state is new;
    ``run`` polls until cancelled (the app's lifespan starts and cancels it)."""

    def __init__(
        self,
        open_ctx: Callable[[], ReadContext],
        every_s: float = WARM_EVERY_S,
        extra: ExtraSteps | None = None,
    ):
        self._open_ctx = open_ctx
        self._extra = extra
        self._every_s = every_s
        self._warmed: Hashable | None = None

    def warm_home(self) -> None:
        """Read the home page's steps now (blocking): the app's start waits for it."""
        _run(home_steps(self._open_ctx()))

    def warm_once(self) -> bool:
        """Warm when the session or the published state moved since the last warm; whether it
        did. Blocking: the store's reads."""
        ctx = self._open_ctx()
        # the session moves with the nightly's run records too (ADR 0062), not only on a publish
        state = (ctx.session.date, ctx.session.newer, ctx.reader.visible_seq())
        if state == self._warmed:
            return False
        warm(ctx, self._extra)
        self._warmed = state
        return True

    async def run(self) -> None:
        """Warm in the read pool, then wait ``every_s``; forever, until cancelled."""
        while True:
            try:
                await off_loop(self.warm_once)
            except Exception:  # a store mid-publish or empty: the next poll tries again
                log.exception("warming the read cache failed")
            await asyncio.sleep(self._every_s)
