"""``load_screener_list``: the Screeners list as filtered rows (ADR 0082, surface ``screeners``).
A row is a ``ScreenerRow``: the screener the user sees, ``owner`` as the list's pick says it
(``mine`` or ``site``), its run for the session (None: not run) and the ids of the edges that
list it (no run rows are read for them). ``q`` searches the screener's id, name and description
(any case) and narrows the list before the filters, so the facets count what the search left
(``facets.total``); the ``filters`` then narrow it through the one pass. A screener with no run
has no ``run_status`` and no ``picked``: UNKNOWN for those filters, never passing. Not paged: the
list is the user's screeners and the site presets."""

from collections.abc import Sequence
from dataclasses import dataclass

from algotrade.config.user import SITE_USER
from algotrade.services.read.context import ReadContext
from algotrade.services.read.evaluation.track_record import load_listing_edge_ids
from algotrade.services.read.filtering.facets import Facets, compute_facets
from algotrade.services.read.filtering.masks import FilterInput
from algotrade.services.read.filtering.rows import frame_of
from algotrade.services.read.filtering.served import load_list_filters
from algotrade.services.read.screens.runs import ScreenerRun, load_latest_runs
from algotrade.services.read.screens.screeners import Screener, load_screeners

SURFACE = "screeners"  # config/site/filters/screeners.toml
MINE, SITE = "mine", "site"


@dataclass(frozen=True)
class ScreenerRow:
    """``screener`` with the facts the list's filters read (the roots of the column sources)."""

    screener: Screener
    owner: str
    latest_run: ScreenerRun | None
    edge_ids: tuple[str, ...]


@dataclass(frozen=True)
class ScreenerList:
    """``items``: the screeners that pass the search and the filters, in id order; ``total``:
    their count (``facets.total``: before the filters, after the search)."""

    items: tuple[ScreenerRow, ...]
    total: int
    facets: Facets


def _matches(s: Screener, needle: str) -> bool:
    return any(needle in (text or "").lower() for text in (s.id, s.name, s.description))


def load_screener_list(
    ctx: ReadContext, filters: Sequence[FilterInput] = (), q: str | None = None
) -> ScreenerList:
    """The user's screeners for ``ctx.session`` matching ``q`` and ``filters``.
    ``FilterRefusedError`` for a filter the viewer is not offered."""
    served = load_list_filters(ctx, SURFACE)
    served.resolved.check(i.id for i in filters)
    needle = (q or "").strip().lower()
    found = [s for s in load_screeners(ctx) if not needle or _matches(s, needle)]
    latest = load_latest_runs(ctx, [(s.owner, s.id) for s in found])
    listing = load_listing_edge_ids(ctx, [s.id for s in found])
    rows = tuple(
        ScreenerRow(
            s,
            SITE if s.owner == SITE_USER else MINE,
            latest[(s.owner, s.id)].run,
            listing[s.id],
        )
        for s in found
    )
    frame = frame_of(rows, served.resolved, served.columns)
    facets = compute_facets(frame, len(rows), served.resolved, filters)
    return ScreenerList(tuple(rows[i] for i in facets.matched_rows), facets.matched, facets)
