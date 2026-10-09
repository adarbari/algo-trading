"""A user's edges (ADR 0053 amendment 2026-10-09): copy, save, delete, state and the published
document; each write read back through the layering the harness reads (``load_edges``)."""

from datetime import UTC, date, datetime
from typing import Any

import pytest

from algotrade.config.edges.loading import load_edges
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.authoring import edges
from algotrade.services.authoring.edges import StateChange
from algotrade.services.authoring.scope import ConflictError, EdgeNotFoundError
from algotrade.storage.configs.writer import MemoryConfigWriter
from tests.unit.config.edges.test_document import document

TODAY = date(2026, 10, 9)


@pytest.fixture
def writer() -> MemoryConfigWriter:
    return MemoryConfigWriter(
        {
            ("site", "selections", "liquid_optionable"): {"name": "liquid_optionable"},
            ("site", "screeners", "vrp@1"): {"id": "vrp", "impl": "rules"},
            ("site", "edges", "drift"): document(status="evidenced", frozen_from="2026-01-02")
            | {"evidence": {"run_id": "r1", "split_from": "2026-01-02"}},
        }
    )


def seen(writer: MemoryConfigWriter, user: str = "alice") -> dict[str, Any]:
    return {e.id: e for e in load_edges(writer, user)}


def test_a_copy_is_a_new_document_that_extends_and_leaves_the_site_edge_alone(
    writer: MemoryConfigWriter,
) -> None:
    assert edges.copy_edge(writer, "alice", "drift", "mine", today=TODAY) == {"extends": "drift"}
    assert writer.load("alice", "edges", "mine") == {"extends": "drift"}
    assert set(seen(writer)) == {"drift", "mine"}
    assert seen(writer)["mine"].extends == "drift"
    assert writer.load("site", "edges", "drift")["status"] == "evidenced"
    assert "mine" not in seen(writer, "bob")  # per user


def test_a_copy_of_a_copy_extends_the_users_own_edge(writer: MemoryConfigWriter) -> None:
    edges.copy_edge(writer, "alice", "drift", "mine", today=TODAY)
    edges.copy_edge(writer, "alice", "mine", "mine_two", today=TODAY)
    assert seen(writer)["mine_two"].extends == "mine"
    assert seen(writer)["mine_two"].site_frozen_from == seen(writer)["drift"].frozen_from


def test_a_new_version_is_a_trial_that_replaces_the_edge(writer: MemoryConfigWriter) -> None:
    edges.copy_edge(writer, "alice", "drift", "drift_v2", today=TODAY, as_version=True)
    follow = seen(writer)["drift_v2"].follow
    assert (follow.state, follow.replaces, follow.since) == ("trial", "drift", TODAY)


@pytest.mark.parametrize(
    ("source", "new", "error"),
    [
        ("ghost", "mine", EdgeNotFoundError),
        ("drift", "drift", ConflictError),  # a site id is taken
        ("drift", "Bad Id", ConfigurationError),
    ],
)
def test_a_copy_needs_a_visible_source_and_a_free_valid_id(
    writer: MemoryConfigWriter, source: str, new: str, error: type[Exception]
) -> None:
    with pytest.raises(error):
        edges.copy_edge(writer, "alice", source, new, today=TODAY)
    assert writer.names("alice", "edges") == []


def test_saving_validates_as_the_harness_reads_it_and_writes_nothing_on_a_clash(
    writer: MemoryConfigWriter,
) -> None:
    edges.copy_edge(writer, "alice", "drift", "mine", today=TODAY)
    saved = edges.save_edge(
        writer, "alice", "mine", {"extends": "drift", "screeners": ["vrp"], "top_k": 3}
    )
    assert saved == {"extends": "drift", "screeners": ["vrp"], "top_k": 3}
    assert seen(writer)["mine"].top_k == 3
    for bad, message in (
        ({"extends": "drift", "screeners": ["nope"]}, "no screener preset named"),
        ({"extends": "drift", "top_k": 0}, "top_k"),
        ({"extends": "drift", "status": "live"}, "status"),
    ):
        with pytest.raises(ConfigurationError, match=message):
            edges.save_edge(writer, "alice", "mine", bad)
        assert writer.load("alice", "edges", "mine") == saved  # nothing was written


