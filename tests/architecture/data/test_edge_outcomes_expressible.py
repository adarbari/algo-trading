"""Every open site edge document can be scored by the harness against what is stored (ADR 0053): its
measure and drawdown fields are outcome fields, its horizons and benchmark are ones the outcomes
task writes, the implied vol a ratio measure divides by is in the catalogue, and its schedule is
one the harness runs (an event schedule with screeners only once its event field's group is in
the catalogue). And among the services/evaluation modules only the harness, the training frame
(learned scorers, ED7) and the winners study's labels (ED6) read outcomes, so the picks cannot see
one."""

import ast
from datetime import date

import pytest

from algotrade.config.edges.chain import MODEL_STRUCTURES
from algotrade.config.edges.document import ANNOUNCED_AHEAD, CLOSED, Edge
from algotrade.config.edges.loading import load_edges
from algotrade.config.edges.portfolio import MIX, PORTFOLIO_KIND
from algotrade.config.edges.schedules.markets import MARKET_TRIGGERS, market_trigger
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.calendar import sessions_between
from algotrade.data.outcomes import CHAIN_FIELDS, OUTCOME_FIELDS
from algotrade.services.configs import field_catalog
from algotrade.services.evaluation.cross_section.events import event_field
from algotrade.services.evaluation.cross_section.harness import MIXED_SOURCE_IV
from algotrade.services.evaluation.cross_section.hit import (
    CHAIN_PNL_FIELDS,
    EXPIRES_OTM_FIELDS,
    IMPLIED_VOL_FIELD,
    MEASURE_FIELDS,
    MODEL_PNL_FIELDS,
    PAIR_FIELDS,
)
from algotrade.services.evaluation.cross_section.portfolio.session import (
    FIELDS as PORTFOLIO_FIELDS,
)
from algotrade.services.evaluation.cross_section.sessions import decision_sessions
from algotrade.storage.configs.files import FileConfigStore
from algotrade_ingestion.tasks.derived.outcomes import horizons_and_benchmarks
from tests.conftest import REPO_ROOT

STORE = FileConfigStore(REPO_ROOT / "config", local=False)
EDGES = [e for e in load_edges(STORE) if e.status not in CLOSED]  # a closed edge is not scored
HARNESS = "src/algotrade/services/evaluation/cross_section/harness.py"
MEASURING = "src/algotrade/services/evaluation/cross_section/measuring.py"  # the harness's split
TRAINING = "src/algotrade/services/evaluation/training/frame.py"  # the one door for fit labels
DISCOVERY = "src/algotrade/services/evaluation/discovery/labels.py"  # the winners of the ED6 study
FORWARD = (
    "src/algotrade/services/evaluation/forward/settle.py"  # closes a followed edge's paper trades
)
TIME_SERIES = "src/algotrade/services/evaluation/time_series/harness.py"  # ADR 0073's seam
PROTECTED = "algotrade.data.outcomes"

OWN_FIELDS = ("expires_otm", "option_model_pnl", "option_pnl", PORTFOLIO_KIND, "pair_spread")


def _ids() -> list[str]:
    return [e.id for e in EDGES]


def _measure(edge: Edge) -> str:
    return edge.outcome.measure or "excess_return"


@pytest.mark.parametrize("edge", EDGES, ids=_ids())
def test_the_measure_and_the_path_condition_are_stored_outcome_fields(edge: Edge) -> None:
    for o in (edge.outcome, *(v.outcome for v in edge.variants)):
        if o.kind == "option_model_pnl":
            assert o.structure is not None
            fields: tuple[str, ...] = MODEL_PNL_FIELDS[o.structure]
        elif o.kind == "expires_otm":
            fields = EXPIRES_OTM_FIELDS
        elif o.kind == "pair_spread":
            fields = PAIR_FIELDS
        elif o.kind == "option_pnl":  # the chain grain's own fields (checked below)
            fields = ()
        elif o.kind == PORTFOLIO_KIND:
            fields = PORTFOLIO_FIELDS
        else:
            fields = MEASURE_FIELDS[o.measure or "excess_return"]
        stored = [f for f in fields if f != IMPLIED_VOL_FIELD]
        assert set(stored) <= set(OUTCOME_FIELDS), f"{edge.id}: {fields} are not outcome fields"
    fields = MEASURE_FIELDS[_measure(edge)] if edge.outcome.kind not in OWN_FIELDS else ()
    stored = [f for f in fields if f != IMPLIED_VOL_FIELD]
    assert set(stored) <= set(OUTCOME_FIELDS), f"{edge.id}: {fields} are not outcome fields"
    if edge.outcome.max_drawdown is not None:
        assert "fwd_max_drawdown" in OUTCOME_FIELDS


