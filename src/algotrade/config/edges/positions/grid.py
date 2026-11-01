"""``[[variant_grid]]`` (ADR 0088, design 2.7): a grid over the literal parameters of an option
outcome that expands to one variant per point, each a trial of the deflated Sharpe ratio. Parsed
here fail closed; ``points`` is the deterministic expansion (axes in ``AXES`` order, each axis
ascending, last axis fastest), ids like ``g_d20_t30_tp50``. Wiring the points into an edge's
variants is the harness slice's."""

from dataclasses import dataclass
from itertools import product

from algotrade.config.site.fields import Table
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.ids import validate_id

# axis -> (id letters, scale of the id number): strike_delta 0.20 -> d20, take_profit 0.5 -> tp50
AXES: dict[str, tuple[str, int]] = {
    "strike_delta": ("d", 100), "tenor_days": ("t", 1), "take_profit": ("tp", 100),
    "stop_loss": ("sl", 100), "exit_dte": ("dte", 1),
}  # fmt: skip
INTEGER_AXES = ("tenor_days", "exit_dte")
MAX_POINTS = 64
KEYS = ("prefix", *AXES)


@dataclass(frozen=True)
class Grid:
    prefix: str
    axes: tuple[tuple[str, tuple[float, ...]], ...]  # in ``AXES`` order, values ascending


@dataclass(frozen=True)
class GridPoint:
    id: str
    values: tuple[tuple[str, float], ...]  # the outcome keys it overrides


def _axis(t: Table, name: str) -> tuple[float, ...]:
    raw = t.raw(name)
    numeric = isinstance(raw, list) and all(
        isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0 for v in raw
    )
    whole = name not in INTEGER_AXES or all(type(v) is int for v in raw or ())
    if not numeric or not raw or not whole or list(raw) != sorted(set(raw)):
        raise ConfigurationError(
            f"{t.where} {name}: expected one or more ascending, distinct "
            f"{'integers' if name in INTEGER_AXES else 'numbers'} >= 0, got {raw!r}"
        )
    return tuple(raw)


def parse_grids(t: Table) -> tuple[Grid, ...]:
    """The edge's ``[[variant_grid]]`` tables (none: ``()``)."""
    grids: list[Grid] = []
    for g in t.tables("variant_grid"):
        g.only(KEYS)
        prefix = validate_id("variant", g.text("prefix", ""))
        axes = tuple((name, _axis(g, name)) for name in AXES if name in g.names())
        if not axes:
            raise ConfigurationError(f"{g.where}: names no axis of {list(AXES)}")
        size = 1
        for _, values in axes:
            size *= len(values)
        if size > MAX_POINTS:
            raise ConfigurationError(f"{g.where}: {size} points, at most {MAX_POINTS}")
        if prefix in {x.prefix for x in grids}:
            raise ConfigurationError(f"{g.where} prefix: {prefix!r} is listed twice")
        grids.append(Grid(prefix, axes))
    return tuple(grids)


def points(grid: Grid) -> tuple[GridPoint, ...]:
    """Every point of ``grid`` in a fixed order, each with its id."""
    out = []
    for combo in product(*(values for _, values in grid.axes)):
        named = tuple(zip((n for n, _ in grid.axes), combo, strict=True))
        parts = [f"{AXES[n][0]}{round(v * AXES[n][1])}" for n, v in named]
        values = tuple((n, int(v) if n in INTEGER_AXES else float(v)) for n, v in named)
        out.append(GridPoint("_".join([grid.prefix, *parts]), values))
    ids = [p.id for p in out]
    if len(set(ids)) != len(ids):
        raise ConfigurationError(f"variant_grid {grid.prefix!r}: two points share an id")
    return tuple(out)


def grid_ids(grids: tuple[Grid, ...]) -> tuple[str, ...]:
    """Every point id of every grid (for a clash check against the edge's own variants)."""
    return tuple(p.id for g in grids for p in points(g))
