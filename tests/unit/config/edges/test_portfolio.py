"""The portfolio_return outcome of an edge document (ADR 0074): the blend of a ``mix:`` benchmark
parses closed, the weighting and its volatility feature agree, a book is long, banded by nothing and
rebalanced on a schedule whose windows never overlap, and ``base = "benchmark"`` is its alone."""

import tomllib
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from algotrade.config.edges.document import Edge, parse_edge
from algotrade.config.edges.identity import identity_dict
from algotrade.config.edges.loading import load_edges
from algotrade.config.edges.portfolio import (
    CASH,
    benchmark_words,
    blend,
    parse_mix,
)
from algotrade.core.model.errors import ConfigurationError
from algotrade.features.rollups.bridges.etf_map import CAPE_ETFS, FX_ETFS, RATE_SERIES, SIGNAL_ETFS
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT
from tests.unit.services.evaluation.cross_section.conftest import edge_document


def test_a_mix_parses_into_weights_in_the_order_written() -> None:
    assert parse_mix("mix:SPY=0.6,AGG=0.4") == (("SPY", 0.6), ("AGG", 0.4))
    assert parse_mix("mix: SPY = 0.5 , TLT=0.25,GLD=0.25") == (
        ("SPY", 0.5),
        ("TLT", 0.25),
        ("GLD", 0.25),
    )
    assert parse_mix("mix:BRK.B=1") == (("BRK.B", 1.0),)  # a lone constituent is a plain index


def test_a_plain_benchmark_is_a_blend_of_itself() -> None:
    assert blend("SPY") == (("SPY", 1.0),)
    assert blend("mix:SPY=0.6,AGG=0.4") == (("SPY", 0.6), ("AGG", 0.4))


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("SPY", "is not a mix"),
        ("mix:SPY=0.6,AGG=0.3", "add to 0.9, not 1"),  # never normalised
        ("mix:SPY=0.6,SPY=0.4", "SPY is listed twice"),
        ("mix:SPY=1.2,AGG=-0.2", "must be in \\(0, 1\\]"),
        ("mix:SPY=0,AGG=1", "must be in \\(0, 1\\]"),
        ("mix:SPY=nan,AGG=1", "must be in \\(0, 1\\]"),
        ("mix:SPY=abc,AGG=1", "not a number"),
        ("mix:SPY,AGG=1", "is not TICKER=weight"),
        ("mix:EQ:SPY=0.5,AGG=0.5", "is not TICKER=weight"),  # an id is never a ticker
        ("mix:spy=0.5,AGG=0.5", "is not TICKER=weight"),
        ("mix:", "is not TICKER=weight"),
    ],
)
def test_a_bad_mix_is_refused_closed(text: str, message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        parse_mix(text)


def test_a_benchmark_is_said_in_words() -> None:
    assert benchmark_words("SPY") == "SPY"
    assert benchmark_words("mix:SPY=0.6,AGG=0.4") == "a blend of 60% SPY and 40% AGG"
    assert benchmark_words("mix:SPY=0.5,TLT=0.25,GLD=0.25") == (
        "a blend of 50% SPY, 25% TLT and 25% GLD"
    )


def outcome(**changes: Any) -> dict[str, Any]:
    base = {
        "kind": "portfolio_return",
        "horizon_sessions": [21],
        "benchmark": "mix:SPY=0.6,AGG=0.4",
        "start_offset_sessions": 1,
        "weighting": "inverse_vol",
        "vol_field": "rollup.price_stats@v2.realised_vol_60d",
        "cost_bps": 5,
    }
    return {k: v for k, v in {**base, **changes}.items() if v is not None}


def book(**changes: Any) -> Edge:
    doc = edge_document(**{"schedule": "month_end", "top_k": 3, "outcome": outcome(), **changes})
    return parse_edge(doc, "drift", "drift.toml")


def test_a_portfolio_outcome_types_into_the_edge() -> None:
    e = book()
    o = e.outcome
    assert (o.kind, o.benchmark, o.weighting) == (
        "portfolio_return",
        "mix:SPY=0.6,AGG=0.4",
        "inverse_vol",
    )
    assert o.vol_field == "rollup.price_stats@v2.realised_vol_60d"
    assert o.is_return and e.base == "benchmark"  # the benchmark is its base unless it says so
    assert book(base="benchmark").base == "benchmark"
    assert book(outcome=outcome(weighting=None, vol_field=None)).outcome.weighting == "equal"
    assert CASH == "CASH"


def test_a_plain_benchmark_index_is_a_portfolio_benchmark_too() -> None:
    assert book(outcome=outcome(benchmark="SPY")).outcome.benchmark == "SPY"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"outcome": outcome(benchmark="none")}, "read against \\['SPY'\\] or a mix"),
        ({"outcome": outcome(benchmark=None)}, "benchmark: required for a portfolio_return"),
        ({"outcome": outcome(benchmark="mix:SPY=0.9")}, "add to 0.9, not 1"),
        ({"outcome": outcome(vol_field=None)}, "an inverse_vol book needs the feature"),
        (
            {"outcome": outcome(weighting="equal")},
            "vol_field: only an inverse_vol book reads one",
        ),
        ({"outcome": outcome(weighting="kelly")}, "weighting: expected one of"),
        ({"outcome": outcome(side="short")}, "needs an excess_return outcome"),
        ({"outcome": outcome(max_drawdown=0.2)}, "max_drawdown: not for a portfolio_return"),
        ({"outcome": outcome(hold_rank=5)}, "a band is for a long or short excess_return"),
        ({"schedule": "every_session"}, "rebalances on month_end, or every_session held one"),
        ({"schedule": "on_event:earnings_reaction"}, "rebalances on month_end"),
        ({"base": "universe"}, "compared with its benchmark"),
        ({"base": "event"}, "compared with its benchmark|needs an on_event schedule"),
    ],
)
def test_a_portfolio_outcome_is_refused_where_it_means_nothing(
    changes: dict[str, Any], message: str
) -> None:
    with pytest.raises(ConfigurationError, match=message):
        book(**changes)


