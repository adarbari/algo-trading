"""Keeps the read cache warm ahead of the pages (ADR 0037): a task of the served API that, at
start and after every publish (polled every ``WARM_EVERY_S``), reads into the shared result
cache what every caller shares: the market tables' whole history (``warm_market_frames``), so
the regime page's charts slice a cached frame instead of reading 14 000 partitions on a
request (20 s a table cold), and the status strip's one-session completeness grid and the
session's regime that every page shows (3 to 5 s on the first page after a publish), and
the signal timing of every reference episode (the regime page's History).
The read runs in the read pool (``off_loop``) like any request's, taking one of its threads;
a failing step is logged and the others still run; the next publish tries again."""

import asyncio
import logging
from collections.abc import Callable, Hashable
from functools import partial

from algotrade.config.site.regime.episodes import load_episodes
from algotrade.services.read.context import ReadContext
from algotrade.services.read.market.history import warm_market_frames
from algotrade.services.read.ops.ingestion import load_completeness
from algotrade.services.read.regime.regime import load_regime
from algotrade.services.read.regime.timeline import load_episode_signals
from algotrade_api.graphql.offload import off_loop

WARM_EVERY_S = 60.0

log = logging.getLogger(__name__)


def warm(ctx: ReadContext) -> None:
    """Read what every page shares for ``ctx``'s session and published state."""
    steps: list[tuple[str, Callable[[], object]]] = [
        ("market frames", lambda: warm_market_frames(ctx)),
        ("completeness", lambda: load_completeness(ctx, 1)),  # the status strip's grid
        ("regime", lambda: load_regime(ctx)),
    ]
    try:
        for episode in load_episodes(ctx.configs).episodes:  # the regime page's History
            steps.append(
                (f"episode {episode.key}", partial(load_episode_signals, ctx, episode.key))
            )
    except Exception:
        log.exception("warming the read cache: the episodes failed")
    for name, step in steps:  # one failing step does not stop (or repeat) the others
        try:
            step()
        except Exception:
            log.exception("warming the read cache: %s failed", name)


class CacheWarmer:
    """Calls ``warm`` on ``open_ctx()`` whenever its session or published state is new;
    ``run`` polls until cancelled (the app's lifespan starts and cancels it)."""

    def __init__(self, open_ctx: Callable[[], ReadContext], every_s: float = WARM_EVERY_S):
        self._open_ctx = open_ctx
        self._every_s = every_s
        self._warmed: Hashable | None = None

    def warm_once(self) -> bool:
        """Warm when the session or the published state moved since the last warm; whether it
        did. Blocking: the store's reads."""
        ctx = self._open_ctx()
        state = (ctx.session.date, ctx.reader.visible_seq())
        if state == self._warmed:
            return False
        warm(ctx)
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
