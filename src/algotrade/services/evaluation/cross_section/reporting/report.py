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
    ("unscored", "unscored", "{}"), ("excluded_score_coverage", "no deciles", "{}"),
    ("excluded_coverage", "unmeasured", "{}"),
    ("deflated_sharpe", "DSR", "{:.2f}"), ("pbo", "PBO", "{:.2f}"),
)  # fmt: skip


def _cell(row: Mapping[str, Any], key: str, fmt: str) -> str:
    value = row.get(key)
    if key == "slice":
        value = f"{row['slice_kind']}={row['slice_value']}"
        if row.get("exploratory"):
            value += " (EXPLORATORY)"
    elif key == "variant" and row.get("edge_variant"):
        value = f"{row['edge_variant']}/{value}"  # an edge variant (null: the edge itself)
    return "-" if value is None else fmt.format(value)


def render_edge_report(result: Mapping[str, Any]) -> str:
    """The report of one ``edge-eval`` job result."""
    lines = [f"# Edge {result['edge']} (run {result['run_id']}, {result['trials']} trials)", ""]
    if result.get("exploratory"):
        lines.append(
            f"EXPLORATORY: test split from {result['split_from']} is not the edge's frozen_from; "
            "never evidence"
        )
    for horizon, (n, m) in result["survivorship"].items():
        lines.append(
            f"SURVIVORSHIP: {n} of {m} sessions (h={horizon}) before the first universe "
            f"snapshot {result['universe_snapshot']}"
        )
    historical = result.get("historical_identity")
    if historical:
        e, k = historical["eligible"], historical["screened"]
        lines.append(
            f"HISTORICAL IDENTITY: {historical['sessions']} sessions before the first reference "
            f"snapshot. Rule: {historical['rule']}. Eligible names: {e['today_flag']} by today's "
            f"flag, {e['proxy']} by the liquidity proxy; screened: {k['today_flag']} and "
            f"{k['proxy']}"
        )
    for horizon, n in result["unclosed_sessions"].items():
        lines.append(f"UNCLOSED: {n} start sessions at h={horizon} have no closed window")
    for lost in result.get("lost_sessions", []):
        lines.append(
            f"LOST: {lost['variant']} h={lost['horizon']} lost {lost['sessions']} sessions: "
            f"no data in {lost['table']} (counted as unmeasured, not a miss)"
        )
    for c in result.get("report_containment", []):
        share = c["contained"] / c["windows"] if c["windows"] else None
        lines.append(
            f"CONTAINED: {c['variant']} h={c['horizon']} contained the report: "
            f"{'-' if share is None else f'{share:.0%}'} of {c['windows']} windows "
            f"({c['no_report']} with no later report stored; a diagnostic, never a filter)"
        )
    rows: Sequence[Mapping[str, Any]] = result["rows"]
    header = "| " + " | ".join(label for _, label, _ in COLUMNS) + " |"
    divider = "|" + "|".join("---" for _ in COLUMNS) + "|"
    body = ["| " + " | ".join(_cell(r, key, fmt) for key, _, fmt in COLUMNS) + " |" for r in rows]
    return "\n".join([*lines, "", header, divider, *body, ""])
