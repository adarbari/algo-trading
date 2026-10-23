"""The fingerprint of a verdict headline: every judge input is in it, every line of judge code is
digested, the judge call equals the old assembly, and a judge change without a version bump
fails (the three fitness tests of the stored-verdict plan, PR 1)."""

import ast
import inspect
import shutil
from dataclasses import fields, replace
from datetime import date
from importlib import import_module
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import algotrade.services.read.evaluation.verdict.fingerprint as fp
from algotrade.config.edges.portfolio import PORTFOLIO_KIND
from algotrade.config.edges.portfolio import benchmark_words as benchword
from algotrade.config.edges.verdict import VerdictSettings
from algotrade.config.site.settings import load_verdict
from algotrade.services.read.evaluation import runs
from algotrade.services.read.evaluation.edges import load_edge
from algotrade.services.read.evaluation.verdict import (
    JUDGE_VERSION,
    Declared,
    EdgeFacts,
    JudgeCall,
    judge,
    judge_call,
    load_edge_verdict,
    summary_of,
)
from algotrade.services.read.evaluation.verdict.fingerprint import (
    JUDGED_CODE,
    canonical_json,
    digest_of,
    fingerprint,
    judge_digest,
    settings_hash,
)
from algotrade.services.read.evaluation.verdict.rule import counts_wins, is_chain, is_factor_neutral
from algotrade.storage.backends.memory import MemoryBackend
from tests.unit.services.read.evaluation.conftest import FROZEN, stores, write_run
from tests.unit.services.read.evaluation.verdict.test_rule import SPLIT, T, draws, result

PACKAGE = Path(fp.__file__).parent
# judge's arguments the fingerprint does not carry, each with the reason
NOT_IN_CALL = {
    "rows": "the run's rows: its id and oos_hidden (both hashed) decide them; immutable per run",
    "draws": "the run's draws: its id and oos_hidden (both hashed) decide them",
    "t": "the settings: covered by settings_hash",
    "headline": "a stored row is always the headline",
    "basis": "only a hidden copy's (never stored); load_edge_verdict never passes it",
}  # fmt: skip
# EdgeFacts fields that only the haircut reads, so the headline never sees them
NOT_HEADLINE = {
    "measured": "the haircut's series reader",
    "site_trials": "the haircut's site trial count",
}
# What the verdict package imports from outside itself and the headline never runs: the full
# verdict's pieces (outlook, evidence, decay, robustness, haircut), the loaders, and the
# constants that only feed the JudgeCall (which is hashed whole).
NOT_JUDGED = {
    "algotrade.config.edges.document:MODEL_KIND": "feeds counts_wins, so the call",
    "algotrade.config.edges.document:PAIR_KIND": "feeds counts_wins, so the call",
    "algotrade.config.edges.portfolio:PORTFOLIO_KIND": "feeds the call's portfolio flag",
    "algotrade.config.edges.portfolio:benchmark_words": "feeds the call's benchmark words",
    "algotrade.config.site.settings:load_verdict": "loads the settings, hashed whole",
    "algotrade.config.edges.portfolio:OOS_CLASSES": "settings parse: in settings_hash",
    "algotrade.config.edges.verdict:COST_LEVELS": "settings parse: in settings_hash",
    "algotrade.config.edges.verdict:DECOYS_STANDARD": "settings parse: in settings_hash",
    "algotrade.config.edges.verdict:EDGE_COSTS_KEYS": "settings parse: in settings_hash",
    "algotrade.config.edges.verdict:HAIRCUT_KEYS": "settings parse: in settings_hash",
    "algotrade.config.edges.verdict:KEYS": "settings parse: in settings_hash",
    "algotrade.config.edges.verdict:_cost_levels": "settings parse: in settings_hash",
    "algotrade.config.edges.verdict:_decoys": "settings parse: in settings_hash",
    "algotrade.config.site.fields:Table": "settings parse: in settings_hash",
    "algotrade.core.views.feature_view:FeatureValue": "a type",
    "algotrade.services.read.context:run_partition": "the storage read of the run's partition",
    "algotrade.storage.runs:RunRecord": "a type",
    "algotrade.storage.tables.interfaces:RowFilter": "a type: the storage read's filter",
    "algotrade.storage.tables.schemas:result_table": "the table's schema lookup",
    "algotrade.services.read.context:Stores": "a type",
    "algotrade.services.read.context:once_per_request": "the memo of the run's inputs",
    "algotrade.services.read.evaluation.decay:EdgeDecay": "full verdict only (decay)",
    "algotrade.services.read.evaluation.decay:decay_of": "full verdict only (decay)",
    "algotrade.services.read.evaluation.edges:Edge": "a type: its fields enter the call",
    "algotrade.services.read.evaluation.edges:EdgePublished": "a type: serialised in the call",
    "algotrade.services.read.evaluation.evidence:AtTarget": "full verdict only (outlook)",
    "algotrade.services.read.evaluation.evidence:COUNT_CRITERIA": "full verdict only (outlook)",
    "algotrade.services.read.evaluation.evidence:EvidenceProgress": "full verdict only (evidence)",
    "algotrade.services.read.evaluation.evidence:LEVEL_WORDS": "full verdict only (outlook)",
    "algotrade.services.read.evaluation.evidence:Projection": "full verdict only (outlook)",
    "algotrade.services.read.evaluation.evidence:count_of": "full verdict only (outlook)",
    "algotrade.services.read.evaluation.evidence:evidence_of": "full verdict only (evidence)",
    "algotrade.services.read.evaluation.evidence:outlook_of": "full verdict only (outlook)",
    "algotrade.services.read.evaluation.robustness:EdgeHaircut": "full verdict only",
    "algotrade.services.read.evaluation.robustness:Robustness": "full verdict only",
    "algotrade.services.read.evaluation.robustness:load_haircut": "full verdict only",
    "algotrade.services.read.evaluation.robustness:load_robustness": "full verdict only",
    "algotrade.services.read.evaluation.runs:Draws": "a type alias",
    "algotrade.services.read.evaluation.runs:EdgeRun": "a type: its fields enter the call",
    "algotrade.services.read.evaluation.runs:load_canonical_run": "the run: named by id",
    "algotrade.services.read.evaluation.runs:load_measured_sessions": "full verdict only",
    "algotrade.services.read.evaluation.runs:load_site_trials": "full verdict only",
}  # fmt: skip


