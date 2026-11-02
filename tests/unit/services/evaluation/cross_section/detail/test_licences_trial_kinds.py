"""The trial licence contract (ADR 0028, ADR 0088 decisions 12 and 20): every trial kind the
harness runs (a cross-section screener, a time-series window, a named option sleeve's (edge
variant, symbol)) records its licence through the one computation (``trial_licences``), and a
personal input (an outcome row, a gate field, a schedule's field) makes the trial and its evidence
licence personal, so the evidence gate hides the setup from a viewer without the licence."""

from collections.abc import Callable
from typing import Any

import pytest

from algotrade.config.edges.document import Edge
from algotrade.config.strategy.schema import parse_selection
from algotrade.config.user import UserContext
from algotrade.services.evaluation.cross_section.detail.licences import (
    rule_fields,
    trial_licences,
)
from algotrade.services.evaluation.cross_section.harness import evaluate_edge
from algotrade.services.evaluation.cross_section.results import edge_eval_frame
from algotrade.services.evaluation.cross_section.run.evaluation import EdgeEvaluation
from algotrade.services.features import catalogue
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.result_writer import ResultWriter
from tests.unit.services.evaluation.cross_section import conftest as cross
from tests.unit.services.evaluation.time_series import conftest as series
from tests.unit.services.evaluation.time_series import test_sleeve as sleeves

VIX_PCT = "market.market_conditions@v2.vix_pct_252"  # personal: VIX-derived (ADR 0028)
OPEN_GATE = "market.market_conditions@v2.sessions_to_fomc"  # open
USER = UserContext("site")


def gate(field: str) -> dict[str, Any]:
    return {"all": [{"field": field, "op": "gt", "value": 0.5}]}


def cross_section(personal: bool) -> EdgeEvaluation:
    w = cross.build_world()
    e = cross.edge(gate=gate(VIX_PCT if personal else OPEN_GATE))
    return evaluate_edge(w.reader, w.results, w.configs, USER, e, cross.DAYS[0], cross.DAYS[-1],
                         cross.AS_OF)  # fmt: skip


def time_series(personal: bool) -> EdgeEvaluation:
    w = series.build_world()
    e = series.timed_edge(gate=gate(VIX_PCT if personal else OPEN_GATE))
    return evaluate_edge(w.reader, w.results, w.configs, USER, e, series.FIRST, series.LAST,
                         series.AS_OF)  # fmt: skip


def sleeve(personal: bool) -> EdgeEvaluation:
    """The sleeve's trades priced from the bought history (personal rows) or from the Cboe
    chains (open rows): the option chain source's licence, recorded per row."""
    e = sleeves.sleeve_edge()
    cboe = {"price_source": "cboe", "licence": "open"}
    changes = {} if personal else {(v, s): cboe for v in sleeves.PNL for _, s in sleeves.entries(e)}
    reader = sleeves.world(e, changes=changes)
    key = ("site", sleeves.KIND, sleeves.NAME)  # the site's position templates
    configs = MemoryConfigStore({key: sleeves.SITE.load(*key)})
    return evaluate_edge(reader, ResultWriter(MemoryBackend()), configs, USER, e, sleeves.FIRST,
                         sleeves.LAST, sleeves.AS_OF)  # fmt: skip


KINDS: dict[str, Callable[[bool], EdgeEvaluation]] = {
    "cross_section": cross_section,
    "time_series": time_series,
    "sleeve": sleeve,
}


@pytest.mark.parametrize("kind", sorted(KINDS))
def test_every_trial_kind_records_a_licence_and_a_personal_input_makes_it_personal(
    kind: str,
) -> None:
    for personal, expected in ((False, "open"), (True, "personal")):
        ev = KINDS[kind](personal)
        assert ev.results
        assert all(r.licences is not None for r in ev.results), kind  # never unrecorded
        trials = {(r.licence, r.licences.evidence) for r in ev.results if r.licences}
        assert trials == {(expected, expected)}, (kind, personal)
        frame = edge_eval_frame(ev, "r", series.AS_OF)
        assert set(frame["licence"].dropna()) == {expected}
        assert set(frame["evidence_licence"].dropna()) == {expected}  # what the gate reads


def test_a_personal_market_trigger_makes_a_time_series_trial_and_its_evidence_personal() -> None:
    """``on_market:vix_spike`` places its windows from the personal VIX trigger dates."""
    triggered: Edge = series.timed_edge(schedule="on_market:vix_spike")
    timed: Edge = series.timed_edge()
    features = catalogue(MemoryConfigStore({}), "site")
    assert set(rule_fields(triggered)) == {
        "market.market_triggers@v2.vix_spike_date",
        "market.market_triggers@v2.sessions_since_vix_spike",
    }
    found = trial_licences(features, triggered, triggered.universe, [], None)  # type: ignore[arg-type]
    assert (found.trial, found.rules, found.evidence) == ("personal",) * 3
    plain = trial_licences(features, timed, timed.universe, [], None)  # type: ignore[arg-type]
    assert (plain.trial, plain.evidence) == ("open", "open")


def test_a_rule_licence_reaches_the_evidence_and_a_screen_field_does_not() -> None:
    """Decision 20 and decision B: a rule's personal field hides the setup (its evidence is
    personal); a screener's or universe's stays under per-column redaction (evidence open)."""
    e = cross.edge(gate=gate(VIX_PCT))
    features = catalogue(MemoryConfigStore({}), "site")
    universe = parse_selection(cross.ACTIVE, "active")
    ruled = trial_licences(features, e, universe, [], None)
    assert (ruled.trial, ruled.outcome, ruled.evidence) == ("personal", "open", "personal")
    scored = trial_licences(features, cross.edge(), universe, [], "personal")
    assert (scored.trial, scored.evidence) == ("personal", "open")
