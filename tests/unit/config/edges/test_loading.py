"""``load_edges`` (ADR 0053 decision 1, ADR 0015 layering), and the fitness test over the
shipped ``config/site/edges/*.toml``: every document validates, its presets and inline fields
exist, and every edge not rejected or blocked answers all nine quality-bar questions."""

import re
from typing import Any

import pytest

from algotrade.config.edges.document import CLOSED
from algotrade.config.edges.loading import edge_problems, load_edges
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


def test_a_copy_extends_a_site_edge_under_its_own_id_and_adds_new_edges() -> None:
    site = document(status="evidenced", frozen_from="2026-01-02")
    site["evidence"] = {"run_id": "r1", "split_from": "2026-01-02"}
    over = {"extends": "drift", "screeners": ["mine"], "outcome": {"horizon_sessions": [20]}}
    idea = document(id="idea", status=None)
    configs = store(site__drift=site, alice__mine_v2=over, alice__idea=idea)
    by_id = {e.id: e for e in load_edges(configs, "alice")}
    assert set(by_id) == {"drift", "mine_v2", "idea"}  # the site edge is still there, beside it
    copy = by_id["mine_v2"]
    assert copy.extends == "drift"
    assert copy.screeners == ("mine",)  # the user's own screen counts for the user
    assert copy.outcome.horizon_sessions == (20,)  # tables merge, lists replace
    assert copy.outcome.kind == "excess_return"  # the extended document's key stays
    assert copy.status == "candidate"  # never the site's status, evidence or rejection
    assert copy.evidence is None
    assert copy.frozen_from == by_id["drift"].frozen_from  # inherited
    assert copy.site_frozen_from == by_id["drift"].frozen_from
    assert by_id["idea"].status == "candidate"  # a new edge is a candidate too
    assert by_id["drift"].screeners == ()  # the site edge is untouched
    assert [e.id for e in load_edges(configs)] == ["drift"]  # the site user sees site edges only


def test_a_copy_may_move_its_own_frozen_from_and_is_then_not_the_site_split() -> None:
    site = document(frozen_from="2026-01-02")
    copy = {"extends": "drift", "frozen_from": "2026-03-02"}
    by_id = {e.id: e for e in load_edges(store(site__drift=site, alice__moved=copy), "alice")}
    assert str(by_id["moved"].frozen_from) == "2026-03-02"
    assert str(by_id["moved"].site_frozen_from) == "2026-01-02"  # exploratory by this


def test_a_version_extends_the_users_own_copy_and_the_root_is_the_site_edge() -> None:
    configs = store(
        site__drift=document(frozen_from="2026-01-02"),
        alice__v1={"extends": "drift", "screeners": ["mine"]},
        alice__v2={"extends": "v1", "top_k": 3},
    )
    by_id = {e.id: e for e in load_edges(configs, "alice")}
    assert (by_id["v2"].screeners, by_id["v2"].top_k) == (("mine",), 3)
    assert by_id["v2"].extends == "v1"
    assert by_id["v2"].site_frozen_from == by_id["drift"].frozen_from


def test_a_follow_only_file_of_a_site_id_is_the_users_state_about_that_edge() -> None:
    follow = {"follow": {"state": "following", "since": "2026-05-04", "labels": []}}
    configs = store(site__drift=document(), alice__drift=follow)
    by_id = {e.id: e for e in load_edges(configs, "alice")}
    assert by_id["drift"].follow.state == "following"
    assert str(by_id["drift"].follow.since) == "2026-05-04"
    assert by_id["drift"].status == "candidate"  # the site's document, as is
    assert load_edges(store(site__drift=document()), "alice")[0].follow.state == "researching"


def test_follow_is_never_inherited_by_a_copy() -> None:
    configs = store(
        site__drift=document(),
        alice__drift={"follow": {"state": "following"}},
        alice__mine={"extends": "drift"},
    )
    by_id = {e.id: e for e in load_edges(configs, "alice")}
    assert (by_id["drift"].follow.state, by_id["mine"].follow.state) == ("following", "researching")


