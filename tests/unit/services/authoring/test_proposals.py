"""A study's proposed edge written as a user's configs (ED6 W5): its screens finalised, the edge
``researching`` with the ``proposed_by_study`` label (never a candidate: the owner moves it),
read back as the harness reads it, and nothing left behind when any part is refused."""

import tomllib
from datetime import date
from typing import Any

import pytest

from algotrade.config.edges.follow import PROPOSED_BY_STUDY
from algotrade.config.edges.loading import RULE_SCREENS, edge_problems, load_edges
from algotrade.config.user import UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.authoring import edges
from algotrade.services.authoring.proposals import save_proposal
from algotrade.services.authoring.scope import ConflictError
from algotrade.services.configs import nightly_screeners, resolve_rule_draft
from algotrade.services.evaluation.discovery.drafts import (
    PROPOSAL_BASELINES,
    PROPOSAL_UNIVERSE,
    edge_proposal,
)
from algotrade.storage.configs.files import FileConfigStore
from algotrade.storage.configs.store import OverlayConfigStore
from algotrade.storage.configs.writer import MemoryConfigWriter
from tests.conftest import REPO_ROOT
from tests.unit.services.authoring.conftest import SELECTION

TODAY = date(2026, 11, 3)
TELLS = ("rollup.price_stats@v2.hv20", "rollup.price_stats@v2.close")


def stats(**over: Any) -> dict[str, Any]:
    return {
        "blocks": 6, "horizon_sessions": 504, "frozen_from": "2026-04-01", "benchmark": "SPY",
        "features_tested": 140, "eligible": {"min_price": 5.0, "min_adv_usd_20d": 1e6},
        "clusters": [[TELLS[0]], [TELLS[1]]],
        "tells": [
            {"feature": TELLS[0], "mean_g": 0.6, "mean_g_wl": 0.5, "sign": 1, "cluster": 0},
            {"feature": TELLS[1], "mean_g": -0.4, "mean_g_wl": -0.4, "sign": -1, "cluster": 1},
        ],
    } | over  # fmt: skip


def decoy(name: str) -> dict[str, Any]:
    price = {"field": "rollup.price_stats@v2.close", "op": "gt", "value": 3}
    return {"id": name, "kind": "screener", "impl": "rules", "version": 1} | {
        "criteria": {"price": price}
    }


@pytest.fixture
def site() -> MemoryConfigWriter:
    return MemoryConfigWriter(
        {
            ("site", "selections", "all_active"): tomllib.loads(SELECTION),
            ("site", "selections", PROPOSAL_UNIVERSE): {"name": PROPOSAL_UNIVERSE},
            **{("site", "screeners", f"{n}@1"): decoy(n) for n in PROPOSAL_BASELINES},
        }
    )


def save(writer: MemoryConfigWriter, run: str = "WS_1") -> Any:
    p = edge_proposal(run, stats())
    return save_proposal(writer, "alice", p.edge_id, p.edge, p.screens, today=TODAY)


def test_a_proposal_is_a_researching_labelled_edge_over_finalised_screens(
    site: MemoryConfigWriter,
) -> None:
    """Catches: a proposal the harness cannot run (screens missing or unloadable), or one that
    starts as a candidate (ML judging its own proposal)."""
    edge = save(site)
    assert (edge.id, edge.status) == ("ws_1", "researching")
    assert PROPOSED_BY_STUDY in edge.audit.labels and edge.audit.status_since == TODAY
    assert edge.screeners == ("ws_1_t1", "ws_1_t2") and edge.baselines == PROPOSAL_BASELINES
    assert edge.frozen_from == date(2026, 4, 1)
    assert "140 features with data searched" in edge.notes and "discovery sample" in edge.notes
    assert {e.id for e in load_edges(site, "alice")} >= {"ws_1"}
    assert [site.versions("alice", s) for s in edge.screeners] == [[1], [1]]
    run = {r.config.id for r in nightly_screeners(site)}
    assert {"ws_1_t1", "ws_1_t2"} <= run  # finalised: on the nightly like any user screen


def test_a_second_proposal_of_the_same_run_is_refused_and_writes_nothing(
    site: MemoryConfigWriter,
) -> None:
    save(site)
    before = site.load("alice", "edges", "ws_1")
    with pytest.raises(ConflictError):
        save(site)
    assert site.load("alice", "edges", "ws_1") == before


def test_a_refused_edge_writes_nothing_and_the_run_can_be_proposed_again(
    site: MemoryConfigWriter,
) -> None:
    """Catches: screens finalised onto the nightly for an edge that was never written, and a
    refusal that archives them, so the run's screen names are burnt and every retry is refused."""
    p = edge_proposal("WS_2", stats())
    with pytest.raises(ConfigurationError):
        save_proposal(site, "alice", p.edge_id, p.edge | {"top_k": "many"}, p.screens, today=TODAY)
    assert all(not site.versions("alice", s) for s in p.screens)
    assert all(site.draft("alice", s) is None for s in p.screens)
    assert site.load("alice", "edges", p.edge_id) is None
    edge = save_proposal(site, "alice", p.edge_id, p.edge, p.screens, today=TODAY)
    assert edge.screeners == tuple(p.screens)


def test_an_invalid_screen_is_refused_before_anything_is_written(site: MemoryConfigWriter) -> None:
    p = edge_proposal("WS_3", stats())
    bad = {n: d | {"rank": {"tie_break": "rollup.nope@v1.x"}} for n, d in p.screens.items()}
    with pytest.raises(ConfigurationError):
        save_proposal(site, "alice", p.edge_id, p.edge, bad, today=TODAY)
    assert all(site.draft("alice", n) is None and not site.versions("alice", n) for n in bad)


def test_a_proposed_edge_never_sets_its_own_status(site: MemoryConfigWriter) -> None:
    """Fitness: a study's proposal is never saved as a candidate (ADR 0053: ML proposes, never
    judges); moving it is the owner's ``set_status``."""
    p = edge_proposal("WS_4", stats())
    for extra in ({"status": "candidate"}, {"audit": {"labels": []}}):
        with pytest.raises(ConfigurationError, match="sets no status"):
            edges.save_proposed_edge(site, "alice", "x", p.edge | extra, today=TODAY)


def test_the_proposal_loads_against_the_shipped_site_config() -> None:
    """Fitness: a proposal's universe, decoy baselines and screen fields exist in config/site.
    Catches: a renamed selection or decoy (or a gate field) breaking ``draft-edges`` silently."""
    p = edge_proposal("WS_9", stats())
    shipped = FileConfigStore(REPO_ROOT / "config", local=False)
    pending = {("alice", RULE_SCREENS, n): d for n, d in p.screens.items()}
    for name, doc in p.screens.items():
        resolve_rule_draft(shipped, name, UserContext("alice"), doc | {"id": name, "version": 1})
    edge = p.edge | {"audit": {"status_since": TODAY, "labels": [PROPOSED_BY_STUDY]}}
    store = OverlayConfigStore(shipped, pending | {("alice", "edges", p.edge_id): edge})
    found = {e.id: e for e in load_edges(store, "alice")}
    assert p.edge_id in found, edge_problems(store, "alice")
    assert found[p.edge_id].baselines == PROPOSAL_BASELINES
