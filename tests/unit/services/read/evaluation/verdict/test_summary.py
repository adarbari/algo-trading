"""The headline of an edge's verdict (``EdgeSummary``): the list's fields, always the full
verdict's own (the contract), read without the haircut, decay, robustness, years or outlook."""

from datetime import date
from typing import Any

import pytest

from algotrade.services.read.evaluation import runs as runs_module
from algotrade.services.read.evaluation import versions
from algotrade.services.read.evaluation.edges import load_edges
from algotrade.services.read.evaluation.verdict import (
    DIAGNOSTIC,
    NOT_ENOUGH,
    NOT_WORKING,
    PROMISING,
    WAITING,
    WORKS,
    EdgeSummary,
    judge,
    load_edge_summary,
    summary_of,
)
from algotrade.services.read.evaluation.verdict import rule as rule_module
from algotrade.storage.backends.memory import MemoryBackend
from tests.unit.services.read.evaluation.conftest import DOCS, EDGE, FROZEN, stores, write_run
from tests.unit.services.read.evaluation.test_versions import (
    ctx_for,
    mine,
    with_copy,
    write_own_run,
)
from tests.unit.services.read.evaluation.verdict.test_rule import SPLIT, T, draws, result, row

STRONG = result(
    oos={"decile_t": 3.0, "decile_spread": 0.9},
    whole={"sessions": 100, "deflated_sharpe": 0.95, "pbo": 0.2},
)
LONG_SHORT = [row(kind="frozen", side="long_short"), row(kind="all")]


def _same(full: Any, headline: EdgeSummary) -> None:
    assert headline == summary_of(full)
    assert (headline.verdict, headline.result, headline.trades, headline.lift) == (
        full.verdict,
        full.result,
        full.trades,
        full.lift,
    )


@pytest.mark.parametrize(
    ("rows", "drawn", "level"),
    [
        (None, (), WAITING),
        (result(oos={"sessions": 12}), (), NOT_ENOUGH),
        (result(), (), PROMISING),
        (STRONG, draws(100), WORKS),
        (result(oos={"hit_rate": 0.40, "lift": 0.8}), draws(0), NOT_WORKING),
        ([row(kind="all")], (), WAITING),
    ],
)
def test_the_headline_judge_gives_the_full_judges_label_result_and_figures(
    rows: Any, drawn: Any, level: str
) -> None:
    full = judge("e", rows, SPLIT, T, draws=drawn)
    cut = judge("e", rows, SPLIT, T, draws=drawn, headline=True)
    assert full.verdict == level
    _same(full, summary_of(cut))
    assert (cut.verdict, cut.result, cut.rationale, cut.basis, cut.trades, cut.lift) == (
        full.verdict, full.result, full.rationale, full.basis, full.trades, full.lift,
    )  # fmt: skip
    assert cut.criteria == full.criteria  # the label's inputs are untouched
    assert (cut.haircut, cut.decay, cut.robustness, cut.evidence) == (None, None, None, None)
    assert (cut.years, cut.columns) == ((), ())


def test_a_diagnostic_long_short_edge_is_a_diagnostic_headline() -> None:
    full = judge("e", LONG_SHORT, SPLIT, T)
    assert full.verdict == DIAGNOSTIC
    _same(full, summary_of(judge("e", LONG_SHORT, SPLIT, T, headline=True)))


def test_the_haircut_is_never_an_input_of_the_label() -> None:
    """``_haircut`` is a piece of the returned verdict: a judge told the site's trials and the
    measured sessions gives the same level and reason as one told neither."""
    facts = rule_module.EdgeFacts(site_trials=lambda: 10_000, measured=lambda: {("scr", 20): 1})
    for rows, drawn in ((STRONG, draws(100)), (result(), ())):
        bare = judge("e", rows, SPLIT, T, draws=drawn)
        told = judge("e", rows, SPLIT, T, draws=drawn, facts=facts)
        assert (told.verdict, told.rationale, told.result) == (
            bare.verdict, bare.rationale, bare.result,
        )  # fmt: skip
        assert told.haircut != bare.haircut or bare.haircut is None


# --- the contract: summary == verdict for every kind of edge ------------------------------


SITE_DOCS = {
    **DOCS,
    ("site", "edges", "promo"): {
        **EDGE, "id": "promo", "name": "Promo", "implementation": {"promoted": "momo"},
    },
    ("site", "edges", "idle"): {**EDGE, "id": "idle", "name": "Idle"},
    ("site", "edges", "early"): {**EDGE, "id": "early", "name": "Early"},
}  # fmt: skip