def test_the_judge_call_carries_every_judge_input() -> None:
    """Adding an argument to ``judge`` without the call (so the fingerprint) fails here."""
    params = set(inspect.signature(judge).parameters)
    assert params == {f.name for f in fields(JudgeCall)} | set(NOT_IN_CALL)
    assert {f.name for f in fields(EdgeFacts)} >= set(NOT_HEADLINE)


def test_every_edge_fact_is_serialised_or_declared_not_headline() -> None:
    """A new ``EdgeFacts`` field enters the fingerprint by construction: the serialiser walks
    every field and refuses a callable, so only the declared two are cleared before it."""
    call = judge_call(_edge(), _run(), True)
    assert canonical_json(call).count('"facts"') == 1
    for name in NOT_HEADLINE:
        assert getattr(call.facts, name) is None
    with pytest.raises(TypeError):
        canonical_json(replace(call, facts=replace(call.facts, measured=lambda: None)))


def _imports(package: Path) -> set[str]:
    """Every ``module:name`` the package takes from outside itself (a name, or an attribute of
    an imported module such as ``runs.MAIN``)."""
    found: set[str] = set()
    for file in package.glob("*.py"):
        if file.name in fp.READER_MODULES:
            continue  # the stored-headline reader judges nothing
        tree = ast.parse(file.read_text())
        modules: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("algotrade"):
                if (node.module or "").startswith("algotrade.services.read.evaluation.verdict"):
                    continue
                for a in node.names:
                    full = f"{node.module}.{a.name}"
                    try:
                        is_module = inspect.ismodule(import_module(full))
                    except ImportError:
                        is_module = False
                    if is_module:
                        modules[a.asname or a.name] = full
                    else:
                        found.add(f"{node.module}:{a.name}")
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in modules
            ):
                found.add(f"{modules[node.value.id]}:{node.attr}")
    return found


def test_every_name_the_verdict_imports_is_digested_or_declared_not_judged() -> None:
    names, judged, not_judged = _imports(PACKAGE), set(JUDGED_CODE), set(NOT_JUDGED)
    left = sorted(names - judged - not_judged)
    assert not left, f"neither in JUDGED_CODE nor NOT_JUDGED: {left}"
    assert not judged & not_judged
    assert all(NOT_JUDGED.values())


