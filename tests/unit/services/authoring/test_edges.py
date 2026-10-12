"""A user's edges (ADR 0053 amendment 2026-10-10): copy, save, delete, status, bookmark and the
published document; each write read back through the layering the harness reads (``load_edges``)."""

from datetime import UTC, date, datetime
from typing import Any

import pytest

from algotrade.config.edges.loading import load_edges
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.authoring import edges
from algotrade.services.authoring.edges import StatusChange
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


def test_a_new_version_is_a_candidate_that_replaces_the_edge(writer: MemoryConfigWriter) -> None:
    edges.copy_edge(writer, "alice", "drift", "drift_v2", today=TODAY, as_version=True)
    v2 = seen(writer)["drift_v2"]
    assert (v2.status, v2.audit.replaces, v2.audit.status_since) == ("candidate", "drift", TODAY)


def test_a_copy_starts_researching(writer: MemoryConfigWriter) -> None:
    edges.copy_edge(writer, "alice", "drift", "mine", today=TODAY)
    assert seen(writer)["mine"].status == "researching"


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
        ({"extends": "drift", "follow": {"since": "2026-10-01"}}, r"no \[follow\] table"),
    ):
        with pytest.raises(ConfigurationError, match=message):
            edges.save_edge(writer, "alice", "mine", bad)
        assert writer.load("alice", "edges", "mine") == saved  # nothing was written


def test_saving_creates_a_new_edge_and_never_a_site_edges_id(writer: MemoryConfigWriter) -> None:
    edges.save_edge(writer, "alice", "idea", document(id="idea", status=None))
    assert seen(writer)["idea"].status == "researching"
    with pytest.raises(ConflictError, match="site edge"):
        edges.save_edge(writer, "alice", "drift", {"top_k": 2})
    with pytest.raises(ConflictError, match="site edge"):
        edges.save_edge(writer, "alice", "drift", {"extends": "drift"})


def test_saving_keeps_the_status_and_its_audit_whatever_the_body_says(
    writer: MemoryConfigWriter,
) -> None:
    edges.copy_edge(writer, "alice", "drift", "mine", today=TODAY)
    edges.set_status(writer, "alice", "mine", StatusChange("candidate"), today=TODAY)
    edges.save_edge(
        writer,
        "alice",
        "mine",
        {"extends": "drift", "status": "live", "audit": {"status_reason": "forged"}},
    )
    mine = seen(writer)["mine"]
    assert (mine.status, mine.audit.status_since, mine.audit.status_reason) == (
        "candidate", TODAY, "",
    )  # fmt: skip


def test_moving_the_split_after_viewing_the_result_is_labelled_for_good(
    writer: MemoryConfigWriter,
) -> None:
    edges.copy_edge(writer, "alice", "drift", "mine", today=TODAY)
    edges.set_status(writer, "alice", "mine", StatusChange(reveal_oos=True), today=TODAY)
    edges.save_edge(writer, "alice", "mine", {"extends": "drift", "top_k": 2})
    assert "split_moved_after_viewing" not in seen(writer)["mine"].audit.labels
    edges.save_edge(writer, "alice", "mine", {"extends": "drift", "frozen_from": "2026-03-02"})
    assert "split_moved_after_viewing" in seen(writer)["mine"].audit.labels
    edges.save_edge(writer, "alice", "mine", {"extends": "drift"})  # moving it back: stays
    assert "split_moved_after_viewing" in seen(writer)["mine"].audit.labels


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


def test_following_a_site_edge_is_a_file_holding_only_follow(writer: MemoryConfigWriter) -> None:
    done = edges.set_status(writer, "alice", "drift", StatusChange(follow=True), today=TODAY)
    assert (done.followed, done.follow.since, done.status) == (True, TODAY, "evidenced")
    assert writer.load("alice", "edges", "drift") == {"follow": {"since": TODAY}}
    assert not seen(writer, "bob")["drift"].followed
    again = edges.set_status(
        writer, "alice", "drift", StatusChange(follow=True), today=date(2026, 10, 12)
    )
    assert again.follow.since == TODAY  # restating keeps the date
    gone = edges.set_status(writer, "alice", "drift", StatusChange(follow=False), today=TODAY)
    assert not gone.followed and writer.load("alice", "edges", "drift") is None
    assert len(writer.archived_documents) == 1  # archived, never erased