def test_a_book_may_rebalance_daily_when_held_one_session() -> None:
    doc = edge_document(
        schedule="every_session",
        top_k=3,
        outcome=outcome(horizon_sessions=[1], weighting=None, vol_field=None),
    )
    assert parse_edge(doc, "drift", "drift.toml").schedule == "every_session"


@pytest.mark.parametrize("key", ["weighting", "vol_field"])
def test_only_a_portfolio_outcome_names_a_weighting(key: str) -> None:
    doc = edge_document(schedule="month_end", top_k=3)
    doc["outcome"] = {**doc["outcome"], key: "equal"}
    with pytest.raises(ConfigurationError, match=f"{key}: only a portfolio_return outcome"):
        parse_edge(doc, "drift", "drift.toml")


def test_the_benchmark_base_belongs_to_a_portfolio_outcome_alone() -> None:
    with pytest.raises(ConfigurationError, match="belongs to a portfolio_return outcome"):
        parse_edge(edge_document(base="benchmark"), "drift", "drift.toml")


def test_a_variant_may_not_carry_the_wrong_base_for_its_kind() -> None:
    variant = {"id": "spy", "outcome": {"benchmark": "SPY"}}
    assert book(variants=[variant]).variants[0].outcome.benchmark == "SPY"
    with pytest.raises(ConfigurationError, match="compared with its benchmark"):
        book(variants=[{"id": "u", "base": "universe"}])


def test_the_default_weighting_stays_out_of_an_identity() -> None:
    """A document with no weighting hashes as it did before the key existed (no leg is
    recomputed), and a book's own weighting is part of what it measures."""
    plain = edge_document()
    plain_edge = parse_edge(plain, "drift", "drift.toml")
    identity = identity_dict(plain_edge.outcome.__dict__)
    assert "weighting" not in identity and "vol_field" not in identity
    weighted = identity_dict(book().outcome.__dict__)
    assert weighted["weighting"] == "inverse_vol"
    other = book(outcome=outcome(weighting="equal", vol_field=None)).outcome
    assert identity_dict(other.__dict__) != weighted


def ensemble(**changes: Any) -> Edge:
    base = {"screeners": ["mom3", "mom6", "mom9"], "ensemble": {"variants": ["mom3", "mom6"]}}
    return book(**{**base, **changes})


def test_an_ensemble_names_its_grid_among_the_screeners() -> None:
    e = ensemble()
    assert e.ensemble == ("mom3", "mom6")  # mom9 is a screener of its own, not a member
    assert book().ensemble == ()  # none declared
    assert ensemble(oos_class="trend").oos_class == "trend" and ensemble().oos_class is None


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"ensemble": {"variants": ["mom3"]}}, "two or more distinct screeners"),
        ({"ensemble": {"variants": ["mom3", "mom3"]}}, "two or more distinct screeners"),
        ({"ensemble": {"variants": []}}, "two or more distinct screeners"),
        ({"ensemble": {"variants": ["mom3", "mom12"]}}, "\\['mom12'\\] are not among the edge's"),
        ({"ensemble": {"variants": ["mom3", "mom6"], "weights": [1, 1]}}, "weights"),
        ({"screeners": ["ensemble", "mom3"]}, "'ensemble' is the id of an ensemble"),
        ({"oos_class": "momentum"}, "oos_class: expected one of"),
    ],
)
def test_an_ensemble_or_haircut_class_is_refused_where_it_means_nothing(
    changes: dict[str, Any], message: str
) -> None:
    with pytest.raises(ConfigurationError, match=message):
        ensemble(**changes)


