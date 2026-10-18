"""The edge verdict rule: one test per verdict and per boundary (ED8)."""

import dataclasses
from dataclasses import fields, replace
from datetime import date, timedelta

from algotrade.config.edges.verdict import VerdictSettings
from algotrade.services.read.evaluation.edges import load_edge
from algotrade.services.read.evaluation.runs import EdgeRow, _lost
from algotrade.services.read.evaluation.verdict import (
    ALL,
    BOTH,
    DIAGNOSTIC,
    IN_SAMPLE,
    NOT_ENOUGH,
    NOT_WORKING,
    OUT_OF_SAMPLE,
    PROMISING,
    WAITING,
    WORKS,
    BasisChoice,
    Declared,
    EdgeFacts,
    EdgeVerdict,
    choose_basis,
    judge,
    load_edge_verdict,
)
from algotrade.storage.backends.memory import MemoryBackend
from tests.unit.services.read.evaluation.conftest import (
    FROZEN,
    series_row,
    stores,
    write_run,
)

T = VerdictSettings()
SPLIT = date(2026, 4, 1)


def row(variant: str = "scr", role: str = "screener", kind: str = "frozen", **over: object):
    base: dict[str, object] = {
        "edge_variant": "main", "variant": variant, "role": role, "horizon_sessions": 20,
        "slice_kind": kind, "slice_value": kind, "sessions": 60, "picks": 600, "hits": 360,
        "trials": 3, "pre_snapshot_sessions": 0, "hit_rate": 0.60, "base_rate": 0.50,
        "lift": 1.2, "mean_excess_picks": 0.01, "decile_spread": 0.05, "decile_t": 2.5,
        "effect_size": 0.3, "sharpe": 1.0, "deflated_sharpe": 0.9, "pbo": 0.3, "picks_t": 3.0,
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
        row(
            "random:scr",
            "random",
            "draw",
            horizon_sessions=horizon,
            lift=1.0 if i < beaten else 1.5,
        )
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


def test_works_needs_a_t_of_three_on_the_picks_series_as_well_as_the_decile_spread() -> None:
    """Owner 2026-10-17 (ADR 0065 amendment): both t series gate Works; Promising asks only the
    decile t."""
    strong = {"decile_t": 3.5, "decile_spread": 0.9}
    whole = {"sessions": 100, "deflated_sharpe": 0.95, "pbo": 0.2}

    def judged(picks_t: float | None):
        return verdict(result(oos={**strong, "picks_t": picks_t}, whole=whole), draws=draws(100))

    assert judged(3.0).verdict == WORKS
    low = judged(2.99)
    assert low.verdict == PROMISING
    assert "Picks-series t" in low.rationale
    crit = {c.id: c for c in low.criteria}
    assert (crit["works_picks_t"].status, crit["works_picks_t"].threshold) == ("fail", "at least 3")
    unstored = judged(None)  # a run from before the column
    assert unstored.verdict == PROMISING
    assert {c.id: c.status for c in unstored.criteria}["works_picks_t"] == "not_measured"
    promising = {c.id: c.status for c in low.criteria if c.level == "promising"}
    assert set(promising.values()) <= {"pass", "not_applicable"}  # the picks t never blocks it


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


def test_the_candidate_best_in_sample_is_the_verdict_and_names_its_screen() -> None:
    rows = [
        *result(),
        row(variant="other", kind="frozen", hit_rate=0.90),  # better out of sample: not read
        row(variant="other", kind="all"),
        row(variant="other", kind="in_sample", hit_rate=0.55),
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


def test_no_declared_baselines_is_not_applicable_never_a_pass_and_the_level_is_unchanged() -> None:
    v = verdict(result(baselines=()), decoys=False)
    assert v.verdict == PROMISING
    by = {c.id: c for c in v.criteria}
    for cid in ("baselines", "works_spread"):
        assert (by[cid].status, by[cid].value) == ("not_applicable", "no decoys declared")
    assert v.rationale.startswith("Trades, and out-of-sample trades")  # the gap is not the decoys
    # with decoys the same rows judge as before: a declared baseline with no stored row is not
    # measured, and a decoy that is beaten passes
    assert verdict(result(baselines=())).verdict == NOT_ENOUGH
    beaten = {c.id: c.status for c in verdict(result()).criteria}
    assert beaten["baselines"] == "pass"
    # the level is the same with and without the decoy criteria's pass
    assert verdict(result(baselines=(0.5,)), decoys=False).verdict == verdict(result()).verdict


def test_no_decoys_never_block_works() -> None:
    strong = result(
        oos={"decile_t": 3.0, "decile_spread": 0.9},
        whole={"sessions": 100, "deflated_sharpe": 0.95, "pbo": 0.2},
        baselines=(),
    )
    v = verdict(strong, draws=draws(100), decoys=False)
    assert v.verdict == WORKS
    assert {c.status for c in v.criteria if c.id in ("baselines", "works_spread")} == {
        "not_applicable"
    }


def test_a_basis_chosen_among_several_says_what_it_was_chosen_on() -> None:
    rows = grid({15: 0.485, 21: 0.512, 31: 0.499}, {15: 0.53, 21: 0.52, 31: 0.60})
    choice = choose_basis(rows, T)
    assert choice.why == "chosen on in-sample lift: 21 d +1.2 pts, 31 d -0.1 pts, 15 d -1.5 pts"
    assert verdict(rows).basis_why == choice.why
    assert choose_basis(rows, T, Declared(horizon=15)).why == ""  # declared: nothing to explain
    assert verdict(result()).basis_why == ""  # the one candidate


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


def parts(year: str = "2026") -> list[EdgeRow]:
    return [
        row(kind="year", slice_value=year),
        row(kind="year_part", slice_value=f"{year}:in_sample", sessions=3),
        row(kind="year_part", slice_value=f"{year}:out_of_sample", sessions=9),
    ]


def test_a_year_the_split_cuts_is_two_rows_not_a_both_row() -> None:
    rows = [*result(), row(kind="year", slice_value="2025"), *parts()]
    years = verdict(rows).years
    assert [(y.year, y.period, y.label, y.partial) for y in years] == [
        ("2025", IN_SAMPLE, "2025", False),
        ("2026", IN_SAMPLE, "2026 Jan\u2013Mar", True),
        ("2026", OUT_OF_SAMPLE, "2026 Apr\u2013Dec", True),
    ]
    assert BOTH not in {y.period for y in years}
    first, second = years[1], years[2]
    assert (first.from_date, first.to_date) == (date(2026, 1, 1), date(2026, 3, 31))
    assert (second.from_date, second.to_date) == (SPLIT, date(2026, 12, 31))
    assert (first.trades, second.trades) == (3, 9)
    assert (years[0].from_date, years[0].to_date) == (date(2025, 1, 1), date(2025, 12, 31))


def test_years_before_the_screens_first_session_are_not_rows_and_the_split_ends_at_the_run() -> (
    None
):
    empty = [row(kind="year", slice_value=str(y), sessions=0) for y in range(2010, 2024)]
    rows = [*result(), *empty, row(kind="year", slice_value="2025"), *parts()]
    years = judge("e", rows, SPLIT, T, range_to=date(2026, 10, 9)).years
    assert [y.label for y in years] == ["2025", "2026 Jan\u2013Mar", "2026 Apr\u2013Oct"]
    assert years[-1].to_date == date(2026, 10, 9)
    # a year after the last with sessions goes too
    tail = [*rows, row(kind="year", slice_value="2027", sessions=0)]
    assert [y.year for y in judge("e", tail, SPLIT, T).years][-1] == "2026"


def test_a_moved_split_cuts_its_own_year_and_never_inverts_the_dates() -> None:
    rows = [*result(), *parts("2025")]
    moved = judge("e", rows, date(2025, 7, 1), T).years  # a copy's run split on 2025-07-01
    assert [(y.label, y.from_date, y.to_date) for y in moved] == [
        ("2025 Jan\u2013Jun", date(2025, 1, 1), date(2025, 6, 30)),
        ("2025 Jul\u2013Dec", date(2025, 7, 1), date(2025, 12, 31)),
    ]
    (y,) = verdict(rows).years  # parts stored at another split: one row, never wrong dates
    assert (y.period, y.partial, y.from_date, y.to_date) == (
        BOTH,
        False,
        date(2025, 1, 1),
        date(2025, 12, 31),
    )


def test_a_run_without_year_parts_keeps_the_both_row() -> None:
    rows = [*result(), row(kind="year", slice_value="2026")]
    (y,) = verdict(rows).years
    assert (y.period, y.label, y.partial) == (BOTH, "2026", False)


def test_columns_are_in_sample_out_of_sample_and_all() -> None:
    rows = result(
        oos={"sessions": 12, "hit_rate": 0.7, "deflated_sharpe": None, "pbo": None},
        whole={"deflated_sharpe": 0.9, "pbo": 0.3},
        insample={"sessions": 40},
    )
    cols = verdict(rows).columns
    assert [c.period for c in cols] == [IN_SAMPLE, OUT_OF_SAMPLE, ALL]
    ins, oos, whole = cols
    assert (ins.trades, oos.trades, whole.trades) == (40, 12, 70)
    assert oos.win_rate == 0.7 and round(oos.lift_pts or 0) == 20
    assert (whole.deflated_sharpe, whole.pbo) == (0.9, 0.3)  # the verdict's value
    assert oos.deflated_sharpe is None and oos.pbo is None  # the side's own, not stored
    assert (ins.thin, oos.thin, whole.thin) == (False, True, False)


def test_columns_of_an_older_run_have_no_in_sample_figures_and_waiting_has_none() -> None:
    rows = [r for r in result() if r.slice_kind != "in_sample"]
    ins = verdict(rows).columns[0]
    assert ins.period == IN_SAMPLE and ins.win_rate is None and ins.trades is None
    assert verdict(None).columns == () and verdict(None).evidence is None


# --- the basis is fixed before the frozen period is read (ADR 0065) ------------------------

# every slice whose figures cover the frozen period
OOS_KINDS = ("frozen", "split", "year", "year_part", "regime", "all")


def grid(insample: dict[int, float], oos: dict[int, float], variant: str = "vrp") -> list[EdgeRow]:
    """One screen at several horizons: in-sample and out-of-sample win rates against a 0.50 base
    rate (lift points = (rate - 0.50) * 100), enough trades for a verdict, one baseline each."""
    rows: list[EdgeRow] = []
    for h in sorted(insample):
        rows += [
            row(variant, kind="in_sample", horizon_sessions=h, hit_rate=insample[h]),
            row(variant, kind="frozen", horizon_sessions=h, hit_rate=oos[h]),
            row(variant, kind="all", horizon_sessions=h, sessions=70),
            row(variant, kind="year", horizon_sessions=h, slice_value="2026", hit_rate=oos[h]),
            row(variant, kind="year_part", horizon_sessions=h, slice_value="2026:out_of_sample"),
            row("b0", role="baseline", kind="frozen", horizon_sessions=h, lift=1.0),
            row("b0", role="baseline", kind="in_sample", horizon_sessions=h, lift=1.0),
        ]
    return rows


def test_vrp_rests_on_the_horizon_best_in_sample_not_the_best_out_of_sample() -> None:
    # vrp_short_premium's run: in-sample +1.2 pts at 21 sessions, -1.5 at 15, -0.1 at 31; the
    # 31-session horizon has the best out-of-sample figure and was the basis before ADR 0065.
    rows = grid({15: 0.485, 21: 0.512, 31: 0.499}, {15: 0.53, 21: 0.52, 31: 0.60})
    assert choose_basis(rows, T).key == ("vrp", 21)
    v = verdict(rows)
    assert v.basis == "vrp, 21 trading days"
    assert v.win_rate == 0.52  # every figure is the basis's, not the best out-of-sample one
    assert {c.win_rate for c in v.columns if c.period == IN_SAMPLE} == {0.512}


def _scrambled(r: EdgeRow, k: int) -> EdgeRow:
    """``r`` with every figure changed (numbers scaled and shifted, None to a number, a number
    to None every other ``k``): only the row's identity is kept."""
    keep = {"edge_variant", "variant", "role", "horizon_sessions", "slice_kind", "slice_value"}
    changes: dict[str, object] = {}
    for f in fields(r):
        value = getattr(r, f.name)
        if f.name in keep or isinstance(value, (bool, str)):
            continue
        if isinstance(value, tuple):
            changes[f.name] = tuple(-3.0 * k for _ in value) or (float(k),)
        elif value is None:
            changes[f.name] = 0.5 * k
        else:
            changes[f.name] = None if k % 2 else value * -5 + k
    return replace(r, **changes)  # type: ignore[arg-type]


def test_the_basis_is_invariant_to_any_change_of_the_out_of_sample_rows() -> None:
    rows = grid({15: 0.485, 21: 0.512, 31: 0.499}, {15: 0.53, 21: 0.52, 31: 0.60})
    rows += [
        row("vrp", kind="regime", horizon_sessions=h, slice_value="calm") for h in (15, 21, 31)
    ]
    chosen = choose_basis(rows, T)
    assert chosen.key == ("vrp", 21)
    for k in range(1, 5):  # every figure of every row that reads the frozen period, pbo and DSR too
        changed = [_scrambled(r, k) if r.slice_kind in OOS_KINDS else r for r in rows]
        assert changed != rows
        assert choose_basis(changed, T) == chosen
    dropped = [r for r in rows if r.slice_kind not in OOS_KINDS or r.slice_kind == "all"]
    assert choose_basis(dropped, T) == chosen
    named_by_in_sample = [r for r in rows if r.slice_kind == "in_sample" or r.role == "baseline"]
    assert choose_basis(named_by_in_sample, T) == chosen
    assert verdict(named_by_in_sample).basis == "vrp, 21 trading days"  # waiting, same basis


def test_a_model_screener_in_sample_fit_never_ranks_it_only_promoted_makes_it_the_basis() -> None:
    rules = grid({21: 0.512}, {21: 0.52})
    fitted = [  # the model's in-sample row is its training fit (in_sample=True): a huge lift
        replace(r, in_sample=r.slice_kind == "in_sample")
        for r in grid({21: 0.95}, {21: 0.90}, variant="model")
        if r.role != "baseline"
    ]
    assert choose_basis([*rules, *fitted], T).key == ("vrp", 21)
    assert choose_basis([*rules, *fitted], T, Declared(screener="model")).key == ("model", 21)
    alone = choose_basis(fitted + [r for r in rules if r.role == "baseline"], T)
    assert alone.key == ("model", 21)  # the only candidate: nothing is ranked


def test_a_declared_horizon_and_screener_fix_the_basis_whatever_the_figures() -> None:
    rows = grid({15: 0.485, 21: 0.512, 31: 0.499}, {15: 0.53, 21: 0.52, 31: 0.60})
    assert choose_basis(rows, T, Declared(horizon=15)) == BasisChoice(("vrp", 15))
    assert verdict(rows, declared=Declared(horizon=15)).basis == "vrp, 15 trading days"
    two = [*rows, *grid({21: 0.70}, {21: 0.40}, variant="model")]
    assert choose_basis(two, T).key == ("model", 21)  # in-sample best across screens
    assert choose_basis(two, T, Declared(screener="vrp")).key == ("vrp", 21)
    assert choose_basis(two, T, Declared("vrp", 31)).key == ("vrp", 31)


def test_a_declared_basis_the_result_does_not_have_is_waiting_and_named() -> None:
    rows = grid({21: 0.512}, {21: 0.52})
    v = verdict(rows, declared=Declared("vrp", 31))
    assert v.verdict == WAITING and "vrp, 31 trading days" in v.rationale


def test_an_older_run_without_in_sample_rows_is_waiting_unless_one_candidate() -> None:
    rows = [
        r for r in grid({15: 0.485, 21: 0.512}, {15: 0.53, 21: 0.6}) if r.slice_kind != "in_sample"
    ]
    v = verdict(rows)
    assert v.verdict == WAITING and "in-sample" in v.rationale and v.basis is None
    single = [r for r in grid({21: 0.512}, {21: 0.6}) if r.slice_kind != "in_sample"]
    assert verdict(single).basis == "vrp, 21 trading days"  # nothing to choose: no figure read
    declared = verdict(rows, declared=Declared(horizon=21))
    assert declared.basis == "vrp, 21 trading days" and declared.verdict != WAITING


def test_the_in_sample_ranking_puts_a_hard_failure_below_a_candidate_without_one() -> None:
    rows = grid({15: 0.60, 21: 0.55}, {15: 0.6, 21: 0.6})
    rows = [
        replace(r, decile_t=-1.0) if r.slice_kind == "in_sample" and r.horizon_sessions == 15 else r
        for r in rows
    ]
    assert choose_basis(rows, T).key == ("vrp", 21)  # 15 has the bigger lift but fails in-sample t


def test_the_haircut_of_a_stored_run_counts_the_series_sessions_with_picks(
    backend: MemoryBackend,
) -> None:
    days = [date(2026, 1, 2) + timedelta(days=30 * i) for i in range(5)]  # no overlap: weight 1
    stored = [series_row(d, FROZEN) for d in days[:3]]
    stored += [series_row(d, FROZEN, status="excluded_coverage", picks=None) for d in days[3:]]
    write_run(
        backend, "r1", FROZEN, 0.6, series=stored,
        whole={"sessions": 70, "sharpe": 0.4, "trials": 5},
    )  # fmt: skip
    ctx = stores(backend)
    edge = load_edge(ctx, "drift")
    assert edge is not None
    h = load_edge_verdict(ctx, edge).haircut
    assert h is not None and (h.sessions, h.trials) == (3, 5)


def test_the_figures_columns_carry_the_touch_and_risk_neutral_rates_when_stored() -> None:
    rows = result(oos={"reference_rate": 0.61, "touch_rate": 0.42}, insample={"touch_rate": 0.54})
    by = {c.period: c for c in verdict(rows).columns}
    assert (by["out_of_sample"].reference_rate, by["out_of_sample"].touch_rate) == (0.61, 0.42)
    assert (by["in_sample"].reference_rate, by["in_sample"].touch_rate) == (None, 0.54)
    assert by["all"].touch_rate is None  # not stored: never a zero


def test_a_lone_trial_has_no_overfitting_test_and_can_still_reach_promising() -> None:
    """ADR 0064 amendment 2026-10-11: PBO needs alternatives of the edge, never baselines, so a
    lone screener's PBO is None and the two PBO criteria do not apply (not a pass, not a gap)."""
    no_pbo = {"oos": {"pbo": None}, "whole": {"pbo": None}}
    lone = verdict(result(**no_pbo))  # type: ignore[arg-type]
    assert lone.verdict == PROMISING
    pbo = {c.id: c.status for c in lone.criteria if c.id in ("pbo", "works_pbo")}
    assert pbo == {"pbo": "not_applicable", "works_pbo": "not_applicable"}
    assert "overfitting" not in lone.rationale
    # a second screener at the holding period: PBO None means not stored, which blocks
    peer = row(variant="scr2", kind="all", pbo=None)
    two = verdict([*result(**no_pbo), peer])  # type: ignore[arg-type]
    assert next(c for c in two.criteria if c.id == "pbo").status == "not_measured"
    assert two.verdict != PROMISING
    # the hard fail still fires when PBO exists
    assert verdict(result(whole={"pbo": 0.51})).verdict == NOT_WORKING


def test_a_long_short_result_is_a_diagnostic_and_never_the_basis() -> None:
    """Owner decision 2026-10-17: a spread is not a verdict basis, however good it looks."""
    spread = [replace(r, side="long_short") for r in result()]
    v = verdict(spread)
    assert v.verdict == DIAGNOSTIC and v.side == "long_short" and v.basis is None
    assert "diagnostic" in v.rationale and "no verdict rests on it" in v.rationale


def test_a_short_result_is_judged_like_any_and_says_it_is_the_short_leg() -> None:
    short = [replace(r, side="short") for r in result()]
    v = verdict(short)
    assert v.verdict == PROMISING and v.side == "short"
    assert "(short leg)" in v.headline
    plain = verdict(result())
    assert plain.side == "long" and "(short leg)" not in plain.headline
    assert (v.verdict, v.lift_pts, v.decile_t) == (plain.verdict, plain.lift_pts, plain.decile_t)


def _without_figure(rows: list[EdgeRow], variant: str) -> list[EdgeRow]:
    return [
        dataclasses.replace(r, lift=None, decile_spread=None) if r.variant == variant else r
        for r in rows
    ]


def test_a_decoy_with_no_figure_is_not_measured_never_left_out_of_beats_every_baseline() -> None:
    """Beating the measured decoys is not beating them all: the criterion reads not measured
    and says how many were measured; a loss to a measured decoy is still a loss."""
    rows = _without_figure(result(oos={"lift": 1.5}, baselines=(1.05, 1.1, 1.2)), "b2")
    by = {c.id: c for c in verdict(rows).criteria}
    for crit in ("baselines", "works_spread"):
        assert by[crit].status == "not_measured", crit
    assert "2 of 3 measured" in by["baselines"].value
    assert "2 of 3 measured" in by["works_spread"].value
    lost = _without_figure(result(oos={"lift": 1.0}, baselines=(1.05, 1.1, 1.2)), "b2")
    assert {c.id: c.status for c in verdict(lost).criteria}["baselines"] == "fail"
    whole = {c.id: c for c in verdict(result(oos={"lift": 1.5}, baselines=(1.05, 1.1))).criteria}
    assert whole["baselines"].status == "pass" and "measured" not in whole["baselines"].value


def test_a_chain_edge_can_be_promising_but_never_works_without_an_in_sample_basis() -> None:
    """No in-sample history exists for the chain grain (ADR 0065 amendment 2026-10-18): the lift
    that keeps its size does not apply, and a Works criterion stays unmet."""
    strong = result(
        oos={"decile_t": 3.0, "decile_spread": 0.9},
        whole={"sessions": 100, "deflated_sharpe": 0.95, "pbo": 0.2},
    )
    rows = [r for r in strong if r.slice_kind != "in_sample"]  # nothing in-sample exists
    chain = EdgeFacts(chain=True)
    v = verdict(rows, draws=draws(100), facts=chain)
    assert v.verdict == PROMISING and "Basis fixed on an in-sample period" in v.rationale
    by = {c.id: c for c in v.criteria}
    assert by["oos_lift"].status == "not_applicable" and by["basis_in_sample"].status == "fail"
    # an ordinary edge with the same rows still waits on its in-sample figures instead
    plain = verdict(rows, draws=draws(100))
    assert plain.verdict == NOT_ENOUGH and "basis_in_sample" not in {c.id for c in plain.criteria}
