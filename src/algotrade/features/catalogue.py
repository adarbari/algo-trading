"""The feature catalogue: every feature of every registered group, rendered as Markdown.

``render()`` is the content of ``docs/data/features.md`` (written by ``make features-doc``;
a fitness test keeps the committed file up to date). Per group: its table, inputs and
description; per feature: kind, type, unit, valid values (range or categories),
description, when it is null, and what it is computed from.
"""

from algotrade.features.framework.declaration import FeatureGroup
from algotrade.features.framework.feature import Feature
from algotrade.features.registry import FEATURES, GROUPS

PATH = "docs/data/features.md"
HEADER = """# Feature catalogue

Generated from `src/algotrade/features/registry.py` by `make features-doc`; do not edit by
hand (a fitness test fails when it is out of date). The model is in
[ADR 0023](../adr/0023-feature-store.md); how groups are computed and stored is in
[layers.md](layers.md#rollups-as-built).

A feature is `<group>.<column>@v<N>`, selectable as `rollup.<group>@v<N>.<column>`. Null is
UNKNOWN, never zero: "Null when" says why a value can be missing. Valid values are a sanity
range (values outside are kept, not clipped) or a label's categories. Units: `decimal` is a
fraction (0.25 = 25%), `pct_points` a quoted percentage (25 = 25%), `sessions` exchange
sessions, `days` calendar days.
"""


def _number(value: float) -> str:
    return f"{value:g}"


def valid_values(f: Feature) -> str:
    if f.categories:
        return ", ".join(f.categories)
    if f.valid_range is None:
        return ""
    lo, hi = f.valid_range
    if lo is not None and hi is not None:
        return f"{_number(lo)} .. {_number(hi)}"
    if lo is not None:
        return f">= {_number(lo)}"
    return f"<= {_number(hi)}" if hi is not None else ""


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _group(g: FeatureGroup) -> list[str]:
    inputs = ", ".join(f"`{i.table}`" + ("" if i.required else " (optional)") for i in g.inputs)
    lines = [
        f"## `{g.key}`",
        "",
        f"{g.description}. Stored as `{g.table}`; reads {inputs}.",
        "",
        "| Feature | Kind | Type | Unit | Valid values | Description | Null when | Inputs |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for f in g.features:
        cells = [
            f"`{f.name}`",
            f.kind,
            f.dtype,
            f.unit,
            valid_values(f),
            f.description,
            f.null_meaning,
            ", ".join(f"`{r}`" for r in f.inputs),
        ]
        lines.append("| " + " | ".join(_cell(c) for c in cells) + " |")
    return [*lines, ""]


def render() -> str:
    """The whole catalogue (``docs/data/features.md``)."""
    lines = [
        HEADER,
        f"{len(FEATURES)} features in {len(GROUPS)} groups, in dependency order.",
        "",
    ]
    for g in GROUPS.values():
        lines += _group(g)
    return "\n".join(lines).rstrip() + "\n"
