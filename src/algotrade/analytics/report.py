"""Render tabular results as Markdown (for CI job summaries and PR comments)."""

from collections.abc import Mapping, Sequence

PERCENT_FIELDS = {
    "total_return",
    "excess_return",
    "cagr",
    "annual_volatility",
    "max_drawdown",
    "exposure",
}


def _fmt(key: str, value: float | str) -> str:
    if isinstance(value, str):
        return value
    if key in PERCENT_FIELDS:
        return f"{value:.2%}"
    if key == "num_trades":
        return f"{int(value)}"
    return f"{value:.2f}"


def markdown_table(rows: Sequence[Mapping[str, float | str]], columns: Sequence[str]) -> str:
    header = "| " + " | ".join(columns) + " |"
    divider = "|" + "|".join("---" for _ in columns) + "|"
    body = ["| " + " | ".join(_fmt(c, row[c]) for c in columns) + " |" for row in rows]
    return "\n".join([header, divider, *body])
