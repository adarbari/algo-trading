"""A user's own edges against the ones they extend (ADR 0053 amendment 2026-10-09, ED8): the
verdict of a copy, the comparison of its latest run with the edge it extends and with its
baselines, and the layered document an admin publishes.

The fair test is withheld SERVER SIDE: a copy's out-of-sample result stays hidden until the user
shows it (``Edge.oos_hidden``: they have not followed it nor asked to see it). Until then
``runs.load_run_rows`` serves its in-sample rows only, its verdict is judged on those (it can
say Not working or Not enough data, never Promising or Works) with the reason saying so, and the
comparison carries in-sample figures only with ``oos_hidden`` set. The browser never filters.

The statistics are the stored rows', never recomputed; the sentences are the server's."""

from collections.abc import Sequence
from dataclasses import dataclass, replace

from algotrade.config.edges import loading
from algotrade.config.site.settings import load_verdict as load_verdict_settings
from algotrade.services.read.context import Stores
from algotrade.services.read.evaluation import runs, verdict
from algotrade.services.read.evaluation.edges import Edge, load_edge
from algotrade.services.read.evaluation.runs import EdgeRow, EdgeRun
from algotrade.storage.configs.toml_text import toml_text

HIDDEN_WORDS = (
    "Judged on in-sample figures only: the out-of-sample result stays hidden until you show it."
)
OUT_OF_SAMPLE = ("frozen", "split")  # the slice after the split: frozen_from's, or a moved split


@dataclass(frozen=True)
class Figures:
    """One period's figures of one screen at one horizon (None: not stored). ``trades`` are the
    independent sessions."""

    win_rate: float | None
    base_rate: float | None
    lift_pts: float | None
    decile_spread: float | None
    trades: int | None


@dataclass(frozen=True)
class CompareRow:
    """One line of the comparison: ``kind`` is ``this`` (the edge's latest run of yours),
    ``extended`` (the edge it is a copy of, its official result) or ``baseline``; ``basis`` the
    screen and holding period; ``out_of_sample`` is None when it is hidden (``oos_hidden``) or
    not stored."""

    kind: str
    label: str
    edge_id: str | None
    run_id: str | None
    basis: str
    in_sample: Figures | None
    out_of_sample: Figures | None
    oos_hidden: bool


@dataclass(frozen=True)
class EdgeCompare:
    """``Edge.compare``: the lines (empty with a ``reason`` when there is nothing to compare);
    ``oos_hidden``: this edge's out-of-sample figures are withheld."""

    edge_id: str
    extends: str | None
    oos_hidden: bool
    reason: str
    rows: tuple[CompareRow, ...] = ()


def own_run(ctx: Stores, edge: Edge) -> EdgeRun | None:
    """The latest committed run of ``edge`` made by the user (a copy has no site run)."""
    found = [r for r in runs.load_edge_runs(ctx, edge) if r.owner == ctx.user.user_id]
    return found[0] if found else None


def _official(rows: Sequence[EdgeRow], hidden: bool) -> tuple[EdgeRow, ...]:
    """``rows`` as the verdict rule reads an official result: the user's own run is not
    exploratory against itself; hidden, only the in-sample rows exist, standing for the whole
    history and the frozen slice, so no figure of the withheld period can enter; revealed, a
    moved split's ``split`` slice stands for ``frozen``."""
    own = [replace(r, exploratory=False) for r in rows]
    if hidden:
        before = [r for r in own if r.slice_kind == runs.IN_SAMPLE]
        return tuple(
            replace(r, slice_kind=k, slice_value=k) for r in before for k in ("all", "frozen")
        )
    if any(r.slice_kind == "frozen" for r in own):
        return tuple(own)
    return tuple(
        replace(r, slice_kind="frozen", slice_value="frozen") if r.slice_kind == "split" else r
        for r in own
    )


def _in_sample_words(text: str) -> str:
    return text.replace("Out-of-sample", "In-sample").replace("out-of-sample", "in-sample")


def load_verdict(ctx: Stores, edge: Edge) -> verdict.EdgeVerdict:
    """The verdict of ``edge``: a site edge's official result (``verdict.load_edge_verdict``);
    a user's own edge from the user's latest run of it, judged on in-sample figures only while
    its out-of-sample result is hidden."""
    if not edge.mine:
        return verdict.load_edge_verdict(ctx, edge)
    settings = load_verdict_settings(ctx.configs)
    run = own_run(ctx, edge)
    if run is None:
        return verdict.judge(edge.id, None, edge.frozen_from, settings)
    hidden = edge.oos_hidden
    rows = _official(runs.load_run_rows(ctx, run), hidden)
    found = verdict.judge(
        edge.id,
        rows,
        edge.frozen_from,
        settings,
        run.lost_inputs,
        decoys=bool(edge.baselines),
    )
    if not hidden or found.verdict == verdict.WAITING:
        return found
    return replace(
        found,
        rationale=_in_sample_words(found.rationale),
        headline=f"{HIDDEN_WORDS} {_in_sample_words(found.headline)}",
        result=_in_sample_words(found.result),
        criteria=tuple(
            replace(c, label=_in_sample_words(c.label), threshold=_in_sample_words(c.threshold))
            for c in found.criteria
        ),
    )


