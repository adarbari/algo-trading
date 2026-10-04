"""Copy a site preset pinned to its version; rebase onto the current one."""

import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.services.authoring import presets, screens
from algotrade.services.authoring.scope import ConflictError, ScreenNotFoundError
from algotrade.storage.configs.writer import MemoryConfigWriter


def _bump(writer: MemoryConfigWriter, **changes: object) -> None:
    preset = dict(writer.load("site", "screeners", "vrp") or {})
    writer._docs[("site", "screeners", "vrp")] = preset | {"version": 4} | changes


def test_copy_pins_the_preset_version(writer: MemoryConfigWriter) -> None:
    draft = presets.copy_preset(writer, "alice", "my_vrp", "vrp")
    assert draft == {"id": "my_vrp", "extends": "vrp@3"}
    with pytest.raises(ConflictError):
        presets.copy_preset(writer, "alice", "my_vrp", "vrp")
    with pytest.raises(ScreenNotFoundError):
        presets.copy_preset(writer, "alice", "other", "nope")
    assert screens.finalise(writer, "alice", "my_vrp").version == 1
    resolved = screens.screen_detail(writer, "alice", "my_vrp")
    assert resolved.preset and (resolved.preset.pinned, resolved.preset.current) == (3, 3)
    assert resolved.resolved and resolved.resolved["schedule"] is None  # not inherited


def test_a_stale_pin_fails_closed_until_rebased(writer: MemoryConfigWriter) -> None:
    screens.save_draft(
        writer, "alice", "my_vrp", {"extends": "vrp@3", "criteria": {"price": {"value": 7}}}
    )
    screens.finalise(writer, "alice", "my_vrp")
    _bump(writer)
    detail = screens.screen_detail(writer, "alice", "my_vrp")
    assert detail.error and "rebase" in detail.error
    assert detail.preset and detail.preset.rebase_available
    draft = presets.rebase(writer, "alice", "my_vrp")
    assert draft == {"id": "my_vrp", "extends": "vrp@4", "criteria": {"price": {"value": 7}}}
    assert screens.finalise(writer, "alice", "my_vrp").version == 2
    assert screens.screen_detail(writer, "alice", "my_vrp").error is None


def test_rebase_fails_closed_when_overrides_no_longer_fit(writer: MemoryConfigWriter) -> None:
    screens.save_draft(
        writer, "alice", "my_vrp", {"extends": "vrp@3", "criteria": {"hv": {"tolerance": 0.01}}}
    )
    _bump(writer, criteria={"hv": {"field": "instrument.status", "op": "eq", "value": "A"}})
    with pytest.raises(ConfigurationError):
        presets.rebase(writer, "alice", "my_vrp")
    assert writer.draft("alice", "my_vrp") == {
        "id": "my_vrp",
        "extends": "vrp@3",
        "criteria": {"hv": {"tolerance": 0.01}},
    }


def test_rebase_needs_a_pinned_screen(writer: MemoryConfigWriter) -> None:
    with pytest.raises(ScreenNotFoundError):
        presets.rebase(writer, "alice", "mine")
    screens.save_draft(writer, "alice", "mine", {"kind": "screener"})
    with pytest.raises(ConfigurationError, match="does not extend"):
        presets.rebase(writer, "alice", "mine")
