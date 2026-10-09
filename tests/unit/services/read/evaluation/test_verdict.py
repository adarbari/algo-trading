"""The edge verdict rule: one test per verdict and per boundary (ED8)."""

from datetime import date

from algotrade.config.edges.verdict import VerdictSettings
from algotrade.services.read.evaluation.edges import load_edge
from algotrade.services.read.evaluation.runs import EdgeRow, _lost
from algotrade.services.read.evaluation.verdict import (
    BOTH,
    IN_SAMPLE,
    NOT_ENOUGH,
    NOT_WORKING,
    OUT_OF_SAMPLE,
    PROMISING,
    WAITING,
    WORKS,
    EdgeVerdict,
    judge,
    load_edge_verdict,
)
from algotrade.storage.backends.memory import MemoryBackend
from tests.unit.services.read.evaluation.conftest import FROZEN, stores, write_run

T = VerdictSettings()
SPLIT = date(2026, 4, 1)


def row(variant: str = "scr", role: str = "screener", kind: str = "frozen", **over: object):
    base: dict[str, object] = {
        "edge_variant": "main", "variant": variant, "role": role, "horizon_sessions": 20,
        "slice_kind": kind, "slice_value": kind, "sessions": 60, "picks": 600, "hits": 360,
        "trials": 3, "pre_snapshot_sessions": 0, "hit_rate": 0.60, "base_rate": 0.50,
        "lift": 1.2, "mean_excess_picks": 0.01, "decile_spread": 0.05, "decile_t": 2.5,
        "effect_size": 0.3, "sharpe": 1.0, "deflated_sharpe": 0.9, "pbo": 0.3,
    }  # fmt: skip
    base.update(over)
    return EdgeRow(**base)  # type: ignore[arg-type]


def result(
    oos: dict[str, object] | None = None,
    whole: dict[str, object] | None = None,
    baselines: tuple[float, ...] = (1.05, 1.1),
    insample: dict[str, object] | None = None,
) -> list[EdgeRow]:
    rows = [
        row(kind="frozen", **(oos or {})),
        row(kind="all", **{"sessions": 70, **(whole or {})}),
        row(kind="in_sample", **{"hit_rate": 0.60, "base_rate": 0.50, **(insample or {})}),
    ]
    rows += [
        row(variant=f"b{i}", role="baseline", lift=x, decile_spread=0.01 * i)
        for i, x in enumerate(baselines)
    ]
    return rows


def draws(beaten: int, of: int = 100, horizon: int = 20) -> list[EdgeRow]:
    """``of`` random-pick draws, ``beaten`` of them below the screener's own lift (1.2)."""
    return [
        row("random", "random", "draw", horizon_sessions=horizon, lift=1.0 if i < beaten else 1.5)
        for i in range(of)
    ]


def verdict(rows: list[EdgeRow] | None, **kw: object) -> EdgeVerdict:
    return judge("e", rows, SPLIT, T, **kw)  # type: ignore[arg-type]


def test_no_official_result_is_waiting() -> None:
    v = verdict(None)
    assert (v.verdict, v.rationale) == (WAITING, "No official result yet")


def test_a_run_without_out_of_sample_rows_is_waiting_and_names_lost_inputs() -> None:
    v = verdict([row(kind="all")], lost_inputs=("scr: rollup (3 sessions)",))
    assert v.verdict == WAITING
    assert "rollup (3 sessions)" in v.rationale


def test_fewer_oos_trades_than_the_minimum_is_not_enough_at_the_boundary() -> None:
    short = verdict(result(oos={"sessions": 39}))
    assert (short.verdict, short.rationale) == (
        NOT_ENOUGH,
        "Only 39 out-of-sample trades; 40 are needed",
    )
    assert verdict(result(oos={"sessions": 40})).verdict == PROMISING
    assert (
        verdict(result(whole={"sessions": 5})).verdict == PROMISING
    )  # whole history is not the gate


def test_promising_names_what_works_still_needs() -> None:
    v = verdict(result())
    assert v.verdict == PROMISING
    assert v.basis == "scr, 20 trading days"
    assert "Trades, and out-of-sample trades" in v.rationale
    assert v.lift_pts is not None and round(v.lift_pts) == 10


def test_works_needs_every_criterion_and_the_random_pick_win() -> None:
    strong = result(
        oos={"decile_t": 3.0, "decile_spread": 0.9},
        whole={"sessions": 100, "deflated_sharpe": 0.95, "pbo": 0.2},
    )
    capped = verdict(strong)
    assert capped.verdict == PROMISING and "random picks is not measured" in capped.rationale
    assert verdict(strong, draws=draws(100)).verdict == WORKS
    assert verdict(strong, draws=draws(0)).verdict == PROMISING