def test_every_model_structure_names_the_stored_fields_it_reads() -> None:
    """An ``option_model_pnl`` structure reads only fields the outcomes task writes (it adds no
    grain, ADR 0053), and every structure the document accepts has its entry."""
    assert set(MODEL_PNL_FIELDS) == set(MODEL_STRUCTURES)
    for structure, fields in MODEL_PNL_FIELDS.items():
        assert set(fields) <= set(OUTCOME_FIELDS), f"{structure}: {fields} are not outcome fields"


def test_an_option_pnl_outcome_reads_only_fields_the_chain_grain_writes() -> None:
    """``option_pnl`` adds a grain (ADR 0053 amendment, EB H13): the fields its value reads are
    the ones ``outcomes/option/structure_pnl@v1`` carries to the harness."""
    assert set(CHAIN_PNL_FIELDS) <= set(CHAIN_FIELDS)


@pytest.mark.parametrize("edge", EDGES, ids=_ids())
def test_horizons_and_benchmark_are_written_by_the_outcomes_task(edge: Edge) -> None:
    horizons, benchmarks = horizons_and_benchmarks(STORE)
    assert set(edge.outcome.horizon_sessions) <= set(horizons), f"{edge.id}: {horizons}"
    if edge.outcome.benchmark != "none" and not edge.outcome.benchmark.startswith(MIX):
        assert edge.outcome.benchmark in benchmarks  # a mix is computed from its constituents


def test_the_implied_vol_a_ratio_measure_divides_by_is_in_the_catalogue() -> None:
    field_catalog(STORE).check_field(IMPLIED_VOL_FIELD, "IMPLIED_VOL_FIELD")


@pytest.mark.parametrize("edge", EDGES, ids=_ids())
def test_every_option_outcome_iv_field_is_a_catalogue_feature_with_a_licence(edge: Edge) -> None:
    """An expires_otm outcome names the one implied-vol field it reads (iv_source and licence
    are recorded from it): it is in the catalogue and never the mixed-source field."""
    catalogue = field_catalog(STORE)
    for o in (edge.outcome, *(v.outcome for v in edge.variants)):
        if o.kind in ("expires_otm", "option_model_pnl"):
            assert o.iv_field is not None and o.iv_field not in MIXED_SOURCE_IV
            catalogue.check_field(o.iv_field, f"{edge.id} iv_field")


def test_the_pair_spread_reads_only_stored_fields_and_a_declared_text_feature() -> None:
    """A pair spread reads each leg's return from the outcomes partition (no new grain), and its
    ``pair_field`` is read at D: a catalogue feature of text type, never a hand list of ids."""
    assert set(PAIR_FIELDS) <= set(OUTCOME_FIELDS)
    kind = field_catalog(STORE).check_field("rollup.share_classes@v1.sibling_id", "pair field")
    assert kind == "str"


@pytest.mark.parametrize("edge", EDGES, ids=_ids())
def test_every_pair_field_is_a_text_catalogue_feature(edge: Edge) -> None:
    catalogue = field_catalog(STORE)
    for o in (edge.outcome, *(v.outcome for v in edge.variants)):
        if o.kind == "pair_spread":
            assert o.pair_field is not None
            assert catalogue.check_field(o.pair_field, f"{edge.id} pair_field") == "str"


@pytest.mark.parametrize("edge", EDGES, ids=_ids())
def test_every_portfolio_vol_field_is_a_catalogue_feature(edge: Edge) -> None:
    """A portfolio_return book sized by inverse volatility reads one declared feature at D."""
    for o in (edge.outcome, *(v.outcome for v in edge.variants)):
        if o.vol_field is not None:
            field_catalog(STORE).check_field(o.vol_field, f"{edge.id} vol_field")


def test_a_book_reads_only_stored_outcome_fields() -> None:
    assert set(PORTFOLIO_FIELDS) <= set(OUTCOME_FIELDS)


def _stored(field: str) -> bool:
    """Whether ``field`` is in the catalogue (its group has been added)."""
    try:
        field_catalog(STORE).check_field(field, field)
    except ConfigurationError:
        return False
    return True