def verdict_level(ctx: Stores, edge_id: str) -> str | None:
    """The verdict level (``works`` .. ``waiting_on_data``) of the edge ``edge_id`` the user sees,
    None when they see none: what a follow is checked against."""
    edge = load_edge(ctx, edge_id)
    return None if edge is None else load_verdict(ctx, edge).verdict


def _figures(row: EdgeRow) -> Figures:
    return Figures(
        row.hit_rate,
        row.base_rate,
        runs.lift_points(row.hit_rate, row.base_rate),
        row.decile_spread,
        row.sessions,
    )


def _pick(
    rows: Sequence[EdgeRow], variant: str, horizon: int, kinds: tuple[str, ...], role: str
) -> EdgeRow | None:
    found = [
        r
        for r in rows
        if r.edge_variant == runs.MAIN
        and r.variant == variant
        and r.horizon_sessions == horizon
        and r.slice_kind in kinds
        and (r.role == "baseline") == (role == "baseline")
    ]
    return found[0] if len(found) == 1 else None


def _basis(rows: Sequence[EdgeRow]) -> tuple[str, int] | None:
    """The (screen, horizon) with the best in-sample lift (out-of-sample when none has one): the
    figure every line of a comparison is read at."""
    best: tuple[float, str, int] | None = None
    for kinds in ((runs.IN_SAMPLE,), OUT_OF_SAMPLE):
        for r in rows:
            if r.edge_variant != runs.MAIN or r.role == "baseline" or r.slice_kind not in kinds:
                continue
            pts = runs.lift_points(r.hit_rate, r.base_rate)
            if pts is not None and (best is None or pts > best[0]):
                best = (pts, r.variant, r.horizon_sessions)
        if best is not None:
            break
    return None if best is None else (best[1], best[2])


def _line(
    kind: str,
    label: str,
    edge_id: str | None,
    run: EdgeRun,
    rows: Sequence[EdgeRow],
    variant: str,
    horizon: int,
    hidden: bool,
    role: str,
) -> CompareRow | None:
    before = _pick(rows, variant, horizon, (runs.IN_SAMPLE,), role)
    after = None if hidden else _pick(rows, variant, horizon, OUT_OF_SAMPLE, role)
    if before is None and after is None and not hidden:
        return None
    return CompareRow(
        kind=kind,
        label=label,
        edge_id=edge_id,
        run_id=run.run_id,
        basis=f"{variant}, {horizon} trading days",
        in_sample=_figures(before) if before is not None else None,
        out_of_sample=_figures(after) if after is not None else None,
        oos_hidden=hidden,
    )


def _extended(ctx: Stores, edge: Edge) -> tuple[Edge, EdgeRun | None] | None:
    """The edge ``edge`` extends and its official run (a site edge's canonical run; the
    user's own edge's latest run)."""
    parent = load_edge(ctx, edge.extends) if edge.extends else None
    if parent is None:
        return None
    return parent, (
        own_run(ctx, parent) if parent.mine else runs.load_canonical_run(ctx, parent).run
    )


def load_compare(ctx: Stores, edge: Edge) -> EdgeCompare | None:
    """The comparison of ``edge`` (the user's own), None for a site edge: its latest run of yours
    against the edge it extends and its baselines, in-sample only while its out-of-sample result
    is hidden. Empty with the reason when there is no run to compare."""
    if not edge.mine:
        return None
    hidden = edge.oos_hidden
    run = own_run(ctx, edge)
    if run is None:
        return EdgeCompare(edge.id, edge.extends, hidden, "You have not run this edge yet")
    rows = runs.load_run_rows(ctx, run)
    found = _basis(rows)
    if found is None:
        return EdgeCompare(edge.id, edge.extends, hidden, "The run has no figures to compare")
    variant, horizon = found
    lines: list[CompareRow | None] = [
        _line("this", edge.name, edge.id, run, rows, variant, horizon, hidden, "implementation")
    ]
    parent = _extended(ctx, edge)
    if parent is not None and parent[1] is not None:
        other, other_run = parent[0], parent[1]
        other_rows = runs.load_run_rows(ctx, other_run)
        basis = _basis(other_rows)
        if basis is not None:
            v, h = (
                (variant, horizon)
                if _pick(
                    other_rows, variant, horizon, (runs.IN_SAMPLE, *OUT_OF_SAMPLE), "implementation"
                )
                else basis
            )
            lines.append(
                _line(
                    "extended",
                    other.name,
                    other.id,
                    other_run,
                    other_rows,
                    v,
                    h,
                    other.oos_hidden,
                    "implementation",
                )
            )
    for name in sorted(
        {r.variant for r in rows if r.role == "baseline" and r.horizon_sessions == horizon}
    ):
        lines.append(_line("baseline", name, None, run, rows, name, horizon, hidden, "baseline"))
    return EdgeCompare(edge.id, edge.extends, hidden, "", tuple(x for x in lines if x is not None))


def load_published_document(ctx: Stores, edge_id: str) -> str | None:
    """The layered document of the edge ``edge_id`` as the user sees it, as TOML (None: they
    see no such edge): ``extends`` resolved (a copy is one whole document), the user's
    ``[follow]`` and ``extends`` left out. What an admin lands in ``config/site/edges/<id>.toml``
    by pull request: the site's config changes only by PR, so publishing is a read."""
    if load_edge(ctx, edge_id) is None:
        return None
    merged = loading.layered_documents(ctx.configs, ctx.user.user_id)[edge_id]
    return toml_text({k: v for k, v in merged.items() if k not in ("follow", "extends")})