def test_works_needs_the_lift_above_the_beat_share_of_the_draws() -> None:
    strong = result(
        oos={"decile_t": 3.0, "decile_spread": 0.9},
        whole={"sessions": 100, "deflated_sharpe": 0.95, "pbo": 0.2},
    )
    assert verdict(strong, draws=draws(95)).verdict == WORKS  # exactly 95 of 100
    below = verdict(strong, draws=draws(94))
    assert below.verdict == PROMISING and "beats 94% of 100 random picks" in below.rationale
    # Draws of another holding period say nothing about this one.
    assert verdict(strong, draws=draws(100, horizon=5)).verdict == PROMISING


def test_works_boundaries() -> None:
    strong = {"decile_t": 3.0, "decile_spread": 0.9}
    whole = {"sessions": 100, "deflated_sharpe": 0.95, "pbo": 0.2}
    assert verdict(result(oos=strong, whole=whole), draws=draws(100)).verdict == WORKS
    short = {**whole, "sessions": 99}
    assert verdict(result(oos=strong, whole=short), draws=draws(100)).verdict == PROMISING
    thin = {**strong, "decile_t": 2.99}
    assert verdict(result(oos=thin, whole=whole), draws=draws(100)).verdict == PROMISING
    few_oos = {**strong, "sessions": 39}  # below the Promising minimum too (both are 40)
    assert verdict(result(oos=few_oos, whole=whole), draws=draws(100)).verdict == NOT_ENOUGH


def test_win_rate_not_above_base_is_not_working() -> None:
    v = verdict(result(oos={"hit_rate": 0.50, "base_rate": 0.50}))
    assert v.verdict == NOT_WORKING and "win rate" in v.rationale.lower()


def test_each_hard_failure_is_not_working_at_its_boundary() -> None:
    assert verdict(result(oos={"decile_t": 0.99})).verdict == NOT_WORKING
    assert verdict(result(whole={"pbo": 0.51})).verdict == NOT_WORKING
    assert verdict(result(whole={"pbo": 0.5})).verdict == PROMISING
    assert verdict(result(whole={"deflated_sharpe": 0.49})).verdict == NOT_WORKING
    assert verdict(result(oos={"lift": 1.0}, baselines=(1.05, 1.1, 1.2))).verdict == NOT_WORKING


def test_a_missed_promising_criterion_is_not_working_and_says_which() -> None:
    v = verdict(result(oos={"decile_t": 1.5}))
    assert v.verdict == NOT_WORKING and "Top vs bottom decile t" in v.rationale
    v = verdict(result(whole={"deflated_sharpe": 0.79}))
    assert v.verdict == NOT_WORKING and "Deflated Sharpe" in v.rationale
    v = verdict(result(oos={"lift": 1.07}, baselines=(1.0, 1.1)))  # above the median, not all
    assert v.verdict == NOT_WORKING and "baseline" in v.rationale
    v = verdict(result(oos={"hit_rate": 0.52}, insample={"hit_rate": 0.70}))
    assert v.verdict == NOT_WORKING and "keeps its size" in v.rationale
    # 5 pts out of sample against 10 in sample is exactly half: passes
    assert verdict(result(oos={"hit_rate": 0.55})).verdict == PROMISING


def test_a_criterion_not_stored_never_passes() -> None:
    v = verdict(result(whole={"deflated_sharpe": None}, oos={"deflated_sharpe": None}))
    assert v.verdict == NOT_ENOUGH and "not measured" in v.rationale
    v = verdict(result(baselines=()))
    assert v.verdict == NOT_ENOUGH and "baseline" in v.rationale


def test_the_best_candidate_is_the_verdict_and_names_its_screen() -> None:
    rows = [
        *result(),
        row(variant="other", kind="frozen", hit_rate=0.45),
        row(variant="other", kind="all"),
    ]
    v = verdict(rows)
    assert v.verdict == PROMISING and v.basis == "scr, 20 trading days"


def test_exploratory_and_variant_rows_are_ignored() -> None:
    rows = result()
    rows += [row(kind="frozen", exploratory=True, variant="x")]
    rows += [row(kind="frozen", edge_variant="v2", variant="y")]
    assert verdict(rows).basis == "scr, 20 trading days"


