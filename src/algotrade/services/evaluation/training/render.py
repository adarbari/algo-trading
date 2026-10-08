"""The scorer as a TOML expression feature (ADR 0053 amendment, ED7; the regime probit's
precedent: coefficients in site config, applied by the expression engine's ``ncdf``).

``render_scorer`` writes one ``[edge_score_<edge>]`` table: the formula
``ncdf(b0 + w1 * (x1 - m1) / s1 + ...)`` over the declared features with every coefficient a
``params`` entry, and a description that records the fit (``fitted_through``, rows, sessions,
horizon). ``merge_scorers`` puts a rendered table into the text of
``config/site/features/edge_scores.toml``, replacing that edge's table and keeping the others
sorted by name. A site config change reviewed via PR: ``fit-edge-scorer`` writes the file, the
owner commits it."""

import re

from algotrade.core.model.errors import ConfigurationError
from algotrade.features.registry import GROUPS
from algotrade.services.evaluation.training.fit import ScorerFit

FILE_HEADER = """# Learned edge scorers (ADR 0053 amendment, ED7): one probit expression feature per
# edge, written by `algotrade-backtest fit-edge-scorer --edge ID`, never by hand. The
# coefficients are fitted on the edge's training frame (features at the decision session, the
# edge's hit at the entry session) over windows closed before frozen_from less one horizon:
# `fitted_through` in the description is always before the edge's frozen_from (a fitness test).
# A re-fit raises the version. Language and keys: docs/configuration.md "Expression features".
"""
PREFIX = "edge_score_"
_HEADER = re.compile(r"^\[([A-Za-z0-9_]+)\]\s*$", re.MULTILINE)


def feature_name(edge_id: str) -> str:
    return f"{PREFIX}{edge_id}"


def expression_name(field: str) -> str:
    """The expression-language name of a selection field: ``rollup.<group>@v<n>.<col>`` is
    ``<group>.<col>``, ``feature.<name>`` is ``<name>``."""
    if field.startswith("feature."):
        return field.removeprefix("feature.")
    head, _, column = field.removeprefix("rollup.").rpartition(".")
    return f"{head.split('@')[0]}.{column}"


def check_versions(fields: tuple[str, ...]) -> None:
    """Each ``rollup.<group>@v<n>.<col>`` must name the registry's current version of its group:
    coefficients fitted on v2 must not silently apply to v3's values. Raises
    ``ConfigurationError``."""
    for field in fields:
        if not field.startswith("rollup."):
            continue
        name, _, rest = field.removeprefix("rollup.").partition("@v")
        declared = int(rest.split(".")[0])
        current = max((g.version for g in GROUPS.values() if g.name == name), default=None)
        if declared != current:
            raise ConfigurationError(
                f"{field}: group {name} is at v{current} now; refit on its current version"
            )


def render_scorer(fit: ScorerFit, version: int = 1) -> str:
    check_versions(fit.features)
    params = {"b0": fit.intercept}
    terms = ["b0"]
    for i, name in enumerate(fit.features, start=1):
        params[f"w{i}"], params[f"m{i}"], params[f"s{i}"] = (
            fit.weights[i - 1],
            fit.means[i - 1],
            fit.scales[i - 1],
        )
        terms.append(f"w{i} * ({expression_name(name)} - m{i}) / s{i}")
    body = ", ".join(f"{k} = {v!r}" for k, v in params.items())
    expr = " + ".join(terms)
    names = ", ".join(fit.features)
    about = (
        f"Fitted probability that edge {fit.edge_id} hits (horizon={fit.horizon} sessions): "
        "a probit "
        f"on {names} standardised on the training rows. fitted_through={fit.fitted_through}; "
        f"{fit.rows} rows, {fit.sessions} sessions, {fit.positives} hits."
    )
    return "\n".join(
        [
            f"[{feature_name(fit.edge_id)}]",
            f'expr = "ncdf({expr})"',
            f"params = {{ {body} }}",
            'dtype = "float"',
            'unit = "decimal"',
            "valid_range = [0, 1]",
            f'description = "{about}"',
            'null_meaning = "a feature is null (UNKNOWN) for the instrument and session"',
            f"version = {version}",
            "",
        ]
    )


def merge_scorers(existing: str, edge_id: str, table: str) -> str:
    """``existing`` (the file's text, "" when new) with ``table`` (``render_scorer``'s) added, or
    replacing the edge's earlier one with its version raised by one."""
    tables = _tables(existing)
    name = feature_name(edge_id)
    bump = _next_version(tables.get(name))
    tables[name] = re.sub(r"^version = \d+", f"version = {bump}", table, flags=re.MULTILINE)
    return FILE_HEADER + "".join("\n" + tables[k] for k in sorted(tables))


def _tables(text: str) -> dict[str, str]:
    marks = list(_HEADER.finditer(text))
    return {
        m.group(1): text[
            m.start() : marks[i + 1].start() if i + 1 < len(marks) else len(text)
        ].strip("\n")
        + "\n"
        for i, m in enumerate(marks)
    }


def _next_version(table: str | None) -> int:
    found = re.search(r"^version = (\d+)", table or "", re.MULTILINE)
    return int(found.group(1)) + 1 if found else 1
