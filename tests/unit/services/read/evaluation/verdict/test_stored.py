"""The stored verdict headline, read (ADR 0053 amendment 2026-10-22): a site edge's canonical run
reads its row only when the fingerprint of the parsed documents equals the row's, and answers
exactly what the live judge answers; every other case is a live judgement, never Waiting on data
and never a blank. Own edges and hidden copies never read a site row."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from typing import Any

import pandas as pd
import pytest

from algotrade.config.site.settings import load_verdict
from algotrade.services.evaluation.cross_section.detail.verdict import edge_verdict_frame
from algotrade.services.read.context import StoreContext, run_day_rows
from algotrade.services.read.evaluation import edges, runs, versions
from algotrade.services.read.evaluation.verdict import (
    NOT_ENOUGH,
    NOT_WORKING,
    PROMISING,
    WAITING,
    WORKS,
    EdgeSummary,
    fingerprint,
    judge_call,
    load_edge_summary,
    load_stored_summary,
    summary_of,
)
from algotrade.services.read.evaluation.verdict import stored as stored_module
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.result_writer import ResultWriter
from tests.unit.services.read.evaluation.conftest import (
    DOCS,
    END,
    FROZEN,
    T,
    row,
    stores,
    write_run,
)
from tests.unit.services.read.evaluation.test_versions import (
    ctx_for,
    mine,
    with_copy,
    write_own_run,
)

TABLE = "results/edge_verdict"
WRITTEN = datetime(2026, 10, 3, tzinfo=T.tzinfo)


STATS: dict[str, Any] = {
    "edge_variant": "main", "sessions": 60, "picks": 600, "hits": 360, "trials": 3,
    "pre_snapshot_sessions": 0, "base_rate": 0.50, "lift": 1.2,
    "mean_excess_picks": 0.01, "decile_spread": 0.05, "decile_t": 2.5, "effect_size": 0.3,
    "sharpe": 1.0, "deflated_sharpe": 0.9, "pbo": 0.3, "picks_t": 3.0,
}  # fmt: skip


def draw_rows(beaten: int, of: int = 100) -> list[dict[str, Any]]:
    return [
        row("random:momo", "draw", 0.4, FROZEN, role="random", slice_value=str(i),
            **{**STATS, "lift": 1.0 if i < beaten else 1.5})
        for i in range(of)
    ]  # fmt: skip


def in_sample() -> dict[str, Any]:
    return row("momo", "in_sample", 0.6, FROZEN, **STATS)


def scenario(
    hit_rate: float = 0.60,
    oos: dict[str, Any] | None = None,
    whole: dict[str, Any] | None = None,
    more: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """``write_run``'s arguments for a run whose frozen row has ``STATS`` changed by ``oos``."""
    return {
        "hit_rate": hit_rate,
        "whole": {**STATS, "sessions": 70, **(whole or {})},
        "oos": {**STATS, **(oos or {})},
        "extra": [in_sample(), *(more or [])],
    }


# One site run per verdict level and per null shape: kwargs of ``write_run``.
SCENARIOS: dict[str, tuple[str, dict[str, Any]]] = {
    "promising": (PROMISING, scenario()),
    "not working": (NOT_WORKING, scenario(0.40, {"lift": 0.8})),
    "not enough": (NOT_ENOUGH, scenario(oos={"sessions": 12})),
    "works": (WORKS, scenario(oos={"decile_t": 3.0, "decile_spread": 0.9},
                              whole={"sessions": 100, "deflated_sharpe": 0.95, "pbo": 0.2},
                              more=draw_rows(100))),
    "null figures": (NOT_ENOUGH, scenario(oos={"sessions": None, "lift": None})),
}  # fmt: skip


def site_edge(ctx: StoreContext) -> edges.Edge:
    found = edges.load_edge(ctx, "drift")
    assert found is not None
    return found