def test_an_ensemble_is_for_a_portfolio_outcome_only() -> None:
    doc = edge_document(
        screeners=["a", "b"], top_k=3, ensemble={"variants": ["a", "b"]}, schedule="month_end"
    )
    with pytest.raises(ConfigurationError, match="ensemble: only a portfolio_return outcome"):
        parse_edge(doc, "drift", "drift.toml")


def test_an_ensemble_is_part_of_the_run_and_an_empty_one_is_not() -> None:
    assert "ensemble" not in identity_dict({"ensemble": (), "top_k": 3})
    assert identity_dict({"ensemble": ("a", "b")})["ensemble"] == ["a", "b"]


def test_a_vol_target_parses_with_its_defaults_and_is_part_of_the_identity() -> None:
    """ADR 0074 amendment: ``vol_target`` is a fraction a year, ``vol_window`` defaults to 60
    sessions and ``vol_return_field`` to the stored daily return; no target, none of the three is
    part of an outcome's identity (no existing hash moves), a target is."""
    plain = book(outcome=outcome(weighting=None, vol_field=None)).outcome
    assert (plain.vol_target, plain.vol_window) == (None, 60)
    assert plain.vol_return_field == "rollup.trend_stats@v2.ret_1d"
    bare = identity_dict(plain.__dict__)
    assert not {"vol_target", "vol_window", "vol_return_field"} & set(bare)
    sized = book(outcome=outcome(vol_target=0.1, vol_window=40, vol_return_field="a.b@v1.c"))
    o = sized.outcome
    assert (o.vol_target, o.vol_window, o.vol_return_field) == (0.1, 40, "a.b@v1.c")
    kept = identity_dict(o.__dict__)
    assert (kept["vol_target"], kept["vol_window"]) == (0.1, 40)
    assert identity_dict(book(outcome=outcome(vol_target=0.1)).outcome.__dict__) != kept
    assert identity_dict(book(outcome=outcome(vol_target=0.12)).outcome.__dict__) != identity_dict(
        book(outcome=outcome(vol_target=0.1)).outcome.__dict__
    )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"vol_target": 0}, "vol_target"),
        ({"vol_target": -0.1}, "vol_target"),
        ({"vol_target": 1.5}, "vol_target: expected a fraction in \\(0, 1\\]"),
        ({"vol_target": 0.1, "vol_window": 5}, "vol_window"),
        ({"vol_target": 0.1, "vol_window": 20.5}, "vol_window"),
        ({"vol_window": 60}, "vol_window: needs a vol_target"),
        ({"vol_return_field": "a.b@v1.c"}, "vol_return_field: needs a vol_target"),
    ],
)
def test_a_bad_vol_target_is_refused(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        book(outcome=outcome(**changes))


@pytest.mark.parametrize("key", ["vol_target", "vol_window", "vol_return_field"])
def test_only_a_portfolio_outcome_names_a_vol_target(key: str) -> None:
    doc = edge_document(schedule="month_end", top_k=3)
    doc["outcome"] = {**doc["outcome"], key: 0.1 if key == "vol_target" else 60}
    with pytest.raises(ConfigurationError, match=f"{key}: only a portfolio_return outcome"):
        parse_edge(doc, "drift", "drift.toml")


BOOKS = [
    e
    for e in load_edges(FileConfigStore(REPO_ROOT / "config", local=False))
    if e.outcome.kind == "portfolio_return"
]


def test_the_shipped_allocation_edges_are_allocation_edges() -> None:
    """EB E5: ten documents ship a book of ETFs; every one has a preset for each screener it
    lists, a book no larger than its universe, and a benchmark whose weights add to one."""
    assert len(BOOKS) >= 10
    for e in BOOKS:
        symbols = {r.value for r in e.universe.where.rules()}  # type: ignore[union-attr]
        names = [n for r in e.universe.where.rules() for n in r.value]  # type: ignore[union-attr]
        assert symbols and e.top_k is not None and e.top_k <= len(names), e.id
        for screener in e.screeners:
            path = REPO_ROOT / f"config/site/presets/screeners/{screener}/v1.toml"
            assert path.exists(), f"{e.id}: no preset {screener}"
        assert abs(sum(w for _, w in blend(e.outcome.benchmark)) - 1.0) < 1e-6, e.id


def test_a_trend_book_declares_its_ensemble_of_lookbacks() -> None:
    """ADR 0074 amendment: an edge of class ``trend`` is read as a grid of lookbacks, one trial,
    never a single lookback chosen after the fact."""
    trend = [e for e in BOOKS if e.oos_class == "trend"]
    assert len(trend) >= 7
    for e in trend:
        assert len(e.ensemble) >= 2 and set(e.ensemble) <= set(e.screeners), e.id


CANARY = {"tickers": ["VWO", "BND"], "field": "rollup.trend_stats@v2.ret_1d", "breadth": 2}


def test_a_canary_parses_and_is_part_of_the_identity() -> None:
    """ADR 0074 amendment item 17: the canaries, the field read at D, the breadth and the defensive
    choice; no canary, no key in the identity (no existing hash moves)."""
    o = book(outcome=outcome(canary={**CANARY, "defensive": ["CASH"]})).outcome
    c = o.canary
    assert c is not None and (c.tickers, c.breadth, c.defensive) == (("BND", "VWO"), 2, ("CASH",))
    assert c.field == "rollup.trend_stats@v2.ret_1d"
    assert identity_dict(asdict(o))["canary"]["tickers"] == ["BND", "VWO"]
    assert "canary" not in identity_dict(asdict(book().outcome))
    other = book(outcome=outcome(canary={**CANARY, "defensive": ["SHY", "IEF"]})).outcome
    assert other.canary is not None and other.canary.defensive == ("IEF", "SHY")  # sorted
    assert identity_dict(asdict(other)) != identity_dict(asdict(o))
    reordered = book(
        outcome=outcome(canary={**CANARY, "tickers": ["BND", "VWO"], "defensive": ["IEF", "SHY"]})
    ).outcome
    assert identity_dict(asdict(reordered)) == identity_dict(asdict(other))  # order is no trial


@pytest.mark.parametrize(
    ("canary", "message"),
    [
        ({**CANARY, "tickers": []}, "tickers: expected one or more distinct"),
        ({**CANARY, "tickers": ["VWO", "VWO"]}, "tickers: expected one or more distinct"),
        ({**CANARY, "tickers": ["VWO", "eq:bnd"]}, "are not plain symbols"),
        ({**CANARY, "tickers": ["VWO", "CASH"]}, "CASH is only the whole defensive choice"),
        ({**CANARY, "defensive": []}, "defensive: expected one or more distinct"),
        ({**CANARY, "defensive": ["CASH", "SHY"]}, "CASH is only the whole defensive choice"),
        ({**CANARY, "breadth": 0}, "breadth"),
        ({**CANARY, "breadth": 3}, "more than the 2 canaries"),
        ({k: v for k, v in CANARY.items() if k != "field"}, "field: expected a non-empty string"),
        ({**CANARY, "defensive": ["CASH"], "weights": [1]}, "weights"),
    ],
)
def test_a_bad_canary_is_refused(canary: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        book(outcome=outcome(canary={"defensive": ["CASH"], **canary}))


def test_only_a_portfolio_outcome_has_a_canary() -> None:
    doc = edge_document(schedule="month_end", top_k=3)
    doc["outcome"] = {**doc["outcome"], "canary": {**CANARY, "defensive": ["CASH"]}}
    with pytest.raises(ConfigurationError, match="canary: only a portfolio_return outcome"):
        parse_edge(doc, "drift", "drift.toml")


# --- the macro allocation documents of EB E5 batch Y: a signal that lives on one carrier fund of
# etf_macro@v1 must be read from a fund that carries it, or the screen is silently empty (a null
# never passes); each document's universe, canary and screener reads are checked against the
# bridge's own map, so a map change or a typo fails here and not in a run that holds cash.

EDGES = {e.id: e for e in BOOKS}
PRESETS = REPO_ROOT / "config/site/presets/screeners"
BRIDGE = "rollup.etf_macro@v1."


def symbols(edge: Edge) -> set[str]:
    return {n for r in edge.universe.where.rules() for n in r.value}  # type: ignore[union-attr]


def criteria(screener: str) -> dict[str, dict[str, object]]:
    return tomllib.loads(Path(PRESETS / screener / "v1.toml").read_text())["criteria"]


def test_the_curve_screens_read_a_column_the_bond_funds_carry() -> None:
    edge = EDGES["bond_curve_timing"]
    assert symbols(edge) == {"TLT", "IEF"}
    for screener, column in (("bond_curve_trend_3m", "t10y3m"), ("bond_curve_trend_2y", "t10y2y")):
        assert screener in edge.screeners
        assert criteria(screener)["curve"]["field"] == BRIDGE + column
        assert symbols(edge) <= set(SIGNAL_ETFS[column]), f"{column}: a fund with no slope"
    assert set(edge.ensemble) == {"bond_curve_trend_3m", "bond_curve_trend_2y"}


def test_the_credit_macro_trial_is_not_listed_until_the_spread_history_is_long_enough() -> None:
    edge = EDGES["credit_spread_trend"]
    assert "credit_spread_below_ma200" not in edge.screeners  # series start 2023-10-09: ~28 months
    assert symbols(edge) == {"HYG", "LQD"}
    assert "HYG" in SIGNAL_ETFS["hy_oas"] and "LQD" in SIGNAL_ETFS["ig_oas"]


def test_the_value_leg_ranks_only_funds_with_a_country_series() -> None:
    value = EDGES["country_etf_momentum_value"]
    assert "country_cape_cheapest" in value.screeners
    assert "country_cape_cheapest" not in value.ensemble
    assert symbols(value) - set(CAPE_ETFS) == {"EWM", "FXI"}  # the two the document discloses
    assert criteria("country_cape_cheapest")["has_cape"]["field"] == BRIDGE + "cape"
    combo = EDGES["trend_carry_value_combo"]
    assert symbols(combo) <= set(CAPE_ETFS), "every fund of the combination has a CAPE"
    assert set(combo.ensemble) == {"trend_positive_12m", "country_cape_cheapest"}


def test_the_carry_leg_is_measured_for_the_funds_that_have_a_rate() -> None:
    edge = EDGES["fx_etf_carry_momentum"]
    assert "fx_carry_positive" in edge.screeners
    assert criteria("fx_carry_positive")["carry"]["field"] == BRIDGE + "fx_carry"
    with_rate = {t for t, code in FX_ETFS.items() if code in RATE_SERIES}
    measured = symbols(edge) & with_rate
    assert measured == {"FXY", "FXA", "FXC"}  # FXE, FXB (no fresh rate) and UUP are not


@pytest.mark.parametrize("edge_id", ["vix_roll_yield"])
def test_the_vix_gate_reads_a_signal_the_canary_fund_carries(edge_id: str) -> None:
    edge = EDGES[edge_id]
    assert symbols(edge) == {"SVXY"} and edge.screeners == ("etf_priced",)
    gates = [edge.outcome.canary, *(v.outcome.canary for v in edge.variants)]
    assert len(gates) == 2 and all(g is not None for g in gates)
    columns = set()
    for gate in gates:
        assert gate is not None and gate.defensive == ("CASH",) and gate.breadth == 1
        column = gate.field.removeprefix(BRIDGE)
        assert column in {"vx_basis", "vx_roll"}
        assert set(gate.tickers) <= set(SIGNAL_ETFS[column]), f"{column}: not the carrier"
        columns.add(column)
    assert columns == {"vx_basis", "vx_roll"}  # the pair of pre-registered gates


def test_the_canary_variants_are_vaa_and_daa_on_the_trend_book() -> None:
    edge = EDGES["absolute_momentum_crash_filter"]
    by_id = {v.id: v.outcome.canary for v in edge.variants}
    assert set(by_id) == {"canary_b1", "canary_daa"}
    vaa, daa = by_id["canary_b1"], by_id["canary_daa"]
    assert vaa is not None and daa is not None
    assert (vaa.breadth, daa.breadth) == (1, 2)
    assert vaa.tickers == daa.tickers == ("BND", "VWO")
    assert vaa.field == daa.field == "feature.momentum_13612w"
    assert vaa.defensive == daa.defensive == ("IEF", "LQD", "SHY")
    assert edge.outcome.canary is None  # the base book has no gate: the variants are the trials


def test_the_volatility_managed_book_targets_ten_percent_on_one_fund() -> None:
    edge = EDGES["vol_managed_equity"]
    assert symbols(edge) == {"SPY"} and edge.top_k == 1
    assert edge.outcome.vol_target == pytest.approx(0.10)
    assert edge.outcome.benchmark == "SPY"  # the benchmark is not scaled (decision log)
    assert edge.oos_class is None and edge.ensemble == ()  # one rule: no lookback grid
