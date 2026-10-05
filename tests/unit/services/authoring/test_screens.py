"""Drafts, finalise (fail closed, immutable versions), detail, and the nightly (ADR 0033)."""

from typing import Any

import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.services.authoring import presets, screens
from algotrade.services.authoring.scope import ConflictError, ScreenNotFoundError
from algotrade.services.configs import nightly_screeners
from algotrade.storage.configs.writer import MemoryConfigWriter, VersionExistsError

OWN: dict[str, Any] = {
    "kind": "screener",
    "impl": "rules",
    "selection": "all_active",
    "criteria": {"price": {"field": "rollup.price_stats@v2.close", "op": "gt", "value": 10}},
}


def test_save_draft_sets_id_and_drops_managed_keys(writer: MemoryConfigWriter) -> None:
    stored = screens.save_draft(
        writer, "alice", "mine", OWN | {"version": 9, "schedule": "nightly"}
    )
    assert stored == {"id": "mine", **OWN}
    assert writer.draft("alice", "mine") == stored
    with pytest.raises(ConfigurationError, match="id"):
        screens.save_draft(writer, "alice", "mine", {"id": "other"})
    with pytest.raises(ConfigurationError, match="secret"):
        screens.save_draft(writer, "alice", "mine", {"api_key": "x"})
    assert screens.discard_draft(writer, "alice", "mine") is True


def test_finalise_numbers_versions_and_removes_the_draft(writer: MemoryConfigWriter) -> None:
    screens.save_draft(writer, "alice", "mine", OWN)
    first = screens.finalise(writer, "alice", "mine")
    assert first.version == 1 and first.hash
    assert writer.draft("alice", "mine") is None
    screens.save_draft(writer, "alice", "mine", OWN | {"criteria": {"price": {"value": 20}}})
    with pytest.raises(ConfigurationError):  # a criterion without field / op
        screens.finalise(writer, "alice", "mine")
    assert writer.versions("alice", "mine") == [1]  # nothing written
    screens.save_draft(writer, "alice", "mine", OWN)
    assert screens.finalise(writer, "alice", "mine").version == 2
    assert writer.version("alice", "mine", 1) == {"id": "mine", **OWN, "version": 1}


@pytest.mark.parametrize(
    "document",
    [
        OWN | {"criteria": {"p": {"field": "rollup.nope@v1.x", "op": "gt", "value": 1}}},
        OWN | {"criteria": {"p": {"field": "instrument.status", "op": "gt", "value": 1}}},
        OWN | {"impl": "short_premium_liquidity", "criteria": None},
        {"kind": "strategy", "impl": "buy_and_hold", "selection": "all_active"},
        OWN | {"selection": "nope"},
        OWN | {"criteria": {"p": {"field": "feature.not_mine", "op": "gt", "value": 1}}},
    ],
)
def test_finalise_fails_closed(writer: MemoryConfigWriter, document: dict[str, Any]) -> None:
    document = {k: v for k, v in document.items() if v is not None}
    screens.save_draft(writer, "alice", "mine", document)
    with pytest.raises(ConfigurationError):
        screens.finalise(writer, "alice", "mine")
    assert writer.versions("alice", "mine") == []
    assert writer.draft("alice", "mine") is not None


def test_finalise_needs_a_draft_and_reports_a_race(
    writer: MemoryConfigWriter, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ScreenNotFoundError):
        screens.finalise(writer, "alice", "mine")
    screens.save_draft(writer, "alice", "mine", OWN)

    def taken(*args: object) -> None:
        raise VersionExistsError("v1 exists")

    monkeypatch.setattr(writer, "add_version", taken)
    with pytest.raises(ConflictError):
        screens.finalise(writer, "alice", "mine")


