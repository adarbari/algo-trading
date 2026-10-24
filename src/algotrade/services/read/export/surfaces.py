"""The surfaces that can be exported, one registration each (ADR 0082 decision 6): a surface
name -> the function that reads its rows through the surface's own loader, unpaged, under the
viewer's filters and licences, and turns them into text cells.

A cell the viewer may not read is its public kind (``LICENCE``), one not known is its kind too,
one not stored is empty, as the ledger file does (``edge_ledger/trades_csv.py``): the cells come
from the read objects the loaders already redacted (a withheld run has no rank or score, a hidden
criterion no value), so the file and the page cannot disagree. A new surface is one function here
and one line in ``SURFACES``; its filters are its ``config/site/filters/<surface>.toml``."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from algotrade.core.model.errors import ConfigurationError
from algotrade.services.read.availability.cause import UnavailableKind
from algotrade.services.read.context import NotFoundError, ReadContext
from algotrade.services.read.filtering.masks import FilterInput
from algotrade.services.read.instruments import table as universe_table
from algotrade.services.read.screens import ideas as ideas_read
from algotrade.services.read.screens import results as results_read
from algotrade.services.read.screens import runs as runs_read
from algotrade.services.read.screens.screeners import load_screener

ROW_CAP = 50_000  # rows in one file; a longer list is cut and the file says so
CHUNK = 1_000  # rows per loader page of a paged surface
MAX_COLUMNS = 40  # catalogue columns a file may add

LICENCE = UnavailableKind.LICENCE.value


@dataclass(frozen=True)
class Params:
    """What a surface asks beyond the filters: ``screener`` (screener results: whose run) and
    ``columns`` (catalogue names added after the surface's own columns)."""

    screener: str | None = None
    columns: tuple[str, ...] = ()


@dataclass(frozen=True)
class Exported:
    """``rows`` (at most ``ROW_CAP``) of text cells under ``headers``; ``total``: every row the
    filters leave (more than ``len(rows)`` when the list was cut)."""

    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    total: int


Surface = Callable[[ReadContext, Sequence[FilterInput], Params], Exported]


def text(value: object) -> str:
    """A scalar as a cell: nothing stored is empty, never 0."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _kinded(value: object, kind: UnavailableKind | None) -> str:
    return kind.value if kind is not None else text(value)


def _readable(value: object, withheld: bool) -> str:
    return LICENCE if withheld else text(value)


def _metrics(result: results_read.ScreenResult, hidden: frozenset[str]) -> str:
    """The best pick's display values (``name=value``), a criterion over a field the viewer's
    licences do not cover as ``name=LICENCE``."""
    shown = [f"{m.name}={m.value}" for m in ideas_read.display_metrics(result)]
    held = [f"{c.id}={LICENCE}" for c in result.criteria if c.field in hidden]
    return "; ".join([*shown, *held])


def _identity(result: results_read.ScreenResult) -> tuple[str, str, str]:
    found = result.instrument
    return (
        result.instrument_id,
        "" if found is None else found.symbol,
        "" if found is None else found.name,
    )


IDEAS_HEADERS = (
    "rank", "instrument_id", "symbol", "company", "score", "decision", "regime",
    "size_multiplier", "screeners", "watch_out", "metrics",
)  # fmt: skip


def ideas(ctx: ReadContext, filters: Sequence[FilterInput], params: Params) -> Exported:
    """The Ideas list under ``filters``: ``load_ideas`` asked for one page of the cap."""
    found = ideas_read.load_ideas(ctx, ROW_CAP, None, filters)
    runs = {s.run.run_id: s.run for s in found.screeners if s.run is not None}
    hidden = {run_id: results_read.run_withheld(ctx, run) for run_id, run in runs.items()}
    rows = []
    for idea in found.items:
        gone = hidden.get(idea.best.run_id, frozenset())
        who, symbol, company = _identity(idea.best)
        rows.append(
            (
                text(idea.rank), who, symbol, company, text(idea.score), idea.best.decision,
                text(idea.regime), text(idea.size_multiplier),
                ",".join(p.config_id for p in idea.picked_by), ",".join(idea.watch_out),
                _metrics(idea.best, gone),
            )
        )  # fmt: skip
    return Exported(IDEAS_HEADERS, tuple(rows), found.total)


RESULT_HEADERS = (
    "rank", "instrument_id", "symbol", "company", "decision", "score", "reasons", "change",
    "previous_decision", "regime", "size_multiplier", "flags", "metrics",
)  # fmt: skip


def screener_results(ctx: ReadContext, filters: Sequence[FilterInput], params: Params) -> Exported:
    """A screener's run for the session, its rows under ``filters``, paged through in chunks
    (``load_result_page``): the rank, score and reasons of a run the viewer's licences withhold
    are ``LICENCE``."""
    if not params.screener:
        raise ConfigurationError("screener: name the screener whose results to export")
    screener = load_screener(ctx, params.screener)
    if screener is None:
        raise NotFoundError(f"no such screener: {params.screener}")
    latest = runs_read.latest_run(ctx, screener.owner, screener.id)
    if latest.run is None:
        raise NotFoundError(f"screener {params.screener} has no run for this session")
    run = latest.run
    hidden = results_read.run_withheld(ctx, run)
    headers = (*RESULT_HEADERS, *params.columns)
    rows: list[tuple[str, ...]] = []
    total, page = 0, 1
    while len(rows) < ROW_CAP:
        got = results_read.load_result_page(ctx, run, None, params.columns, page, CHUNK, filters)
        total = got.total
        for i, r in enumerate(got.results):
            who, symbol, company = _identity(r)
            gone = r.rank is None
            rows.append(
                (
                    _readable(r.rank, gone), who, symbol, company, r.decision,
                    _readable(r.score, gone), _readable(r.reasons, gone), text(r.change),
                    text(r.previous_decision), text(r.regime), text(r.size_multiplier),
                    ",".join(r.flags), _metrics(r, hidden),
                    *(_kinded(v, k) for v, k in zip(got.rows[i], got.kinds[i], strict=True)),
                )
            )  # fmt: skip
        if not got.results or len(rows) >= total:
            break
        page += 1
    return Exported(headers, tuple(rows[:ROW_CAP]), total)


UNIVERSE_HEADERS = ("instrument_id", "symbol", "company", "security_type")


def universe(ctx: ReadContext, filters: Sequence[FilterInput], params: Params) -> Exported:
    """The universe table under ``filters`` with the catalogue ``columns``, in symbol order."""
    headers = (*UNIVERSE_HEADERS, *dict.fromkeys(params.columns))
    rows: list[tuple[str, ...]] = []
    total, page = 0, 1
    while len(rows) < ROW_CAP:
        got = universe_table.load_table(
            ctx, params.columns, None, None, page, CHUNK, None, tuple(filters)
        )
        total = got.total
        for i, who in enumerate(got.instruments):
            cells: Any = zip(got.rows[i], got.kinds[i], strict=True)
            rows.append(
                (
                    who.instrument_id, who.symbol, who.name, text(who.security_type),
                    *(_kinded(v, k) for v, k in cells),
                )
            )  # fmt: skip
        if not got.instruments or len(rows) >= total:
            break
        page += 1
    return Exported(headers, tuple(rows[:ROW_CAP]), total)


SURFACES: dict[str, Surface] = {
    "ideas": ideas,
    "screener_results": screener_results,
    "universe": universe,
}