def _module_names(tree: ast.Module, module: str) -> tuple[dict[str, str], dict[str, str]]:
    """``(defined, imported)`` at module level: name -> ``module:name`` for its own top-level
    definitions, and for what it imports from ``algotrade`` (a module alias maps to the module)."""
    defined: dict[str, str] = {}
    imported: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            defined[node.name] = f"{module}:{node.name}"
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Name):
                    defined[t.id] = f"{module}:{t.id}"
        elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("algotrade"):
            for a in node.names:
                imported[a.asname or a.name] = f"{node.module}:{a.name}"
    return defined, imported


def _references(entry: str) -> set[str]:
    """Every ``module:name`` (own module or ``algotrade`` import, one hop) that the definition
    ``entry`` names: the edges of the call graph the digest must cover."""
    module, name = entry.split(":")
    tree = ast.parse(inspect.getsource(import_module(module)))
    defined, imported = _module_names(tree, module)
    node = next(
        n for n in tree.body
        if getattr(n, "name", None) == name
        or any(isinstance(t, ast.Name) and t.id == name
               for t in (n.targets if isinstance(n, ast.Assign) else [getattr(n, "target", None)]))
    )  # fmt: skip
    found: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name):
            target = imported.get(n.value.id)
            if target and inspect.ismodule(_resolve(target)):
                found.add(f"{target.replace(':', '.')}:{n.attr}")
                continue
        if isinstance(n, ast.Name):
            ref = defined.get(n.id) or imported.get(n.id)
            if ref and ref != entry and not inspect.ismodule(_resolve(ref)):
                found.add(ref)
    return found


def _resolve(ref: str) -> Any:
    module, name = ref.split(":")
    return getattr(import_module(module), name, None)


def _uncovered(judged: set[str]) -> set[str]:
    """Names the judged code references that are neither judged nor declared not judged."""
    return {r for e in judged for r in _references(e)} - judged - set(NOT_JUDGED)


def test_the_judged_code_is_closed_under_the_names_it_calls() -> None:
    """Transitive: a helper reached at any depth from the judge's outside code is digested or
    declared not judged (a change to ``_finite`` must change the digest)."""
    assert not _uncovered(set(JUDGED_CODE)), sorted(_uncovered(set(JUDGED_CODE)))


def test_removing_a_depth_two_helper_from_judged_code_fails_the_closure() -> None:
    dropped = "algotrade.quant.edges.statistics:_finite"
    assert dropped in JUDGED_CODE  # reached only through percentile_of
    assert dropped in _uncovered(set(JUDGED_CODE) - {dropped})


def test_every_judged_code_entry_exists() -> None:
    assert judge_digest()  # a name that is not a top-level definition raises LookupError


def test_the_digest_changes_with_the_judge_code_and_ignores_docstrings_and_comments(
    tmp_path: Path,
) -> None:
    copy = tmp_path / "verdict"
    shutil.copytree(PACKAGE, copy, ignore=shutil.ignore_patterns("__pycache__"))
    base = digest_of(copy, JUDGED_CODE)
    assert base == judge_digest()
    level = copy / "level.py"
    text = level.read_text()
    level.write_text("# a comment\n" + text.replace('"""', '"""Reworded. ', 1))
    assert digest_of(copy, JUDGED_CODE) == base
    level.write_text(text.replace("<", "<=", 1) if "<" in text else text + "\nX = 1\n")
    assert digest_of(copy, JUDGED_CODE) != base


def test_the_fingerprint_moves_with_every_input_and_is_stable() -> None:
    call, run = judge_call(_edge(), _run(), True), _run()
    base = fingerprint(call, run, VerdictSettings())
    assert base == fingerprint(judge_call(_edge(), _run(), True), run, VerdictSettings())
    assert len(base) == 64
    changed: list[Any] = [
        fingerprint(call, replace(run, run_id="other-run"), VerdictSettings()),
        fingerprint(call, replace(run, oos_hidden=True), VerdictSettings()),
        fingerprint(call, run, replace(VerdictSettings(), min_oos_trades=41)),
        fingerprint(replace(call, decoys=not call.decoys), run, VerdictSettings()),
        fingerprint(replace(call, split=date(2020, 1, 1)), run, VerdictSettings()),
        fingerprint(replace(call, lost_inputs=("x",)), run, VerdictSettings()),
        fingerprint(replace(call, declared=Declared("x", 5)), run, VerdictSettings()),
        fingerprint(replace(call, facts=replace(call.facts, wins=True)), run, VerdictSettings()),
    ]
    assert base not in changed and len(set(changed)) == len(changed)