def test_detail_and_versions_and_finalising_puts_a_screen_on_the_nightly(
    writer: MemoryConfigWriter,
) -> None:
    with pytest.raises(ScreenNotFoundError):
        screens.screen_detail(writer, "alice", "mine")
    preset = screens.screen_detail(writer, "alice", "vrp")  # an uncopied site preset
    assert preset.versions == [] and preset.layers[0] == "site/screeners/vrp"
    screens.save_draft(writer, "alice", "mine", OWN)
    assert [r.config.id for r in nightly_screeners(writer) if r.user.user_id == "alice"] == []
    screens.finalise(writer, "alice", "mine")
    screens.save_draft(writer, "alice", "mine", OWN | {"selection": "nope"})
    detail = screens.screen_detail(writer, "alice", "mine")
    assert (detail.versions, detail.latest) == ([1], 1)
    assert detail.draft_error and "nope" in detail.draft_error
    assert detail.error is None and detail.resolved is not None
    assert [v.version for v in screens.screen_versions(writer, "alice", "mine")] == [1]
    # Finalising is what puts a screen on the nightly: no switch, and a draft alone is not run.
    assert [r.config.id for r in nightly_screeners(writer) if r.user.user_id == "alice"] == ["mine"]


def test_delete_takes_a_screen_off_the_list_and_the_nightly(writer: MemoryConfigWriter) -> None:
    screens.save_draft(writer, "alice", "mine", OWN)
    screens.finalise(writer, "alice", "mine")
    screens.save_draft(writer, "alice", "mine", OWN)
    screens.delete_screen(writer, "alice", "mine")
    assert [s.screener_id for s in screens.list_screens(writer, "alice")] == []
    assert [r.config.id for r in nightly_screeners(writer) if r.user.user_id == "alice"] == []
    assert len(writer.archived) == 1
    with pytest.raises(ScreenNotFoundError, match="no such screen"):
        screens.delete_screen(writer, "alice", "mine")


@pytest.mark.parametrize("user", ["site", "../etc", "Bob"])
def test_users_are_strict_labels_never_the_site(writer: MemoryConfigWriter, user: str) -> None:
    with pytest.raises(ConfigurationError):
        screens.save_draft(writer, user, "mine", OWN)


def test_list_screens_has_finalised_and_draft_only_screens(writer: MemoryConfigWriter) -> None:
    assert screens.list_screens(writer, "alice") == []
    screens.save_draft(writer, "alice", "mine", OWN)
    screens.finalise(writer, "alice", "mine")
    screens.save_draft(writer, "alice", "mine", OWN)  # a working copy beside v1
    screens.save_draft(writer, "alice", "vrp", {"extends": "vrp@3"})  # same id as the preset
    listed = {s.screener_id: s for s in screens.list_screens(writer, "alice")}
    assert list(listed) == ["mine", "vrp"]
    assert (listed["mine"].status, listed["mine"].latest, listed["mine"].has_draft) == (
        "FINAL",
        1,
        True,
    )
    assert (listed["vrp"].status, listed["vrp"].latest, listed["vrp"].preset_id) == (
        "DRAFT",
        None,
        "vrp",
    )
    assert screens.list_screens(writer, "bob") == []


def test_a_copy_may_share_its_presets_id_and_clear_the_tie_break(
    writer: MemoryConfigWriter,
) -> None:
    presets.copy_preset(writer, "alice", "vrp", "vrp")
    detail = screens.screen_detail(writer, "alice", "vrp")
    assert detail.draft == {"id": "vrp", "extends": "vrp@3"} and detail.draft_error is None
    cleared = {"extends": "vrp@3", "rank": {"tie_break": ""}}
    screens.save_draft(writer, "alice", "vrp", cleared)
    assert screens.finalise(writer, "alice", "vrp").version == 1


def test_an_uncopied_preset_names_itself_and_its_version(writer: MemoryConfigWriter) -> None:
    detail = screens.screen_detail(writer, "alice", "vrp")
    assert detail.draft is None and detail.versions == []
    assert detail.preset is not None
    assert (detail.preset.preset_id, detail.preset.pinned, detail.preset.current) == (
        "vrp",
        None,
        3,
    )
    assert not detail.preset.rebase_available
