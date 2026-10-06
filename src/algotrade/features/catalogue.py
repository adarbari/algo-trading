"""The feature catalogue: every feature of the site's ``FeatureSet``, rendered as Markdown.

``render(features)`` is the content of ``docs/data/features.md`` (written by
``make features-doc`` from the repository's ``config/``; a fitness test keeps the committed
file up to date). Per code group: its table, inputs and description; per feature: kind,
type, unit, licence, valid values (range or categories), description, when it is null, and what it
is computed from. Then the market features (the market-entity groups, one ``MKT:US`` row
per session; ADR 0047), when there are any, the expression features by theme file (formula,
and where it is stored when materialised) and the superseded group versions.
"""

from algotrade.features.expressions.definitions import Expression
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.framework.declaration import FeatureGroup
from algotrade.features.framework.feature import Feature

PATH = "docs/data/features.md"
HEADER = """# Feature catalogue

Generated from `src/algotrade/features/registry.py` (code groups) and
`config/site/features/*.toml` (expression features) by `make features-doc`; do not edit by
hand (a fitness test fails when it is out of date). The model is in
[ADR 0023](../adr/0023-feature-store.md); how groups are computed and stored is in
[layers.md](layers.md#rollups-as-built); the expression language is in
[configuration.md](../configuration.md#expression-features).

A group feature is `<group>.<column>@v<N>`, selectable as `rollup.<group>@v<N>.<column>`; an
expression feature is `<name>@v<N>`, selectable as `feature.<name>` and computed on read from
the stored features it names (unless materialised). Null is UNKNOWN, never zero: "Null when"
says why a value can be missing. Valid values are a sanity range or a label's categories:
values outside a range are kept, never clipped, and are reported by the feature-quality
checks (ADR 0023, step 7). Units: `decimal` is a fraction (0.25 = 25%), `pct_points` a
quoted percentage (25 = 25%), `sessions` exchange sessions, `days` calendar days. Types:
`float32` is a 32-bit float (about 7 significant digits). Licence: `open` (computed by us
from free data) or `personal` (derived from IBKR market data, a personal-use licence: the API
will show it to the owner only once there are other users;
[ADR 0028](../adr/0028-ibkr-enrichment-source.md)); an expression feature takes the most
restrictive licence of its inputs.
"""
_COLUMNS = "| Feature | Kind | Type | Unit | Licence | Valid values | Description | Null when |"


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


def _row(f: Feature, *extra: str) -> str:
    cells = [f"`{f.name}`", f.kind, f.dtype, f.unit, f.licence, valid_values(f),
             f.description, f.null_meaning, *extra]  # fmt: skip
    return "| " + " | ".join(_cell(c) for c in cells) + " |"


def _group(g: FeatureGroup, level: str = "##") -> list[str]:
    inputs = ", ".join(f"`{i.key}`" + ("" if i.required else " (optional)") for i in g.inputs)
    lines = [
        f"{level} `{g.key}`",
        "",
        f"{g.description}. Stored as `{g.table}`; reads {inputs}.",
        "",
        f"{_COLUMNS} Inputs |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    lines += [_row(f, ", ".join(f"`{r}`" for r in f.inputs)) for f in g.features]
    return [*lines, ""]


def _market(groups: list[FeatureGroup]) -> list[str]:
    if not groups:
        return []
    lines = [
        "## Market features",
        "",
        "Market-entity groups (ADR 0047): one row per "
        "session for the whole market (`instrument_id` `MKT:US`), stored as "
        "`rollups/market/<group>@v<N>` and read as `market.<group>@v<N>.<column>`, never "
        "selected per instrument.",
        "",
    ]
    for g in groups:
        lines += _group(g, "###")
    return lines


def _formula(e: Expression) -> str:
    text = " ".join(e.definition.expr.split())
    params = ", ".join(f"{k} = {v!r}" for k, v in e.definition.params.items())
    return f"`{text}`" + (f" ({params})" if params else "")


def _expressions(fs: FeatureSet) -> list[str]:
    lines = [
        "## Expression features",
        "",
        "Declared in `config/site/features/<theme>.toml`; virtual (computed on read) unless "
        "stored (materialised, by the `rollups` task after its inputs).",
        "",
    ]
    themes = sorted({e.definition.theme for e in fs.expressions.values()})
    for theme in themes:
        lines += [
            f"### `{theme}.toml`",
            "",
            f"{_COLUMNS} Formula | Stored |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for e in fs.expressions.values():
            if e.definition.theme == theme:
                stored = f"`{fs.table(e.name)}`" if e.materialise else "virtual"
                lines.append(_row(e.feature, _formula(e), stored))
        lines.append("")
    return lines


def _superseded(fs: FeatureSet) -> list[str]:
    lines = [
        "## Superseded groups",
        "",
        "Readable until retired (`algotrade-ingest retire-features --group <key>`); their "
        "selection fields fail with the field that replaced them.",
        "",
        "| Group | Replaced by |",
        "|---|---|",
    ]
    for key, old in fs.superseded.items():
        moves = ", ".join(
            f"`{c}` -> `{n}`" if n else f"`{c}` retired" for c, n in old.fields.items()
        )
        lines.append(
            f"| `{key}` | `{old.by}` + expression features" + (f"; {moves}" if moves else "") + " |"
        )
    return [*lines, ""]


def render(fs: FeatureSet) -> str:
    """The whole catalogue (``docs/data/features.md``)."""
    groups = [g for g in fs.groups.values() if g.key in fs.code]
    stored = sum(len(g.features) for g in groups)
    lines = [
        HEADER,
        f"{stored} stored features in {len(groups)} groups, in dependency order; "
        f"{len(fs.expressions)} expression features.",
        "",
    ]
    for g in groups:
        if g.entity == "instrument":
            lines += _group(g)
    lines += _market([g for g in groups if g.entity == "market"])
    lines += _expressions(fs)
    lines += _superseded(fs)
    return "\n".join(lines).rstrip() + "\n"