def test_saving_creates_a_new_edge_and_never_a_site_edges_id(writer: MemoryConfigWriter) -> None:
    edges.save_edge(writer, "alice", "idea", document(id="idea", status=None))
    assert seen(writer)["idea"].status == "candidate"
    with pytest.raises(ConflictError, match="site edge"):
        edges.save_edge(writer, "alice", "drift", {"top_k": 2})
    with pytest.raises(ConflictError, match="site edge"):
        edges.save_edge(writer, "alice", "drift", {"extends": "drift"})


def test_saving_keeps_the_follow_table_and_ignores_one_in_the_body(
    writer: MemoryConfigWriter,
) -> None:
    edges.copy_edge(writer, "alice", "drift", "mine", today=TODAY)
    edges.set_state(writer, "alice", "mine", StateChange("following"), today=TODAY)
    edges.save_edge(writer, "alice", "mine", {"extends": "drift", "follow": {"state": "rejected"}})
    assert seen(writer)["mine"].follow.state == "following"


def test_moving_the_split_after_viewing_the_result_is_labelled_for_good(
    writer: MemoryConfigWriter,
) -> None:
    edges.copy_edge(writer, "alice", "drift", "mine", today=TODAY)
    edges.set_state(writer, "alice", "mine", StateChange(reveal_oos=True), today=TODAY)
    edges.save_edge(writer, "alice", "mine", {"extends": "drift", "top_k": 2})
    assert "split_moved_after_viewing" not in seen(writer)["mine"].follow.labels
    edges.save_edge(writer, "alice", "mine", {"extends": "drift", "frozen_from": "2026-03-02"})
    assert "split_moved_after_viewing" in seen(writer)["mine"].follow.labels
    edges.save_edge(writer, "alice", "mine", {"extends": "drift"})  # moving it back: stays
    assert "split_moved_after_viewing" in seen(writer)["mine"].follow.labels


def test_delete_archives_the_edge_and_its_id_is_not_reused(writer: MemoryConfigWriter) -> None:
    edges.copy_edge(writer, "alice", "drift", "mine", today=TODAY)
    edges.delete_edge(writer, "alice", "mine", datetime(2026, 10, 9, tzinfo=UTC))
    assert "mine" not in seen(writer)
    assert len(writer.archived_documents) == 1
    with pytest.raises(ConflictError, match="deleted edge"):
        edges.copy_edge(writer, "alice", "drift", "mine", today=TODAY)
    with pytest.raises(EdgeNotFoundError):
        edges.delete_edge(writer, "alice", "mine")


def test_an_edge_another_extends_is_not_deleted(writer: MemoryConfigWriter) -> None:
    edges.copy_edge(writer, "alice", "drift", "mine", today=TODAY)
    edges.copy_edge(writer, "alice", "mine", "mine_two", today=TODAY)
    with pytest.raises(ConflictError, match="extended by"):
        edges.delete_edge(writer, "alice", "mine")


def test_the_state_of_a_site_edge_is_a_file_holding_only_follow(
    writer: MemoryConfigWriter,
) -> None:
    follow = edges.set_state(writer, "alice", "drift", StateChange("following"), today=TODAY)
    assert (follow.state, follow.since) == ("following", TODAY)
    assert set(writer.load("alice", "edges", "drift") or {}) == {"follow"}
    assert seen(writer, "bob")["drift"].follow.state == "researching"
    edges.set_state(
        writer, "alice", "drift", StateChange("retired", "stopped working"), today=TODAY
    )
    assert seen(writer)["drift"].follow.reason == "stopped working"


@pytest.mark.parametrize(
    ("start", "to", "ok"),
    [
        ("researching", "following", True),
        ("researching", "retired", False),
        ("following", "retired", True),
        ("following", "rejected", False),
        ("retired", "following", False),
        ("rejected", "researching", True),
        ("rejected", "following", False),
    ],
)
def test_state_transitions(writer: MemoryConfigWriter, start: str, to: str, ok: bool) -> None:
    writer.save_user_document(
        "alice", "edges", "drift", {"follow": {"state": start, "reason": "why"}}
    )
    change = StateChange(to, "because")
    if ok:
        assert edges.set_state(writer, "alice", "drift", change, today=TODAY).state == to
    else:
        with pytest.raises(ConfigurationError, match="cannot go from"):
            edges.set_state(writer, "alice", "drift", change, today=TODAY)