def test_year_rows_are_marked_by_the_split() -> None:
    rows = [*result(), *(row(kind="year", slice_value=y) for y in ("2025", "2026", "2027"))]
    periods = {y.year: y.period for y in verdict(rows).years}
    assert periods == {"2025": IN_SAMPLE, "2026": BOTH, "2027": OUT_OF_SAMPLE}


# --- the loader: an edge's verdict from the stored official result -------------------------


def test_an_edge_without_a_run_is_waiting_on_data(backend: MemoryBackend) -> None:
    ctx = stores(backend)
    edge = load_edge(ctx, "drift")
    assert edge is not None
    assert load_edge_verdict(ctx, edge).verdict == WAITING


def test_an_exploratory_only_edge_is_still_waiting(backend: MemoryBackend) -> None:
    write_run(backend, "x", date(2026, 3, 1), 0.9)
    ctx = stores(backend)
    edge = load_edge(ctx, "drift")
    assert edge is not None
    assert load_edge_verdict(ctx, edge).verdict == WAITING


def test_a_short_official_result_is_not_enough_data(backend: MemoryBackend) -> None:
    write_run(backend, "official", FROZEN, 0.6)
    ctx = stores(backend)
    edge = load_edge(ctx, "drift")
    assert edge is not None
    found = load_edge_verdict(ctx, edge)
    assert (found.verdict, found.rationale) == (
        NOT_ENOUGH,
        "Only 12 out-of-sample trades; 40 are needed",
    )
    assert found.basis == "momo, 20 trading days" and found.edge_id == "drift"


def test_the_definition_sources_and_lost_inputs_are_served(backend: MemoryBackend) -> None:
    ctx = stores(backend)
    edge = load_edge(ctx, "drift")
    assert edge is not None
    assert edge.definition.picks == "Every session · top 5 of the screen"
    assert edge.definition.trade == (
        "Enter 1 session after the decision · hold 20 trading days · win = beats SPY"
    )
    assert edge.definition.test == f"Out-of-sample from {FROZEN.isoformat()}"
    assert [(s.title, s.url) for s in edge.sources] == [("A paper", "")]
    lost = [{"variant": "main/momo", "horizon": 20, "table": "rollup", "sessions": 3}]
    assert _lost({"lost_sessions": lost}) == ("main/momo: rollup (3 sessions)",)
    assert _lost({}) == ()


def test_a_run_without_the_in_sample_slice_reports_the_ratio_not_measured() -> None:
    rows = [r for r in result() if r.slice_kind != "in_sample"]
    v = verdict(rows)
    assert v.verdict == NOT_ENOUGH and "keeps its size is not measured yet" in v.rationale


def test_lost_inputs_for_the_screen_make_the_edge_wait_even_with_rows() -> None:
    v = verdict(result(), lost_inputs=("main/scr: rollup (3 sessions)",))
    assert v.verdict == WAITING and "rollup (3 sessions)" in v.rationale
    assert v.basis == "scr, 20 trading days"
    other = verdict(result(), lost_inputs=("main/other: rollup (3 sessions)",))
    assert other.verdict == PROMISING


def test_a_zero_lift_candidate_is_ranked_above_a_missing_one() -> None:
    rows = [
        *result(),
        row(variant="blank", kind="frozen", hit_rate=None, base_rate=None),
        row(variant="blank", kind="all"),
    ]
    assert verdict(rows).basis == "scr, 20 trading days"


def test_no_declared_baselines_do_not_block_promising_and_say_so() -> None:
    v = verdict(result(baselines=()), decoys=False)
    assert v.verdict == PROMISING
    decoy = next(c for c in v.criteria if c.id == "baselines")
    assert (decoy.status, decoy.value) == ("pass", "no decoys declared")
    # a declared baseline with no stored row stays not measured
    assert verdict(result(baselines=())).verdict == NOT_ENOUGH


def test_the_page_figures_are_the_in_sample_deciles_the_trials_and_the_robustness() -> None:
    deciles = tuple(0.09 - i / 50 for i in range(10))
    rows = [
        row(kind="in_sample", decile_means=deciles) if r.slice_kind == "in_sample" else r
        for r in result()
    ]
    v = verdict(rows, draws=draws(60))
    assert v.deciles == deciles  # the in-sample row's, never the out-of-sample one
    assert v.trials == 3
    assert v.robustness is not None and v.robustness.beats == 0.6 and v.robustness.draws == 100
    assert v.robustness.summary == "Beats 60% of 100 random backtests after 3 variants tried."
    bare = verdict(result())
    assert bare.deciles == () and bare.robustness is None  # not stored: not zeros, no chart