def test_a_site_edge_has_the_sites_status_and_an_own_edge_is_not_followed(
    writer: MemoryConfigWriter,
) -> None:
    with pytest.raises(ConfigurationError, match="site's status"):
        edges.set_status(writer, "alice", "drift", StatusChange("live"), today=TODAY)
    edges.copy_edge(writer, "alice", "drift", "mine", today=TODAY)
    with pytest.raises(ConfigurationError, match="only a site edge is followed"):
        edges.set_status(writer, "alice", "mine", StatusChange(follow=True), today=TODAY)


def mine(writer: MemoryConfigWriter, status: str = "researching") -> None:
    """The user's own edge ``mine`` at ``status`` (the allowed moves to it are skipped)."""
    edges.copy_edge(writer, "alice", "drift", "mine", today=TODAY)
    doc = dict(writer.load("alice", "edges", "mine") or {})
    writer.save_user_document(
        "alice", "edges", "mine", {**doc, "status": status, "audit": {"status_reason": "why"}}
    )


@pytest.mark.parametrize(
    ("start", "to", "ok"),
    [
        ("researching", "candidate", True),
        ("researching", "live", False),
        ("researching", "retired", False),
        ("candidate", "live", True),
        ("candidate", "rejected", True),
        ("live", "retired", True),
        ("live", "rejected", False),
        ("retired", "live", False),
        ("rejected", "researching", True),
        ("rejected", "live", False),
    ],
)
def test_status_transitions(writer: MemoryConfigWriter, start: str, to: str, ok: bool) -> None:
    mine(writer, start)
    change = StatusChange(to, reason="because")
    if ok:
        assert edges.set_status(writer, "alice", "mine", change, today=TODAY).status == to
    else:
        with pytest.raises(ConfigurationError, match="cannot go from"):
            edges.set_status(writer, "alice", "mine", change, today=TODAY)


def test_evidenced_and_blocked_stay_the_sites(writer: MemoryConfigWriter) -> None:
    mine(writer)
    for status in ("evidenced", "blocked"):
        with pytest.raises(ConfigurationError, match="expected one of"):
            edges.set_status(writer, "alice", "mine", StatusChange(status), today=TODAY)


def test_rejecting_needs_a_reason_and_the_status_since_moves(writer: MemoryConfigWriter) -> None:
    mine(writer)
    with pytest.raises(ConfigurationError, match="needs a reason"):
        edges.set_status(writer, "alice", "mine", StatusChange("rejected"), today=TODAY)
    done = edges.set_status(
        writer, "alice", "mine", StatusChange("rejected", reason=" no\n edge "), today=TODAY
    )
    assert (done.status, done.audit.status_reason, done.audit.status_since) == (
        "rejected", "no edge", TODAY,
    )  # fmt: skip
    assert done.rejection_reason == "no edge"


def test_going_live_against_the_verdict_is_labelled_not_blocked(
    writer: MemoryConfigWriter,
) -> None:
    mine(writer, "candidate")
    done = edges.set_status(
        writer, "alice", "mine", StatusChange("live"), today=TODAY, verdict="not_working"
    )
    assert (done.status, done.audit.labels) == ("live", ("followed_against_verdict",))
    edges.set_status(writer, "bob", "drift", StatusChange(follow=True), today=TODAY)
    clean = edges.set_status(
        writer, "carol", "drift", StatusChange(follow=True), today=TODAY, verdict="not_working"
    )
    assert clean.follow.labels == ("followed_against_verdict",)  # a bookmark carries it too
    assert seen(writer, "bob")["drift"].follow.labels == ()