def test_rejecting_needs_a_reason(writer: MemoryConfigWriter) -> None:
    with pytest.raises(ConfigurationError, match="needs a reason"):
        edges.set_state(writer, "alice", "drift", StateChange("rejected"), today=TODAY)
    done = edges.set_state(
        writer, "alice", "drift", StateChange("rejected", " no\n edge "), today=TODAY
    )
    assert (done.state, done.reason) == ("rejected", "no edge")


def test_following_against_the_verdict_is_labelled_not_blocked(writer: MemoryConfigWriter) -> None:
    done = edges.set_state(
        writer, "alice", "drift", StateChange("following"), today=TODAY, verdict="not_working"
    )
    assert done.state == "following"
    assert done.labels == ("followed_against_verdict",)
    clean = edges.set_state(
        writer, "bob", "drift", StateChange("following"), today=TODAY, verdict="promising"
    )
    assert clean.labels == ()


def test_revealing_out_of_sample_while_tuning_is_labelled_but_following_is_not(
    writer: MemoryConfigWriter,
) -> None:
    edges.copy_edge(writer, "alice", "drift", "mine", today=TODAY)
    edges.copy_edge(writer, "alice", "drift", "kept", today=TODAY)
    tuning = edges.set_state(writer, "alice", "mine", StateChange(reveal_oos=True), today=TODAY)
    assert (tuning.oos_revealed, tuning.labels) == (True, ("oos_viewed_during_tuning",))
    following = edges.set_state(writer, "alice", "kept", StateChange("following"), today=TODAY)
    assert (following.oos_revealed, following.labels) == (True, ())  # following shows it too


def test_replacing_retires_the_followed_edge_and_early_replacing_is_labelled(
    writer: MemoryConfigWriter,
) -> None:
    edges.set_state(writer, "alice", "drift", StateChange("following"), today=date(2026, 6, 1))
    edges.copy_edge(writer, "alice", "drift", "drift_v2", today=date(2026, 10, 1), as_version=True)
    done = edges.set_state(writer, "alice", "drift_v2", StateChange("following"), today=TODAY)
    assert done.labels == ("replaced_without_forward_test",)  # a week, not 20 sessions
    old = seen(writer)["drift"].follow
    assert (old.state, old.reason) == ("retired", "replaced by a new version")


def test_replacing_after_the_forward_test_carries_no_label(writer: MemoryConfigWriter) -> None:
    edges.set_state(writer, "alice", "drift", StateChange("following"), today=date(2026, 6, 1))
    edges.copy_edge(writer, "alice", "drift", "drift_v2", today=date(2026, 8, 3), as_version=True)
    done = edges.set_state(writer, "alice", "drift_v2", StateChange("following"), today=TODAY)
    assert done.labels == ()


def test_a_failed_second_write_never_leaves_two_versions_following(
    writer: MemoryConfigWriter, monkeypatch: pytest.MonkeyPatch
) -> None:
    edges.set_state(writer, "alice", "drift", StateChange("following"), today=date(2026, 6, 1))
    edges.copy_edge(writer, "alice", "drift", "drift_v2", today=date(2026, 8, 3), as_version=True)
    real = writer.save_user_document
    calls: list[str] = []

    def failing(user: str, kind: str, name: str, document: Any) -> None:
        calls.append(name)
        if name == "drift_v2":  # the follow of the new version is the second write
            raise OSError("disk full")
        real(user, kind, name, document)

    monkeypatch.setattr(writer, "save_user_document", failing)
    with pytest.raises(OSError):
        edges.set_state(writer, "alice", "drift_v2", StateChange("following"), today=TODAY)
    assert calls == ["drift", "drift_v2"]  # the old version is retired first
    following = [e.id for e in seen(writer).values() if e.follow.state == "following"]
    assert following == []  # a trial and a retired edge: never two following


def test_a_save_that_would_break_an_edge_extending_it_is_refused(
    writer: MemoryConfigWriter,
) -> None:
    edges.save_edge(writer, "alice", "v1", {"extends": "drift", "top_k": 2})
    edges.save_edge(writer, "alice", "v2", {"extends": "v1", "base": "event"})
    before = writer.load("alice", "edges", "v1")
    with pytest.raises(ConfigurationError, match=r"would break \['v2'\]"):
        edges.save_edge(writer, "alice", "v1", {"extends": "drift", "schedule": "every_session"})
    assert writer.load("alice", "edges", "v1") == before
    assert "v2" in seen(writer)