def test_summary_equals_verdict_for_every_site_edge() -> None:
    """Not enough data (a short official run, plain and promoted), Waiting on data (no run; a
    run at another split only) and the frozen drift edge."""
    backend = MemoryBackend()
    write_run(backend, "official", FROZEN, 0.6)
    write_run(backend, "p1", FROZEN, 0.7, edge="promo")
    write_run(backend, "e1", date(2026, 3, 1), 0.9, edge="early")
    ctx = stores(backend, docs=SITE_DOCS)
    edges = load_edges(ctx)
    assert {e.id for e in edges} == {"drift", "promo", "idle", "early"}
    assert any(e.promoted for e in edges)
    levels = set()
    for e in edges:
        full = versions.load_verdict(ctx, e)
        _same(full, versions.load_summary(ctx, e))
        levels.add(full.verdict)
    assert levels == {WAITING, NOT_ENOUGH}


def test_summary_equals_verdict_for_a_hidden_copy_a_revealed_one_and_a_copy_with_no_run() -> None:
    for audit in (None, {"oos_revealed": True}):
        backend = MemoryBackend()
        write_own_run(backend)
        ctx = ctx_for(backend, with_copy(audit))
        edge = mine(ctx)
        full = versions.load_verdict(ctx, edge)
        _same(full, versions.load_summary(ctx, edge))
        assert edge.oos_hidden is (audit is None)
    empty = ctx_for(MemoryBackend(), with_copy())
    full = versions.load_verdict(empty, mine(empty))
    assert full.verdict == WAITING
    _same(full, versions.load_summary(empty, mine(empty)))


def test_a_hidden_copys_summary_says_in_sample_and_never_leaks_the_withheld_figure() -> None:
    backend = MemoryBackend()
    write_own_run(backend)
    ctx = ctx_for(backend, with_copy())
    found = versions.load_summary(ctx, mine(ctx))
    assert "Out-of-sample" not in found.result and "0.80" not in found.result


# --- the cost: what the headline does not read --------------------------------------------

N = 6
IDS = [f"e{i}" for i in range(N)]


def _docs() -> dict[tuple[str, str, str], dict[str, Any]]:
    return {**DOCS, **{("site", "edges", i): {**EDGE, "id": i, "name": i.upper()} for i in IDS}}


def _fill(backend: MemoryBackend) -> None:
    for k, edge in enumerate(["drift", *IDS]):
        write_run(backend, f"a{k}", FROZEN, 0.6, minutes=k, edge=edge, trials_counted=3 + k)


def test_a_page_of_summaries_reads_no_haircut_decay_or_robustness_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = MemoryBackend()
    _fill(backend)
    ctx = stores(backend, docs=_docs())
    boom = pytest.fail

    def refuse(name: str) -> Any:
        return lambda *a, **k: boom(f"the headline called {name}")

    monkeypatch.setattr(runs_module, "_site_trials", refuse("_site_trials"))
    monkeypatch.setattr(runs_module, "load_site_trials", refuse("load_site_trials"))
    monkeypatch.setattr(runs_module, "load_measured_sessions", refuse("load_measured_sessions"))
    monkeypatch.setattr(runs_module, "load_run_series", refuse("load_run_series"))
    monkeypatch.setattr(rule_module, "decay_of", refuse("decay_of"))
    monkeypatch.setattr(rule_module, "load_robustness", refuse("load_robustness"))
    monkeypatch.setattr(rule_module, "load_haircut", refuse("load_haircut"), raising=False)
    found = [load_edge_summary(ctx, e) for e in load_edges(ctx)]
    assert len(found) == N + 1 and {s.verdict for s in found} == {NOT_ENOUGH}


def test_summaries_share_one_read_of_each_runs_rows_and_draws(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = MemoryBackend()
    _fill(backend)
    ctx = stores(backend, docs=_docs())
    rows_of: list[str] = []
    draws_of: list[str] = []
    real_rows, real_draws = runs_module.load_run_rows, runs_module.load_run_draws

    def rows_spy(c: Any, run: Any, *a: Any) -> Any:
        rows_of.append(run.run_id)
        return real_rows(c, run, *a)

    def draws_spy(c: Any, run: Any) -> Any:
        draws_of.append(run.run_id)
        return real_draws(c, run)

    monkeypatch.setattr(runs_module, "load_run_rows", rows_spy)
    monkeypatch.setattr(runs_module, "load_run_draws", draws_spy)
    edges = load_edges(ctx)
    for _ in range(3):  # three resolvers ask per edge
        for e in edges:
            load_edge_summary(ctx, e)
    assert sorted(rows_of) == sorted(set(rows_of)) and len(rows_of) == N + 1
    assert sorted(draws_of) == sorted(set(draws_of)) and len(draws_of) == N + 1