@pytest.mark.parametrize(
    ("user_doc", "message"),
    [
        ({"top_k": 2}, r"holds only \[follow\].*ignored \['top_k'\]"),
        ({"extends": "drift"}, r"holds only \[follow\].*ignored \['extends'\]"),
        ({"follow": {"state": "bogus"}}, "state"),
        ({"follow": {"labels": ["nope"]}}, r"unknown \['nope'\]"),
    ],
)
def test_a_site_edges_own_file_is_only_state_and_a_fault_in_it_is_a_problem_not_a_failed_load(
    user_doc: dict[str, Any], message: str
) -> None:
    configs = store(site__drift=document(), alice__drift=user_doc)
    assert [e.id for e in load_edges(configs, "alice")] == ["drift"]  # the site edge stays
    assert re.search(message, edge_problems(configs, "alice")["drift"])


@pytest.mark.parametrize(
    ("user_doc", "message"),
    [
        ({"extends": "drift", "status": "live"}, "status: a user's edge is a 'candidate'"),
        (
            {"extends": "drift", "evidence": {"run_id": "r", "split_from": "2026-04-01"}},
            r"\['evidence'\] are the site's to set",
        ),
        ({"extends": "drift", "rejection_reason": "Back."}, r"\['rejection_reason'\] are the"),
        ({"extends": "ghost"}, "extends: no edge 'ghost'"),
        ({"extends": "mine"}, "makes a cycle"),
        ({"extends": "drift", "top_k": 0}, r"mine\.toml top_k"),
    ],
)
def test_a_faulty_copy_is_left_out_with_its_reason_and_the_other_edges_load(
    user_doc: dict[str, Any], message: str
) -> None:
    configs = store(site__drift=document(), alice__mine=user_doc, alice__fine={"extends": "drift"})
    assert [e.id for e in load_edges(configs, "alice")] == ["drift", "fine"]
    assert re.search(message, edge_problems(configs, "alice")["mine"])


def test_extends_cycles_between_two_copies_are_isolated() -> None:
    configs = store(site__drift=document(), alice__a={"extends": "b"}, alice__b={"extends": "a"})
    assert [e.id for e in load_edges(configs, "alice")] == ["drift"]
    assert set(edge_problems(configs, "alice")) == {"a", "b"}


def test_a_new_edge_is_only_a_candidate() -> None:
    configs = store(alice__idea=document(id="idea", status="evidenced"))
    assert load_edges(configs, "alice") == ()
    assert "a user's edge is a 'candidate'" in edge_problems(configs, "alice")["idea"]


def test_the_site_publishing_a_users_copy_by_its_id_keeps_all_their_edges() -> None:
    """The publish path: the site gets an edge under the copy's id; the user's file of that id
    becomes their state about it, and their other edges still load."""
    mine = {"extends": "drift", "top_k": 3, "follow": {"state": "following"}}
    before = store(site__drift=document(), alice__mine=mine, alice__other={"extends": "mine"})
    assert [e.id for e in load_edges(before, "alice")] == ["drift", "mine", "other"]
    after = store(
        site__drift=document(),
        site__mine=document(id="mine", top_k=3),
        alice__mine=mine,
        alice__other={"extends": "mine"},
    )
    by_id = {e.id: e for e in load_edges(after, "alice")}
    assert set(by_id) == {"drift", "mine", "other"}
    assert by_id["mine"].follow.state == "following" and by_id["mine"].extends is None
    assert by_id["other"].extends == "mine"
    assert "the site now has an edge 'mine'" in edge_problems(after, "alice")["mine"]


def test_the_site_removing_the_parent_of_a_copy_isolates_that_copy_only() -> None:
    configs = store(site__keep=document(id="keep"), alice__mine={"extends": "drift"},
                    alice__fine={"extends": "keep"})  # fmt: skip
    assert [e.id for e in load_edges(configs, "alice")] == ["fine", "keep"]
    assert "extends: no edge 'drift'" in edge_problems(configs, "alice")["mine"]


def test_with_a_catalog_inline_universe_fields_must_exist() -> None:
    rule = {"field": "feature.no_such_field", "op": "eq", "value": 1}
    configs = store(site__drift=document(universe={"where": {"all": [rule]}}))
    assert load_edges(configs)[0].id == "drift"  # shape only without a catalogue
    with pytest.raises(ConfigurationError, match=r"drift\.toml universe"):
        load_edges(configs, catalog=field_catalog(SHIPPED))


def test_an_invalid_user_layer_names_the_user_file() -> None:
    configs = store(site__drift=document(), alice__mine={"extends": "drift", "top_k": 0})
    assert "config/users/alice/edges/mine.toml top_k" in edge_problems(configs, "alice")["mine"]


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
    edges = load_edges(SHIPPED, catalog=field_catalog(SHIPPED))
    assert any(isinstance(e.universe, Selection) for e in edges)