@pytest.mark.parametrize("edge", EDGES, ids=_ids())
def test_the_schedule_is_one_the_harness_runs(edge: Edge) -> None:
    """The entry session S is always after the decision session D (the offset validators); a
    plain schedule gives decision sessions; an event schedule needs a declared field whose
    group is in the catalogue, else the edge waits with no screeners (earnings_reaction@v1 and
    earnings_expected@v1 arrive with ED4b and ED4e)."""
    event = edge.event_class
    trigger = market_trigger(edge.schedule)
    if trigger is not None:  # ADR 0075: a market trigger is read by the time-series harness
        assert trigger in MARKET_TRIGGERS, f"{edge.id}: {trigger!r} is not a declared trigger"
        assert edge.outcome.start_offset_sessions >= 1, f"{edge.id}: S must be after D"
        return
    if event is None:
        days = sessions_between(date(2026, 1, 2), date(2026, 3, 31))
        decision_sessions(edge.schedule, days, edge.outcome.horizon_sessions[0])
        assert edge.outcome.start_offset_sessions >= 1, f"{edge.id}: S must be after D"
        return
    if event not in ANNOUNCED_AHEAD:
        assert edge.outcome.start_offset_sessions >= 1, (
            f"{edge.id}: {event} is known when it happens"
        )
    try:  # resolved for the schedule's subtype (an 8-K item has its own count and date fields)
        spec = event_field(event, edge.event_subtype)
    except ConfigurationError:
        spec = None
    if spec is None or not all(_stored(f) for f in (spec.count, spec.date)):
        assert not edge.screeners and not edge.baselines, (
            f"{edge.id}: the field of {event} is not in the catalogue yet: no screeners until "
            "its feature group exists"
        )


@pytest.mark.parametrize("edge", EDGES, ids=_ids())
def test_the_variants_horizons_and_benchmark_are_written_by_the_outcomes_task(edge: Edge) -> None:
    horizons, benchmarks = horizons_and_benchmarks(STORE)
    for v in edge.variants:
        assert set(v.outcome.horizon_sessions) <= set(horizons), f"{edge.id}/{v.id}: {horizons}"
        assert v.outcome.benchmark in {*benchmarks, "none"}


def test_only_the_named_modules_read_outcomes() -> None:
    offenders = []
    for path in sorted((REPO_ROOT / "src/algotrade/services/evaluation").rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        names = {
            n
            for node in ast.walk(ast.parse(path.read_text()))
            for n in (
                [a.name for a in node.names] if isinstance(node, ast.Import) else
                [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            )
        }  # fmt: skip
        if rel not in (HARNESS, MEASURING, TRAINING, DISCOVERY, FORWARD, TIME_SERIES) and any(
            n == PROTECTED or n.startswith(f"{PROTECTED}.") for n in names
        ):
            offenders.append(rel)
    assert not offenders, (
        f"only {HARNESS}, {MEASURING}, {TRAINING}, {DISCOVERY}, {FORWARD}, {TIME_SERIES} may read "
        f"outcomes: "
        f"{offenders}"
    )


# Owner decision 2026-10-08 (ADR 0053 amendment): fixed, never rolling.
FROZEN_FROM = date(2026, 4, 1)


@pytest.mark.parametrize("edge", EDGES, ids=_ids())
def test_an_evidenced_or_live_edge_cites_a_run_at_its_frozen_split(edge: Edge) -> None:
    """Only a run whose split is the site's (the edge's ``frozen_from``) is evidence (ADR 0053
    amendment, ED5a): an exploratory run never moves a status."""
    if edge.status not in ("evidenced", "live"):
        return
    assert edge.evidence is not None, (
        f"{edge.id}: {edge.status} needs [evidence] run_id, split_from"
    )
    split = edge.evidence.split_from
    assert split == edge.frozen_from, f"{edge.id}: evidence split {split} != {edge.frozen_from}"


@pytest.mark.parametrize("edge", EDGES, ids=_ids())
def test_every_open_edge_names_the_decided_frozen_period(edge: Edge) -> None:
    """An open edge is judged in the one frozen period; moving it needs an ADR amendment."""
    assert edge.frozen_from == FROZEN_FROM, f"{edge.id}: frozen_from must be {FROZEN_FROM}"


def test_the_vrp_earnings_exclusion_keeps_etfs_and_clears_the_whole_window() -> None:
    """The window ends D + offset + horizon, the expected date is read at D: the threshold is
    that many sessions, and an ETF (no earnings rows: UNKNOWN) is not dropped by the filter."""
    edge = next(e for e in load_edges(STORE) if e.id == "vrp_short_premium")
    variant = next(v for v in edge.variants if v.id == "no_earnings")
    text = repr(variant.universe)
    window = max(edge.outcome.horizon_sessions) + edge.outcome.start_offset_sessions
    assert window == 32 and f"value={window}" in text.replace(" ", "")
    assert "'ETF'" in text and "UNKNOWN" in text