def test_revealing_out_of_sample_while_tuning_is_labelled_but_going_live_is_not(
    writer: MemoryConfigWriter,
) -> None:
    mine(writer)
    tuning = edges.set_status(writer, "alice", "mine", StatusChange(reveal_oos=True), today=TODAY)
    assert (tuning.audit.oos_revealed, tuning.audit.labels) == (True, ("oos_viewed_during_tuning",))
    edges.copy_edge(writer, "alice", "drift", "kept", today=TODAY)
    edges.set_status(writer, "alice", "kept", StatusChange("candidate"), today=TODAY)
    live = edges.set_status(writer, "alice", "kept", StatusChange("live"), today=TODAY)
    assert (live.audit.oos_revealed, live.audit.labels) == (True, ())  # going live shows it too


def test_replacing_retires_the_live_edge_and_early_replacing_is_labelled(
    writer: MemoryConfigWriter,
) -> None:
    mine(writer, "candidate")
    edges.copy_edge(writer, "alice", "mine", "mine_v2", today=date(2026, 10, 1), as_version=True)
    edges.set_status(writer, "alice", "mine", StatusChange("live"), today=date(2026, 6, 1))
    done = edges.set_status(writer, "alice", "mine_v2", StatusChange("live"), today=TODAY)
    assert done.audit.labels == ("replaced_without_forward_test",)  # a week, not 20 sessions
    old = seen(writer)["mine"]
    assert (old.status, old.audit.status_reason) == ("retired", "replaced by a new version")


def test_replacing_a_followed_site_edge_unfollows_it(writer: MemoryConfigWriter) -> None:
    edges.set_status(writer, "alice", "drift", StatusChange(follow=True), today=date(2026, 6, 1))
    edges.copy_edge(writer, "alice", "drift", "drift_v2", today=date(2026, 8, 3), as_version=True)
    done = edges.set_status(writer, "alice", "drift_v2", StatusChange("live"), today=TODAY)
    assert done.audit.labels == ()  # past the forward test
    assert not seen(writer)["drift"].followed


def test_a_failed_second_write_never_leaves_two_versions_live(
    writer: MemoryConfigWriter, monkeypatch: pytest.MonkeyPatch
) -> None:
    mine(writer, "candidate")
    edges.set_status(writer, "alice", "mine", StatusChange("live"), today=date(2026, 6, 1))
    edges.copy_edge(writer, "alice", "mine", "mine_v2", today=date(2026, 8, 3), as_version=True)
    real = writer.save_user_document
    calls: list[str] = []

    def failing(user: str, kind: str, name: str, document: Any) -> None:
        calls.append(name)
        if name == "mine_v2":  # the status of the new version is the second write
            raise OSError("disk full")
        real(user, kind, name, document)

    monkeypatch.setattr(writer, "save_user_document", failing)
    with pytest.raises(OSError):
        edges.set_status(writer, "alice", "mine_v2", StatusChange("live"), today=TODAY)
    assert calls == ["mine", "mine_v2"]  # the old version is retired first
    assert [e.id for e in seen(writer).values() if e.status == "live"] == []


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


def old(state: str, **follow: Any) -> dict[str, Any]:
    return {"follow": {"state": state, "since": "2026-09-01", **follow}}


@pytest.mark.parametrize(
    ("state", "result"),
    [
        ("following", "followed"),
        ("trial", "unfollowed"),
        ("researching", "unfollowed"),
        ("rejected", "unfollowed"),
        ("retired", "unfollowed"),
    ],
)
def test_migrating_a_site_edges_follow_only_file(
    writer: MemoryConfigWriter, state: str, result: str
) -> None:
    writer.save_user_document(
        "alice", "edges", "drift", old(state, reason="r", labels=["followed_against_verdict"])
    )
    assert edges.migrate_follows(writer, "alice") == {"drift": result}
    if result == "followed":
        assert writer.load("alice", "edges", "drift") == {
            "follow": {"since": date(2026, 9, 1), "labels": ["followed_against_verdict"]}
        }
        assert seen(writer)["drift"].followed
    else:
        assert writer.load("alice", "edges", "drift") is None
        assert len(writer.archived_documents) == 1  # archived, never erased
        assert not seen(writer)["drift"].followed


