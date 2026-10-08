"""An edge evaluation as text (``algotrade-backtest evaluate-edges``): the survivorship line,
the unclosed sessions, then one table row per variant, horizon and slice with the number of
independent sessions beside the numbers. Pure: it renders the job's result dict."""

from collections.abc import Mapping, Sequence
from typing import Any

COLUMNS = (
    ("variant", "variant", "{}"), ("horizon_sessions", "h", "{}"), ("slice", "slice", "{}"),
    ("sessions", "sessions", "{}"), ("picks", "picks", "{}"), ("hit_rate", "hit", "{:.1%}"),
    ("base_rate", "base", "{:.1%}"), ("lift", "lift", "{:.2f}"),
    ("mean_excess_picks", "picks mean", "{:+.4f}"), ("bh_mean", "buy&hold", "{:+.4f}"),
    ("top_decile_mean", "top decile", "{:+.4f}"), ("decile_spread", "spread", "{:+.4f}"),
    ("decile_t", "t", "{:.2f}"), ("decile_sessions", "dec. sessions", "{}"),
    ("unscored", "unscored", "{}"), ("excluded_coverage", "unmeasured", "{}"),
    ("deflated_sharpe", "DSR", "{:.2f}"), ("pbo", "PBO", "{:.2f}"),
)  # fmt: skip


def _cell(row: Mapping[str, Any], key: str, fmt: str) -> str:
    value = f"{row['slice_kind']}={row['slice_value']}" if key == "slice" else row.get(key)
    return "-" if value is None else fmt.format(value)


def render_edge_report(result: Mapping[str, Any]) -> str:
    """The report of one ``edge-eval`` job result."""
    lines = [f"# Edge {result['edge']} (run {result['run_id']}, {result['trials']} trials)", ""]
    for horizon, (n, m) in result["survivorship"].items():
        lines.append(
            f"SURVIVORSHIP: {n} of {m} sessions (h={horizon}) before the first universe "
            f"snapshot {result['universe_snapshot']}"
        )
    for horizon, n in result["unclosed_sessions"].items():
        lines.append(f"UNCLOSED: {n} start sessions at h={horizon} have no closed window")
    rows: Sequence[Mapping[str, Any]] = result["rows"]
    header = "| " + " | ".join(label for _, label, _ in COLUMNS) + " |"
    divider = "|" + "|".join("---" for _ in COLUMNS) + "|"
    body = ["| " + " | ".join(_cell(r, key, fmt) for key, _, fmt in COLUMNS) + " |" for r in rows]
    return "\n".join([*lines, "", header, divider, *body, ""])