def test_the_fingerprint_follows_the_judge_version(monkeypatch: pytest.MonkeyPatch) -> None:
    call, run = judge_call(_edge(), _run(), True), _run()
    before = fingerprint(call, run, VerdictSettings())
    monkeypatch.setattr(fp, "JUDGE_VERSION", JUDGE_VERSION + 1)
    assert fingerprint(call, run, VerdictSettings()) != before


def test_floats_hash_by_the_python_repr_not_numpy_s() -> None:
    assert canonical_json({"x": np.float64(0.1)}) == canonical_json({"x": 0.1})


def test_the_settings_hash_covers_the_thresholds() -> None:
    assert settings_hash(VerdictSettings()) == settings_hash(VerdictSettings())
    assert settings_hash(VerdictSettings()) != settings_hash(
        replace(VerdictSettings(), works_trades=VerdictSettings().works_trades + 1)
    )


def test_the_fingerprint_is_the_same_for_every_viewer() -> None:
    """Nothing per viewer is in the call: two users' reads of a site edge fingerprint alike."""
    backend = MemoryBackend()
    write_run(backend, "official", FROZEN, 0.6)
    prints = []
    for user in ("me", "you"):
        ctx = stores(backend, user)
        edge = load_edge(ctx, "drift")
        run = runs.load_canonical_run(ctx, edge).run
        assert run is not None
        prints.append(fingerprint(judge_call(edge, run, True), run, load_verdict(ctx.configs)))
    assert prints[0] == prints[1]


def _edge() -> Any:
    backend = MemoryBackend()
    write_run(backend, "official", FROZEN, 0.6)
    return load_edge(stores(backend), "drift")


def _run() -> runs.EdgeRun:
    backend = MemoryBackend()
    write_run(backend, "official", FROZEN, 0.6)
    ctx = stores(backend)
    run = runs.load_canonical_run(ctx, load_edge(ctx, "drift")).run
    assert run is not None
    return run


def _old_assembly(ctx: Any, edge: Any, headline: bool) -> Any:
    """``load_edge_verdict`` as it was before ``judge_call`` (the inline argument list)."""
    run = runs.load_canonical_run(ctx, edge).run
    assert run is not None
    return judge(
        edge.id,
        runs.load_run_rows(ctx, run),
        run.split_from or edge.frozen_from,
        load_verdict(ctx.configs),
        run.lost_inputs,
        draws=runs.load_run_draws(ctx, run),
        decoys=bool(edge.baselines),
        declared=Declared(edge.promoted, edge.basis_horizon),
        facts=EdgeFacts(
            edge.published,
            edge.schedule,
            after=run.range_to,
            measured=None if headline else lambda: runs.load_measured_sessions(ctx, run),
            wins=counts_wins(edge),
            chain=is_chain(edge),
            portfolio=edge.settings is not None and edge.settings.kind == PORTFOLIO_KIND,
            benchmark=benchword(edge.settings.benchmark) if edge.settings is not None else "",
            neutral=is_factor_neutral(edge),
            base=edge.base,
            site_trials=None if edge.mine or headline else lambda: runs.load_site_trials(ctx),
        ),
        range_to=run.range_to,
        headline=headline,
    )


@pytest.mark.parametrize("headline", [True, False])
@pytest.mark.parametrize("user", ["me", "site"])
def test_the_judge_call_path_equals_the_old_assembly(headline: bool, user: str) -> None:
    backend = MemoryBackend()
    write_run(backend, "official", FROZEN, 0.6, owner="site", whole={"sessions": 70})
    ctx = stores(backend, user)
    edge = load_edge(ctx, "drift")
    now = load_edge_verdict(ctx, edge, headline)
    then = _old_assembly(ctx, edge, headline)
    assert now == then
    assert summary_of(now) == summary_of(then)


def test_a_missing_run_is_still_waiting() -> None:
    ctx = stores(MemoryBackend())
    edge = load_edge(ctx, "drift")
    assert load_edge_verdict(ctx, edge, True).rationale == "No official result yet"