@pytest.mark.parametrize(
    ("state", "status"),
    [
        ("researching", "researching"),
        ("trial", "candidate"),
        ("following", "live"),
        ("rejected", "rejected"),
        ("retired", "retired"),
    ],
)
def test_migrating_an_own_edges_follow_table_to_status_and_audit(
    writer: MemoryConfigWriter, state: str, status: str
) -> None:
    labels = ["oos_viewed_during_tuning", "followed_against_verdict"]
    writer.save_user_document(
        "alice",
        "edges",
        "mine",
        {"extends": "drift", "top_k": 3}
        | old(state, reason="why", replaces="drift", labels=labels, oos_revealed=True),
    )
    before = seen(writer)["mine"]
    assert edges.migrate_follows(writer, "alice") == {"mine": f"status {status}"}
    assert writer.load("alice", "edges", "mine") == {
        "extends": "drift",
        "top_k": 3,
        "status": status,
        "audit": {
            "status_since": date(2026, 9, 1),
            "status_reason": "why",
            "replaces": "drift",
            "labels": labels,
            "oos_revealed": True,
        },
    }
    after = seen(writer)["mine"]
    assert (after.status, after.audit) == (before.status, before.audit)  # read the same either way
    assert after.top_k == 3


def test_migrating_is_idempotent_and_leaves_new_files_alone(writer: MemoryConfigWriter) -> None:
    writer.save_user_document("alice", "edges", "drift", old("following"))
    writer.save_user_document("alice", "edges", "mine", {"extends": "drift"} | old("trial"))
    edges.copy_edge(writer, "alice", "drift", "fresh", today=TODAY)
    first = edges.migrate_follows(writer, "alice")
    assert first == {"drift": "followed", "mine": "status candidate"}
    snapshot = {n: writer.load("alice", "edges", n) for n in writer.names("alice", "edges")}
    assert edges.migrate_follows(writer, "alice") == {}
    assert snapshot == {n: writer.load("alice", "edges", n) for n in writer.names("alice", "edges")}
    assert edges.migrate_follows(writer, "bob") == {}


def test_migrating_names_a_file_it_cannot_read_and_goes_on(writer: MemoryConfigWriter) -> None:
    writer.save_user_document("alice", "edges", "mine", {"extends": "drift"} | old("bogus"))
    writer.save_user_document("alice", "edges", "other", {"extends": "drift"} | old("following"))
    done = edges.migrate_follows(writer, "alice")
    assert done["mine"].startswith("skipped:") and done["other"] == "status live"


def test_the_old_state_wins_over_a_stray_status_when_migrating(writer: MemoryConfigWriter) -> None:
    writer.save_user_document(
        "alice", "edges", "mine", {"extends": "drift", "status": "candidate"} | old("following")
    )
    assert seen(writer)["mine"].status == "live"  # read the same before the migration
    assert edges.migrate_follows(writer, "alice") == {"mine": "status live"}
    assert (writer.load("alice", "edges", "mine") or {})["status"] == "live"


def test_save_edge_revision_returns_the_previous_stored_document_read_with_the_write(
    writer: MemoryConfigWriter,
) -> None:
    edges.copy_edge(writer, "alice", "drift", "mine", today=TODAY)
    before = writer.load("alice", "edges", "mine")
    previous, stored = edges.save_edge_revision(
        writer, "alice", "mine", {"extends": "drift", "top_k": 3}
    )
    assert previous == before and stored == {"extends": "drift", "top_k": 3}
    first, _ = edges.save_edge_revision(writer, "alice", "fresh", {"extends": "drift"})
    assert first is None
