"""A user's copy against the edge it extends (ADR 0053 amendment 2026-10-09): its out-of-sample
result is withheld SERVER SIDE until the user shows it, its verdict is then judged on in-sample
figures with the reason saying so, and the comparison and the published document are the
server's."""

import tomllib
from datetime import UTC, date, datetime
from typing import Any

import pytest

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.read.context import StoreContext, open_stores
from algotrade.services.read.evaluation import runs, versions
from algotrade.services.read.evaluation.edges import Edge, load_edge, load_edges
from algotrade.services.read.evaluation.verdict import NOT_ENOUGH, NOT_WORKING, WAITING
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.result_writer import ResultWriter
from tests.helpers.stored_frames import stamped
from tests.unit.services.read.evaluation.conftest import DOCS, END, FROZEN, START, row, write_run

MOVED = date(2026, 7, 1)
HERE = datetime(2026, 10, 3, 3, tzinfo=UTC)


def with_copy(
    follow: dict[str, Any] | None = None, **changes: Any
) -> dict[tuple[str, str, str], Any]:
    document: dict[str, Any] = {"extends": "drift", "screeners": ["momo"], **changes}
    if follow is not None:
        document["follow"] = follow
    return {**DOCS, ("me", "edges", "mine"): document}


def ctx_for(backend: MemoryBackend, docs: dict[tuple[str, str, str], Any]) -> StoreContext:
    return open_stores(StoreReader(backend), MemoryConfigStore(docs), UserContext("me"))


def write_own_run(backend: MemoryBackend, run_id: str = "mine1", split: date = MOVED) -> None:
    """The user's run of ``mine``: in-sample, whole-history, year, split rows of one screen and
    one baseline (the figures differ by slice so a leak shows)."""
    kind = "split"
    rows = [
        row("momo", "all", 0.55, split, edge_id="mine", user_id="me", exploratory=True),
        row(
            "momo",
            "year",
            0.58,
            split,
            edge_id="mine",
            user_id="me",
            exploratory=True,
            slice_value="2026",
        ),
        row(
            "momo",
            "in_sample",
            0.45,
            split,
            edge_id="mine",
            user_id="me",
            exploratory=True,
            sessions=20,
            hits=9,
        ),
        row("momo", kind, 0.80, split, edge_id="mine", user_id="me", exploratory=True, sessions=50),
        row(
            "decoy",
            "in_sample",
            0.40,
            split,
            role="baseline",
            edge_id="mine",
            user_id="me",
            exploratory=True,
        ),
        row(
            "decoy",
            kind,
            0.41,
            split,
            role="baseline",
            edge_id="mine",
            user_id="me",
            exploratory=True,
        ),
    ]
    frame = stamped(rows, END, run_id, HERE, "edge-eval")
    stats = {
        "edge": "mine", "split_from": split.isoformat(), "exploratory": True,
        "range": [START.isoformat(), END.isoformat()], "as_of": "2026-10-01T00:00:00+00:00",
        "trials_counted": 1,
    }  # fmt: skip
    writer = ResultWriter(backend)
    with writer.publishing(run_id, HERE):
        writer.write_result("edge_eval", END, run_id, frame, pending=True)
        record = RunRecord(run_id, "edge-eval:mine:me", END, HERE)
        writer.save_run(record.finish(HERE, complete=True, stats=stats))


def mine(ctx: StoreContext) -> Edge:
    found = load_edge(ctx, "mine")
    assert found is not None
    return found


def test_an_edge_reads_its_state_and_whether_it_is_the_users_own() -> None:
    follow = {"state": "following", "since": "2026-09-01", "labels": ["followed_against_verdict"]}
    ctx = ctx_for(MemoryBackend(), with_copy(follow))
    edges = {e.id: e for e in load_edges(ctx)}
    assert (edges["drift"].mine, edges["drift"].state, edges["drift"].extends) == (
        False,
        "researching",
        None,
    )
    copy = edges["mine"]
    assert (copy.mine, copy.state, copy.extends) == (True, "following", "drift")
    assert copy.since == date(2026, 9, 1)
    assert copy.labels == ("followed_against_verdict",)
    assert not copy.oos_revealed and copy.oos_hidden


def test_a_hidden_runs_rows_are_the_in_sample_slice_only() -> None:
    backend = MemoryBackend()
    write_own_run(backend)
    ctx = ctx_for(backend, with_copy())
    (run,) = runs.load_edge_runs(ctx, mine(ctx))
    assert run.oos_hidden
    shown = runs.load_run_rows(ctx, run)
    assert {r.slice_kind for r in shown} == {"in_sample"}  # no frozen / split / all / year rows
    assert all(r.hit_rate != 0.80 for r in shown)  # the withheld figure is nowhere
    revealed_ctx = ctx_for(backend, with_copy({"state": "researching", "oos_revealed": True}))
    (shown_run,) = runs.load_edge_runs(revealed_ctx, mine(revealed_ctx))
    assert not shown_run.oos_hidden
    assert {"split", "all", "year"} <= {
        r.slice_kind for r in runs.load_run_rows(revealed_ctx, shown_run)
    }