# The headline of fixture results, by JUDGE_VERSION: (verdict, result, basis, trades, oos_trades,
# lift_pts rounded, lift). A changed output under an unchanged JUDGE_VERSION fails: bump it and
# add the new expectations (an architect reviews every change of EXPECTED).
CASES: dict[str, dict[str, Any]] = {
    "promising": {"rows": result()},
    "works": {
        "rows": result(
            oos={"decile_t": 3.0, "decile_spread": 0.9},
            whole={"sessions": 100, "deflated_sharpe": 0.95, "pbo": 0.2},
        ),
        "draws": draws(100),
    },
    "light_oos": {"rows": result(oos={"sessions": 39})},
    "no_oos_figures": {"rows": result(oos={"sessions": None, "hit_rate": None, "lift": None})},
    "lost_inputs": {"rows": result(), "lost_inputs": ("main/scr: rollup (3 sessions)",)},
    "no_decoys": {"rows": result(), "decoys": False},
    "undeclared_basis_waits": {"rows": [], "declared": Declared("scr", 99)},
    "portfolio": {"rows": result(), "facts": EdgeFacts(portfolio=True, benchmark="SPY")},
    "out_of_window": {"rows": result(), "facts": EdgeFacts(base="out_of_window", chain=True)},
}
EXPECTED: dict[int, dict[str, tuple[Any, ...]]] = {
    1: {
        "promising": (
            "promising",
            "Win rate 60% · base rate 50%",
            "scr, 20 trading days",
            70,
            60,
            10.0,
            1.2,
        ),
        "works": (
            "works",
            "Win rate 60% · base rate 50%",
            "scr, 20 trading days",
            100,
            60,
            10.0,
            1.2,
        ),
        "light_oos": (
            "not_enough_data",
            "Only 39 out-of-sample trades; 40 are needed",
            "scr, 20 trading days",
            70,
            39,
            10.0,
            1.2,
        ),
        "no_oos_figures": (
            "not_enough_data",
            "Only 0 out-of-sample trades; 40 are needed",
            "scr, 20 trading days",
            70,
            None,
            None,
            None,
        ),
        "lost_inputs": (
            "waiting_on_data",
            "The result lost inputs for scr: main/scr: rollup (3 sessions)",
            "scr, 20 trading days",
            None,
            None,
            None,
            None,
        ),
        "no_decoys": (
            "promising",
            "Win rate 60% · base rate 50%",
            "scr, 20 trading days",
            70,
            60,
            10.0,
            1.2,
        ),
        "undeclared_basis_waits": (
            "waiting_on_data",
            "The official result has no figures for the declared basis scr, 99 trading days",
            None,
            None,
            None,
            None,
            None,
        ),
        "portfolio": (
            "not_working",
            "Beat the benchmark in 60% of sessions",
            "scr, 20 trading days",
            70,
            60,
            10.0,
            1.2,
        ),
        "out_of_window": (
            "promising",
            "Win rate 60% · base rate 50%",
            "scr, 20 trading days",
            70,
            60,
            10.0,
            1.2,
        ),
    }
}


def _headline(name: str) -> tuple[Any, ...]:
    case = dict(CASES[name])
    rows = case.pop("rows")
    s = summary_of(judge("e", rows, SPLIT, T, headline=True, **case))
    return (
        s.verdict, s.result, s.basis, s.trades, s.oos_trades,
        None if s.lift_pts is None else round(s.lift_pts, 6), s.lift,
    )  # fmt: skip


def test_a_judge_change_without_a_version_bump_fails() -> None:
    assert JUDGE_VERSION in EXPECTED, "bump JUDGE_VERSION and add the new expectations"
    got = {name: _headline(name) for name in CASES}
    assert got == EXPECTED[JUDGE_VERSION], (
        "the judge's output changed under an unchanged JUDGE_VERSION: bump it and add the new "
        "expectations to EXPECTED"
    )


def test_a_hidden_and_a_revealed_copy_of_one_run_fingerprint_differently() -> None:
    """``load_run_rows`` serves in-sample rows only while ``oos_hidden``: a stored headline must
    not outlive a hide or a reveal (it would leak, or understate, the out-of-sample result)."""
    run = _run()
    call = judge_call(_edge(), run, True)
    shown = fingerprint(call, replace(run, oos_hidden=False), VerdictSettings())
    assert shown != fingerprint(call, replace(run, oos_hidden=True), VerdictSettings())


def test_no_judging_module_imports_a_reader_module() -> None:
    """``READER_MODULES`` are outside the digest: judging code must never depend on them."""
    readers = {Path(m).stem for m in fp.READER_MODULES}
    for file in PACKAGE.glob("*.py"):
        if file.name in fp.READER_MODULES or file.name == "__init__.py":
            continue
        for node in ast.walk(ast.parse(file.read_text())):
            names: list[str] = []
            if isinstance(node, ast.ImportFrom):
                names = [node.module or "", *(f"{node.module}.{a.name}" for a in node.names)]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            assert not [n for n in names if n.split(".")[-1] in readers], file.name
