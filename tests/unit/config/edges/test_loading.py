"""``load_edges`` (ADR 0053 decision 1, ADR 0015 layering), and the fitness test over the
shipped ``config/site/edges/*.toml``: every document validates, its presets and inline fields
exist, and every edge not rejected or blocked answers all nine quality-bar questions."""

from typing import Any

import pytest

from algotrade.config.edges.document import CLOSED
from algotrade.config.edges.loading import load_edges
from algotrade.config.strategy.schema import Selection
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.configs import field_catalog
from algotrade.storage.configs.files import FileConfigStore, MemoryConfigStore
from tests.conftest import REPO_ROOT
from tests.unit.config.edges.test_document import document

PRESETS: dict[tuple[str, str, str], dict[str, Any]] = {
    ("site", "selections", "liquid_optionable"): {"name": "liquid_optionable"},
    ("site", "screeners", "vrp_scanner@1"): {"id": "vrp_scanner", "impl": "rules"},
    ("site", "strategies", "short_premium"): {"id": "short_premium", "kind": "screener"},
    ("site", "strategies", "sma_trend"): {"id": "sma_trend", "kind": "strategy"},
    ("alice", "screeners", "mine@1"): {"id": "mine", "impl": "rules"},
}


def store(**docs: dict[str, Any]) -> MemoryConfigStore:
    """``PRESETS`` plus edge documents keyed ``<scope>__<id>``."""
    edges = {(k.split("__")[0], "edges", k.split("__")[1]): v for k, v in docs.items()}
    return MemoryConfigStore({**PRESETS, **edges})


def test_no_files_no_edges() -> None:
    assert load_edges(MemoryConfigStore({})) == ()


def test_screeners_name_rule_screens_and_python_screeners() -> None:
    doc = document(screeners=["vrp_scanner", "short_premium"])
    (edge,) = load_edges(store(site__drift=doc))
    assert edge.screeners == ("vrp_scanner", "short_premium")


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"screeners": ["sma_trend"]}, "screeners: no screener preset named \\['sma_trend'\\]"),
        ({"baselines": ["momentum_12_1"]}, "baselines: no screener preset named"),
        ({"screeners": ["mine"]}, "screeners: no screener preset named \\['mine'\\]"),
        ({"universe": "everything"}, "universe: no selection preset named 'everything'"),
    ],
)
def test_presets_that_do_not_exist_fail_with_the_file(
    changes: dict[str, Any], message: str
) -> None:
    with pytest.raises(ConfigurationError, match=message) as caught:
        load_edges(store(site__drift=document(**changes)))
    assert "config/site/edges/drift.toml" in str(caught.value)


def test_a_user_document_layers_over_the_site_and_adds_drafts() -> None:
    site = document()
    over = {"screeners": ["mine"], "outcome": {"horizon_sessions": [20]}}
    draft = document(id="idea", status="candidate")
    configs = store(site__drift=site, alice__drift=over, alice__idea=draft)
    by_id = {e.id: e for e in load_edges(configs, "alice")}
    assert by_id["drift"].screeners == ("mine",)  # the user's own screen counts for the user
    assert by_id["drift"].outcome.horizon_sessions == (20,)  # tables merge, lists replace
    assert by_id["drift"].outcome.kind == "excess_return"  # the site's key stays
    assert set(by_id) == {"drift", "idea"}
    site_only = load_edges(configs)
    assert [e.id for e in site_only] == ["drift"]
    assert site_only[0].screeners == ()


def test_an_invalid_user_layer_names_the_user_file() -> None:
    configs = store(site__drift=document(), alice__drift={"status": "maybe"})
    with pytest.raises(ConfigurationError, match=r"config/users/alice/edges/drift\.toml status"):
        load_edges(configs, "alice")


# ----------------------------------------------------------------------------- fitness


SHIPPED = FileConfigStore(REPO_ROOT / "config", local=False)


def test_every_shipped_edge_document_validates() -> None:
    edges = load_edges(SHIPPED)
    names = SHIPPED.names("site", "edges")
    assert [e.id for e in edges] == names  # every file loads, none is skipped
    assert {"vrp_short_premium", "sp500_index_changes", "russell_reconstitution"} <= set(names)


def test_every_open_shipped_edge_answers_the_whole_quality_bar() -> None:
    unanswered = [
        f"{e.id}: {key}"
        for e in load_edges(SHIPPED)
        if e.status not in CLOSED
        for key, answer in e.answers
        if not answer.strip()
    ]
    assert not unanswered, f"answer every quality-bar question (docs/edges-plan.md): {unanswered}"


def test_every_shipped_inline_universe_names_catalogue_fields() -> None:
    catalog = field_catalog(SHIPPED)
    for edge in load_edges(SHIPPED):
        if isinstance(edge.universe, Selection):
            catalog.check(edge.universe.where, f"config/site/edges/{edge.id}.toml universe")