def publish_row(backend: MemoryBackend, run_id: str = "official") -> None:
    """The row the edge-eval publish frames for ``run_id`` (the writer's own judge, from the run's
    rows), committed as its own run would."""
    ctx = stores(backend, "site")
    record = ctx.reader.run(run_id)
    frame = ctx.reader.read_run("results/edge_eval", END, run_id)
    assert record is not None and frame is not None
    framed = edge_verdict_frame(ctx, "drift", record, frame, WRITTEN)
    assert framed is not None
    writer = ResultWriter(backend)
    with writer.publishing(f"verdicts-{run_id}", WRITTEN):
        writer.write_result("edge_verdict", END, f"verdicts-{run_id}", framed, pending=True)


def stored_for(backend: MemoryBackend, docs: Any = None, user: str = "me") -> Any:
    ctx = stores(backend, user, docs)
    return load_stored_summary(ctx, site_edge(ctx)), load_edge_summary(ctx, site_edge(ctx))


def never_judge(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_: object, **__: object) -> None:
        raise AssertionError("a stored headline must not read the run's rows")

    monkeypatch.setattr(runs, "load_run_rows", refuse)
    monkeypatch.setattr(runs, "load_run_draws", refuse)


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_the_stored_headline_equals_the_live_judgement_field_by_field(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    level, kwargs = SCENARIOS[name]
    backend = MemoryBackend()
    write_run(backend, "official", FROZEN, **kwargs)
    ctx = stores(backend)
    live = load_edge_summary(ctx, site_edge(ctx))
    assert live.verdict == level
    publish_row(backend)
    never_judge(monkeypatch)  # the stored path answers without a read of the run's rows
    stored = load_stored_summary(ctx, site_edge(ctx))
    assert stored == live
    assert versions.load_summary(ctx, site_edge(ctx)) == live
    for field in (
        "trades",
        "oos_trades",
        "lift",
        "lift_pts",
        "basis",
        "basis_screener",
        "basis_horizon",
    ):
        assert getattr(stored, field) == getattr(live, field)  # None stays None, never 0 or NaN
    if live.basis is not None:  # the words and the two keys name the one basis (ADR 0083 d2)
        assert live.basis == f"{live.basis_screener}, {live.basis_horizon} trading days"
    else:
        assert live.basis_screener is None and live.basis_horizon is None
    if name == "null figures":
        assert stored is not None and stored.oos_trades is None and stored.lift is None


def test_a_stored_headline_is_not_judged_again_by_the_list(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = MemoryBackend()
    write_run(backend, "official", FROZEN, **scenario())
    publish_row(backend)
    ctx = stores(backend)
    edge = site_edge(ctx)
    never_judge(monkeypatch)
    assert versions.load_summary(ctx, edge).verdict == PROMISING


def test_no_row_judges_live_and_is_never_waiting_on_data() -> None:
    backend = MemoryBackend()
    write_run(backend, "official", FROZEN, **scenario())
    stored, live = stored_for(backend)
    assert stored is None and live.verdict == PROMISING
    ctx = stores(backend)
    assert versions.load_summary(ctx, site_edge(ctx)) == live


def test_an_edge_with_no_run_answers_live_waiting() -> None:
    ctx = stores(MemoryBackend())
    edge = site_edge(ctx)
    assert load_stored_summary(ctx, edge) is None
    assert versions.load_summary(ctx, edge).verdict == WAITING  # the live judge's own answer


def changed(**edits: Any) -> dict[tuple[str, str, str], dict[str, Any]]:
    docs = deepcopy(DOCS)
    docs[("site", "edges", "drift")].update(edits)
    return docs


@pytest.mark.parametrize(
    "docs",
    [
        changed(baselines=["momo"]),
        changed(implementation={"promoted": "momo"}),
        {**DOCS, ("site", "settings", "verdict"): {"min_oos_trades": 3}},
        {**DOCS, ("site", "settings", "verdict"): {"promising_t": 9.0}},
    ],
    ids=["decoys", "declared basis", "min_oos_trades", "promising_t"],
)
def test_a_changed_document_or_setting_judges_live_and_gives_the_live_answer(docs: Any) -> None:
    backend = MemoryBackend()
    write_run(backend, "official", FROZEN, **scenario())
    publish_row(backend)
    assert stored_for(backend)[0] is not None  # the row matches the unchanged documents
    ctx = stores(backend, docs=docs)
    edge = site_edge(ctx)
    assert load_stored_summary(ctx, edge) is None  # the row's fingerprint no longer matches
    assert versions.load_summary(ctx, edge) == load_edge_summary(ctx, edge)


def test_a_changed_judge_version_or_judge_code_judges_live(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = MemoryBackend()
    write_run(backend, "official", FROZEN, **scenario())
    publish_row(backend)
    assert stored_for(backend)[0] is not None
    monkeypatch.setattr(fingerprint, "JUDGE_VERSION", fingerprint.JUDGE_VERSION + 1)
    assert stored_for(backend)[0] is None
    monkeypatch.undo()
    monkeypatch.setattr(fingerprint, "judge_digest", lambda: "another judge")
    assert stored_for(backend)[0] is None


def test_the_hidden_out_of_sample_flip_never_reads_the_row() -> None:
    backend = MemoryBackend()
    write_run(backend, "official", FROZEN, **scenario())
    publish_row(backend)
    ctx = stores(backend)
    edge = site_edge(ctx)
    run = runs.load_canonical_run(ctx, edge).run
    assert run is not None
    # the fingerprint carries oos_hidden: a run served in-sample only differs from the stored one
    call = judge_call(edge, run, True)
    settings = load_verdict(ctx.configs)
    assert fingerprint.fingerprint(call, run, settings) != fingerprint.fingerprint(
        call, replace(run, oos_hidden=True), settings
    )


def test_a_newer_canonical_run_without_a_row_judges_live_and_never_serves_the_old_row() -> None:
    backend = MemoryBackend()
    write_run(backend, "old", FROZEN, **scenario())
    publish_row(backend, "old")
    write_run(backend, "new", FROZEN, minutes=30, **scenario(0.40, {"lift": 0.8}))
    stored, live = stored_for(backend)
    assert stored is None  # the old row belongs to a run that is no longer canonical
    assert live.verdict == NOT_WORKING and live.verdict != PROMISING


def test_a_row_of_another_edge_or_user_is_never_returned() -> None:
    backend = MemoryBackend()
    write_run(backend, "official", FROZEN, **scenario())
    publish_row(backend)
    ctx = stores(backend)
    edge = site_edge(ctx)
    present = ctx.reader.table(TABLE, END)
    assert present is not None
    for column, value in (("edge_id", "other"), ("user_id", "me")):
        planted = present.copy()
        planted[column] = value
        planted["verdict"] = "works"  # would show if the lookup ever matched it
        planted["fingerprint"] = "x"
        writer = ResultWriter(backend)
        with writer.publishing(f"plant-{column}", WRITTEN):
            writer.write_result("edge_verdict", END, f"plant-{column}", planted, pending=True)
    after = stores(backend)
    keys = run_day_rows(after, TABLE, END, stored_module.KEY)
    assert {k[:2] for k in keys} == {("drift", "site"), ("other", "site"), ("drift", "me")}
    got = load_stored_summary(after, edge)
    assert got is not None and got.verdict == PROMISING  # only its own key matches


def test_a_copy_and_a_users_own_edge_never_read_a_site_row(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = MemoryBackend()
    write_own_run(backend)
    write_run(backend, "official", FROZEN, **scenario())
    publish_row(backend)
    ctx = ctx_for(backend, with_copy())
    own = mine(ctx)
    assert own.mine

    def table_read(*_: object, **__: object) -> None:
        raise AssertionError("an own edge must not read the site's verdict table")

    monkeypatch.setattr(stored_module, "run_day_rows", table_read)
    assert load_stored_summary(ctx, own) is None  # it returns before any read
    assert versions.load_summary(ctx, own) == summary_of(versions.load_verdict(ctx, own, True))


def test_a_corrupted_row_judges_live(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = MemoryBackend()
    write_run(backend, "official", FROZEN, **scenario())
    publish_row(backend)
    ctx = stores(backend)
    edge = site_edge(ctx)
    real = run_day_rows

    def broken_level(*args: Any, **kwargs: Any) -> Any:
        rows = real(*args, **kwargs)
        return {k: {**v, "verdict": None} for k, v in rows.items()}

    monkeypatch.setattr(stored_module, "run_day_rows", broken_level)
    assert load_stored_summary(ctx, edge) is None
    assert versions.load_summary(ctx, edge) == load_edge_summary(ctx, edge)

    def unreadable(*_: Any, **__: Any) -> Any:
        raise OSError("the partition cannot be read")

    monkeypatch.setattr(stored_module, "run_day_rows", unreadable)
    assert load_stored_summary(ctx, edge) is None
    assert versions.load_summary(ctx, edge).verdict == PROMISING  # live, not blank


def test_a_row_missing_a_column_judges_live(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = MemoryBackend()
    write_run(backend, "official", FROZEN, **scenario())
    publish_row(backend)
    ctx = stores(backend)
    real = run_day_rows

    def without_result(*args: Any, **kwargs: Any) -> Any:
        return {
            k: {c: v for c, v in r.items() if c != "result"}
            for k, r in real(*args, **kwargs).items()
        }

    monkeypatch.setattr(stored_module, "run_day_rows", without_result)
    assert load_stored_summary(ctx, site_edge(ctx)) is None


def test_the_rows_of_a_day_are_read_once_per_request(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = MemoryBackend()
    write_run(backend, "official", FROZEN, **scenario())
    publish_row(backend)
    ctx = stores(backend)
    calls: list[object] = []
    real = ctx.reader.table

    def counting(*args: Any, **kwargs: Any) -> pd.DataFrame | None:
        calls.append(args[0])
        return real(*args, **kwargs)

    monkeypatch.setattr(type(ctx.reader), "table", lambda self, *a, **k: counting(*a, **k))
    for _ in range(3):
        assert load_stored_summary(ctx, site_edge(ctx)) is not None
    assert calls.count(TABLE) == 1


def test_a_viewer_sees_the_same_stored_headline_as_any_other() -> None:
    backend = MemoryBackend()
    write_run(backend, "official", FROZEN, **scenario())
    publish_row(backend)
    a, _ = stored_for(backend, user="me")
    b, _ = stored_for(backend, user="you")
    assert a is not None and a == b
    assert isinstance(a, EdgeSummary)


def test_a_failing_digest_or_hash_judges_live(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = MemoryBackend()
    write_run(backend, "official", FROZEN, **scenario())
    publish_row(backend)
    ctx = stores(backend)
    edge = site_edge(ctx)
    live = load_edge_summary(ctx, edge)

    def broken() -> str:
        raise OSError("source not available")

    monkeypatch.setattr(fingerprint, "judge_digest", broken)
    assert load_stored_summary(ctx, edge) is None
    monkeypatch.setattr(fingerprint, "canonical_json", lambda _: (_ for _ in ()).throw(TypeError()))
    assert load_stored_summary(ctx, edge) is None
    assert live.verdict == PROMISING


def test_the_memo_of_a_day_is_per_key_columns() -> None:
    backend = MemoryBackend()
    write_run(backend, "official", FROZEN, **scenario())
    publish_row(backend)
    ctx = stores(backend)
    by_four = run_day_rows(ctx, TABLE, END, stored_module.KEY)
    by_edge = run_day_rows(ctx, TABLE, END, ("edge_id",))
    assert {len(k) for k in by_four} == {4} and {len(k) for k in by_edge} == {1}
