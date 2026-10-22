"""The fingerprint of a verdict headline (decision log 2026-10-22, "A stored edge verdict
headline"): a digest of everything the judge reads, so a stored headline is used only when
none of it changed. It covers the run judged, the whole ``JudgeCall``, the verdict settings,
the source of the judge (the verdict package and ``JUDGED_CODE``, the code outside it the
headline path runs, closed under the names it calls) and ``JUDGE_VERSION``, the knob for a
semantic change the source digest cannot see. Hashing is sha256 over sorted canonical JSON,
never ``hash()`` (randomised per process)."""

import ast
import dataclasses
import hashlib
import importlib
import inspect
import json
from datetime import date, datetime
from functools import cache
from pathlib import Path
from typing import Any

from algotrade.config.edges.verdict import VerdictSettings
from algotrade.services.read.evaluation.verdict.rule import JudgeCall

JUDGE_VERSION = 1  # bump on a semantic change of the judge outside JUDGED_CODE (a parse, a column)

# Each name outside the verdict package that the headline path runs, as ``module:name`` (a
# function, a class or a module constant): the source digest hashes its definition. The fitness
# test (tests/unit/.../test_fingerprint.py) lists every name the package imports from outside
# and requires it here or in its own ``NOT_JUDGED`` with a reason.
JUDGED_CODE: tuple[str, ...] = (
    "algotrade.config.edges.named:OUT_OF_WINDOW",
    "algotrade.config.edges.verdict:VerdictSettings",
    "algotrade.quant.edges.statistics:_finite",
    "algotrade.quant.edges.statistics:percentile_of",
    "algotrade.services.read.evaluation.robustness:beat_share",
    "algotrade.services.read.evaluation.robustness:draw_lifts",
    "algotrade.services.read.evaluation.runs:BASELINE",
    "algotrade.services.read.evaluation.runs:DECILES",
    "algotrade.services.read.evaluation.runs:EDGE_EVAL",
    "algotrade.services.read.evaluation.runs:Draw",
    "algotrade.services.read.evaluation.runs:EdgeRow",
    "algotrade.services.read.evaluation.runs:IN_SAMPLE",
    "algotrade.services.read.evaluation.runs:MAIN",
    "algotrade.services.read.evaluation.runs:MEMBER",
    "algotrade.services.read.evaluation.runs:RANDOM",
    "algotrade.services.read.evaluation.runs:_day_of",
    "algotrade.services.read.evaluation.runs:_deciles",
    "algotrade.services.read.evaluation.runs:_draws_of",
    "algotrade.services.read.evaluation.runs:_exits",
    "algotrade.services.read.evaluation.runs:_float",
    "algotrade.services.read.evaluation.runs:_int",
    "algotrade.services.read.evaluation.runs:_row",
    "algotrade.services.read.evaluation.runs:_rows_of",
    "algotrade.services.read.evaluation.runs:_in_sample_only",
    "algotrade.services.read.evaluation.runs:_stored",
    "algotrade.services.read.evaluation.runs:_text",
    "algotrade.services.read.evaluation.runs:_without_oos_counts",
    "algotrade.services.read.evaluation.runs:COST",
    "algotrade.services.read.evaluation.runs:SIDE_PARTS",
    "algotrade.services.read.evaluation.runs:draws_of_record",
    "algotrade.services.read.evaluation.runs:load_run_draws",
    "algotrade.services.read.evaluation.runs:load_run_rows",
    "algotrade.services.read.evaluation.runs:rows_of_record",
    "algotrade.services.read.evaluation.runs:lift_points",
    "algotrade.services.read.evaluation.runs:rows_of_frame",
    "algotrade.services.read.values:to_scalar",
)


def _plain(node: ast.AST) -> ast.AST:
    """``node`` without docstrings (comments and formatting are not in an AST): an edit that
    only rewords documentation never changes the digest."""
    for n in ast.walk(node):
        body = getattr(n, "body", None)
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            n.body = body[1:] or [ast.Pass()]
    return node


def _dump(source: str) -> str:
    return ast.dump(_plain(ast.parse(source)))


def _definition(entry: str) -> str:
    """The AST dump of the top-level definition ``module:name`` (a def, a class or an
    assignment); an entry that names nothing is an error, never an empty digest."""
    module, name = entry.split(":")
    source = inspect.getsource(importlib.import_module(module))
    for node in ast.parse(source).body:
        names = (
            [node.name]
            if isinstance(node, (ast.FunctionDef, ast.ClassDef))
            else [t.id for t in node.targets if isinstance(t, ast.Name)]
            if isinstance(node, ast.Assign)
            else [node.target.id]
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
            else []
        )
        if name in names:
            return ast.dump(_plain(node))
    raise LookupError(f"JUDGED_CODE names {entry}, which does not exist")


def digest_of(package: Path, entries: tuple[str, ...]) -> str:
    """The source digest of every module of ``package`` and of ``entries``."""
    parts = [f"{f.name}:{_dump(f.read_text())}" for f in sorted(package.glob("*.py"))]
    parts += [f"{e}:{_definition(e)}" for e in sorted(entries)]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


@cache
def judge_digest() -> str:
    """The digest of the judge's source, computed once per process (a Python upgrade changes
    ``ast.dump`` and so invalidates every stored row once: accepted)."""
    return digest_of(Path(__file__).parent, JUDGED_CODE)


def _jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, float):  # also numpy's float64, whose own repr is ``np.float64(x)``
        return float.__repr__(float(value))
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        items = [_jsonable(v) for v in value]
        return sorted(items, key=str) if isinstance(value, (set, frozenset)) else items
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"cannot fingerprint a {type(value).__name__}: {value!r}")  # never a repr


def canonical_json(value: Any) -> str:
    """``value`` as sorted, compact JSON: dates ISO, tuples lists, dataclasses by field (a
    callable is not a value and fails loudly), floats by ``repr``."""
    return json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":"))


def settings_hash(settings: VerdictSettings) -> str:
    """The hash of the verdict thresholds (``verdict.toml`` merged over the code defaults)."""
    return hashlib.sha256(canonical_json(settings).encode()).hexdigest()


def _without_callables(call: JudgeCall) -> JudgeCall:
    """The call as a headline sees it: the haircut's readers are not inputs of the headline."""
    return dataclasses.replace(
        call, facts=dataclasses.replace(call.facts, measured=None, site_trials=None)
    )


def fingerprint(call: JudgeCall, judged_run_id: str, settings: VerdictSettings) -> str:
    """The fingerprint of the headline of ``call`` judged on run ``judged_run_id``: equal only
    when the run, every judge input, the settings, the judge's source and ``JUDGE_VERSION`` are."""
    body = {
        "judge_version": JUDGE_VERSION,
        "judge_digest": judge_digest(),
        "settings_hash": settings_hash(settings),
        "judged_run_id": judged_run_id,
        "call": _without_callables(call),
    }
    return hashlib.sha256(canonical_json(body).encode()).hexdigest()