def test_a_site_edges_rows_are_never_hidden() -> None:
    backend = MemoryBackend()
    write_run(backend, "site1", FROZEN, 0.7)
    ctx = ctx_for(backend, with_copy())
    (run,) = runs.load_edge_runs(ctx, load_edge(ctx, "drift"))  # type: ignore[arg-type]
    assert not run.oos_hidden
    assert {r.slice_kind for r in runs.load_run_rows(ctx, run)} == {"all", "frozen"}


def test_a_hidden_copy_is_judged_on_in_sample_and_says_so_and_never_beyond_not_enough() -> None:
    backend = MemoryBackend()
    write_own_run(backend)
    ctx = ctx_for(backend, with_copy())
    found = versions.load_verdict(ctx, mine(ctx))
    assert found.verdict in (NOT_ENOUGH, NOT_WORKING)  # Promising / Works need the fair test
    assert found.headline.startswith(versions.HIDDEN_WORDS)
    assert "Out-of-sample" not in found.headline and "0.80" not in found.headline
    assert found.win_rate == 0.45 and found.base_rate == 0.4  # the in-sample figures
    assert all("Out-of-sample" not in c.label for c in found.criteria)


def test_a_revealed_copy_is_judged_on_its_out_of_sample_figures() -> None:
    backend = MemoryBackend()
    write_own_run(backend)
    ctx = ctx_for(backend, with_copy({"state": "researching", "oos_revealed": True}))
    found = versions.load_verdict(ctx, mine(ctx))
    assert found.win_rate == 0.80  # the split slice stands for the frozen one
    assert not found.headline.startswith(versions.HIDDEN_WORDS)


def test_a_copy_with_no_run_is_waiting_and_a_site_edge_keeps_its_official_verdict() -> None:
    backend = MemoryBackend()
    write_run(backend, "site1", FROZEN, 0.7)
    ctx = ctx_for(backend, with_copy())
    assert versions.load_verdict(ctx, mine(ctx)).verdict == WAITING
    site = load_edge(ctx, "drift")
    assert site is not None and versions.load_verdict(ctx, site).win_rate == 0.7


def test_the_comparison_is_in_sample_only_while_the_result_is_hidden() -> None:
    backend = MemoryBackend()
    write_run(backend, "site1", FROZEN, 0.7)
    write_own_run(backend)
    ctx = ctx_for(backend, with_copy())
    compare = versions.load_compare(ctx, mine(ctx))
    assert compare is not None and compare.oos_hidden and compare.extends == "drift"
    by_kind = {r.kind: r for r in compare.rows}
    assert set(by_kind) == {"this", "extended", "baseline"}
    assert by_kind["this"].out_of_sample is None and by_kind["this"].oos_hidden
    assert by_kind["this"].in_sample.win_rate == 0.45
    assert by_kind["baseline"].out_of_sample is None and by_kind["baseline"].label == "decoy"
    assert by_kind["extended"].out_of_sample.win_rate == 0.7  # the site's result is public
    assert 0.8 not in {
        f.win_rate for r in compare.rows for f in (r.in_sample, r.out_of_sample) if f
    }


def test_the_comparison_shows_out_of_sample_once_revealed() -> None:
    backend = MemoryBackend()
    write_own_run(backend)
    ctx = ctx_for(backend, with_copy({"state": "following", "oos_revealed": True}))
    compare = versions.load_compare(ctx, mine(ctx))
    assert compare is not None and not compare.oos_hidden
    this = next(r for r in compare.rows if r.kind == "this")
    assert this.out_of_sample.win_rate == 0.80 and this.out_of_sample.trades == 50
    assert this.in_sample.win_rate == 0.45


def test_the_comparison_says_why_it_is_empty_and_is_none_for_a_site_edge() -> None:
    ctx = ctx_for(MemoryBackend(), with_copy())
    compare = versions.load_compare(ctx, mine(ctx))
    assert compare is not None and compare.rows == () and "not run" in compare.reason
    site = load_edge(ctx, "drift")
    assert site is not None and versions.load_compare(ctx, site) is None


def test_the_published_document_is_one_whole_toml_without_the_users_state() -> None:
    ctx = ctx_for(MemoryBackend(), with_copy({"state": "following"}, top_k=3))
    published = tomllib.loads(versions.load_published_document(ctx, "mine"))
    assert published["id"] == "mine" and published["top_k"] == 3
    assert published["thesis"] == "Dear names keep rising."  # inherited, resolved
    assert not {"follow", "extends"} & set(published)


@pytest.mark.parametrize("hidden", [True, False])
def test_the_oos_hidden_flag_follows_the_users_reveal(hidden: bool) -> None:
    follow = None if hidden else {"state": "researching", "oos_revealed": True}
    ctx = ctx_for(MemoryBackend(), with_copy(follow))
    assert mine(ctx).oos_hidden is hidden
