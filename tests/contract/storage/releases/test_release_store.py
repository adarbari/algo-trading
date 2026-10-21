"""Storage contract, the serving release store (ADR 0077 decisions 1, 5, 6): a release is built in
a draft that pins its sequence, becomes visible only when sealed, and is served only once
promoted through one atomic CURRENT; a failed build is invisible; prune deletes releases and
unpins every pin no kept release (or live draft) holds."""

import json
import os
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import pyarrow as pa
import pytest

from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.backends.release.interfaces import (
    InputPartitions,
    ReleaseCorruptError,
    ReleaseInvalidError,
    ReleaseNotFoundError,
    ReleaseStore,
)
from algotrade.storage.backends.release.local import LocalReleaseStore
from algotrade.storage.backends.release.memory import MemoryReleaseStore
from algotrade.storage.tables.interfaces import Backend
from tests.helpers.stored_frames import T0, stamped

S1, S2 = date(2026, 10, 1), date(2026, 10, 2)
TABLE = "rollups/instrument/a@v1"
AT = T0 + timedelta(minutes=30)
PICKS = pa.table({"instrument_id": ["EQ:A", "EQ:B"], "rank": [1, 2]})
SESSION = pa.table({"session_date": [S1.isoformat()], "complete": [True]})


class Rig:
    """A backend and a release store over it (``kind``: memory or local); ``make`` limits."""

    def __init__(self, kind: str, tmp_path: Path) -> None:
        self.kind, self.root = kind, tmp_path / "data"
        self.backend: Backend = MemoryBackend() if kind == "memory" else LocalBackend(self.root)
        self.store = self.make()

    def make(self, **limits: object) -> ReleaseStore:
        if self.kind == "memory":  # the same releases, drafts and CURRENT under other limits
            shared = getattr(self, "store", None)
            state = None if shared is None else shared.state  # type: ignore[attr-defined]
            return MemoryReleaseStore(self.backend.tables, state=state, **limits)  # type: ignore[arg-type]
        return LocalReleaseStore(self.root, self.backend.tables, **limits)  # type: ignore[arg-type]

    def commit(self, run: str, day: date = S1, value: float = 1.0) -> int:
        frame = stamped([{"instrument_id": "EQ:A", "value": value}], day, run)
        self.backend.tables.write(TABLE, day, run, frame, pending=True)
        self.backend.tables.commit_run(run, AT)
        return self.backend.tables.visible_seq()

    def build(
        self, session: date = S1, seq: int | None = None, store: ReleaseStore | None = None
    ) -> str:
        store = store or self.store
        x = self.backend.tables.visible_seq() if seq is None else seq
        draft = store.begin(session, x, 1)
        store.write(draft, "session", SESSION)
        store.write(draft, "picks", PICKS)
        inputs = [InputPartitions(TABLE, {S1: x})]
        return store.seal(draft, inputs, "abc123").release_id


@pytest.fixture(params=["memory", "local"])
def rig(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Rig]:
    yield Rig(request.param, tmp_path)


def test_a_sealed_release_is_readable_with_its_manifest(rig: Rig) -> None:
    x = rig.commit("r1")
    release_id = rig.build()
    assert release_id == f"{S1.isoformat()}.{x}.f1"
    release = rig.store.open(release_id)
    assert release is not None
    m = release.manifest
    assert (m.format, m.session, m.seq, m.code_sha) == (1, S1.isoformat(), x, "abc123")
    assert m.destructive_epoch == rig.backend.tables.destructive_epoch()
    assert m.tables["picks"].rows == 2 and len(m.tables["picks"].sha256) == 64
    assert [(i.table, dict(i.partitions)) for i in m.inputs] == [(TABLE, {S1: x})]
    assert release.read("picks").equals(PICKS) and release.read("session").equals(SESSION)
    with pytest.raises(KeyError):
        release.read("nothing")


def test_two_builds_of_the_same_inputs_give_the_same_manifest_and_one_release(rig: Rig) -> None:
    rig.commit("r1")
    first = rig.build()
    again = rig.build()
    assert first == again
    release = rig.store.open(first)
    assert (
        release is not None
        and release.manifest.content_hash == rig.store.open(again).manifest.content_hash
    )  # type: ignore[union-attr]
    other = Rig(rig.kind, rig.root.parent / "other")
    other.commit("r1")
    assert (
        rig.store.open(first).manifest.to_json()
        == other.store.open(other.build()).manifest.to_json()
    )  # type: ignore[union-attr]


def test_begin_pins_its_sequence_so_the_release_inputs_survive_recommits(rig: Rig) -> None:
    x = rig.commit("r1", value=1.0)
    draft = rig.store.begin(S1, x, 1)
    assert rig.backend.tables.pins() == {f"release-{draft.release_id}": x}
    for v in (2.0, 3.0, 4.0):
        rig.commit("r1", value=v)
    pinned = rig.backend.tables.read(TABLE, S1, upto=x)
    assert pinned is not None and float(pinned["value"].iloc[0]) == 1.0


def test_a_failed_seal_is_invisible_and_leaves_current_where_it_was(rig: Rig) -> None:
    x = rig.commit("r1")
    good = rig.build()
    rig.store.promote(good)
    y = rig.commit("r2", S2)
    draft = rig.store.begin(S2, y, 1)
    rig.store.write(draft, "picks", PICKS)
    with pytest.raises(ReleaseInvalidError, match="above"):
        rig.store.seal(draft, [InputPartitions(TABLE, {S2: y + 1})], "abc")
    assert rig.store.open(draft.release_id) is None
    with pytest.raises(ReleaseNotFoundError):
        rig.store.promote(draft.release_id)
    assert rig.store.current() == (good, rig.store.open(good).manifest.content_hash)  # type: ignore[union-attr]
    assert x < y


def test_a_destructive_operation_between_begin_and_seal_or_promote_invalidates(rig: Rig) -> None:
    x = rig.commit("r1")
    draft = rig.store.begin(S1, x, 1)
    rig.store.write(draft, "picks", PICKS)
    rig.backend.tables.drop("rollups/instrument/other@v1")
    with pytest.raises(ReleaseInvalidError, match="epoch"):
        rig.store.seal(draft, [InputPartitions(TABLE, {S1: x})], "abc")
    sealed = rig.build()  # a new draft: sealed at the new epoch
    rig.backend.tables.drop("rollups/instrument/other@v1")
    with pytest.raises(ReleaseInvalidError, match="epoch"):
        rig.store.promote(sealed)
    assert rig.store.current() is None


def test_promote_switches_current_in_one_step_and_keeps_the_old_release_openable(
    rig: Rig,
) -> None:
    rig.commit("r1")
    first = rig.build()
    rig.store.promote(first)
    rig.commit("r2", S2)
    second = rig.build(S2)
    assert rig.store.current() == (first, rig.store.open(first).manifest.content_hash)  # type: ignore[union-attr]
    rig.store.promote(second)
    current = rig.store.current_release()
    assert current is not None and current.manifest.release_id == second
    assert rig.store.open(first) is not None
    with pytest.raises(ReleaseNotFoundError):
        rig.store.promote("2026-01-01.1.f1")


def test_a_promote_that_dies_before_the_rename_changes_nothing(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    if rig.kind != "local":
        pytest.skip("CURRENT is a file only on the local store")
    rig.commit("r1")
    first = rig.build()
    rig.store.promote(first)
    rig.commit("r2", S2)
    second = rig.build(S2)

    def boom(*args: object, **kwargs: object) -> None:
        raise OSError("killed")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError, match="killed"):
        rig.store.promote(second)
    monkeypatch.undo()
    assert rig.store.current_release().manifest.release_id == first  # type: ignore[union-attr]
    assert not [p for p in (rig.root / "serving").iterdir() if p.name.endswith(".tmp")]


def test_current_is_verified_against_the_manifest_hash(rig: Rig) -> None:
    if rig.kind != "local":
        pytest.skip("files are tampered with on the local store")
    rig.commit("r1")
    release_id = rig.build()
    rig.store.promote(release_id)
    folder = rig.root / "serving" / "releases" / release_id
    manifest = folder / "manifest.json"
    original = manifest.read_bytes()

    manifest.write_bytes(original.replace(b'"code_sha":"abc123"', b'"code_sha":"evil00"'))
    with pytest.raises(ReleaseCorruptError):
        rig.store.open(release_id)
    with pytest.raises(ReleaseCorruptError):
        rig.store.current_release()
    manifest.write_bytes(original)

    (rig.root / "serving" / "CURRENT").write_text(
        json.dumps({"manifest_hash": "0000", "release_id": release_id})
    )
    with pytest.raises(ReleaseCorruptError, match="CURRENT"):
        rig.store.current_release()


def test_a_table_file_that_changed_is_refused_on_read(rig: Rig) -> None:
    if rig.kind != "local":
        pytest.skip("files are tampered with on the local store")
    rig.commit("r1")
    release_id = rig.build()
    path = rig.root / "serving" / "releases" / release_id / "picks.parquet"
    path.write_bytes(path.read_bytes()[:-8] + b"tampered")
    release = rig.store.open(release_id)
    assert release is not None
    with pytest.raises(ReleaseCorruptError):
        release.read("picks")


def test_a_release_over_the_size_ceiling_is_not_sealed(rig: Rig) -> None:
    x = rig.commit("r1")
    small = rig.make(max_bytes=50)
    draft = small.begin(S1, x, 1)
    small.write(draft, "picks", PICKS)
    with pytest.raises(ReleaseInvalidError, match="ceiling"):
        small.seal(draft, [InputPartitions(TABLE, {S1: x})], "abc")
    assert small.open(draft.release_id) is None


def test_a_build_is_refused_without_the_free_space_floor_and_pins_nothing(rig: Rig) -> None:
    x = rig.commit("r1")
    tight = rig.make(free=lambda: 10)
    with pytest.raises(ReleaseInvalidError, match="free"):
        tight.begin(S1, x, 1)
    assert rig.backend.tables.pins() == {}


def test_the_floor_is_three_times_the_last_release_when_that_is_larger(rig: Rig) -> None:
    rig.commit("r1")
    rig.build()
    last = sum(t.bytes for t in rig.store.open(rig.store.releases()[-1]).manifest.tables.values())  # type: ignore[union-attr]
    x = rig.backend.tables.visible_seq()
    floor = 5 * 1024**3
    assert rig.make(free=lambda: floor).begin(S2, x, 1) is not None
    assert 3 * last < floor  # a small release: the 5 GB minimum rules
    with pytest.raises(ReleaseInvalidError):
        rig.make(free=lambda: floor - 1).begin(S2, x, 1)


def test_prune_keeps_the_newest_and_the_current_and_unpins_the_rest(rig: Rig) -> None:
    ids = []
    for n, day in enumerate((S1, S2, date(2026, 10, 3), date(2026, 10, 4))):
        rig.commit(f"r{n}", day)
        ids.append(rig.build(day))
    rig.store.promote(ids[1])
    assert rig.store.prune(keep=1) == 2  # ids[0] and ids[2] go; the newest and the current stay
    assert rig.store.releases() == [ids[1], ids[3]]
    assert rig.store.open(ids[0]) is None and rig.store.open(ids[3]) is not None
    assert set(rig.backend.tables.pins()) == {f"release-{ids[1]}", f"release-{ids[3]}"}
    assert rig.store.current_release().manifest.release_id == ids[1]  # type: ignore[union-attr]


def test_prune_unpins_a_crashed_draft_and_a_pin_with_no_release_but_not_other_pins(
    rig: Rig,
) -> None:
    x = rig.commit("r1")
    crashed = rig.store.begin(S1, x, 1)  # a build that died before seal
    rig.backend.tables.pin("release-2026-09-01.1.f1", 1)  # a release deleted by hand
    rig.backend.tables.pin("someone-else", 1)
    live = rig.make(draft_ttl_s=3600)
    assert live.prune(keep=1) == 0
    assert f"release-{crashed.release_id}" in rig.backend.tables.pins()  # a draft in flight
    assert "release-2026-09-01.1.f1" not in rig.backend.tables.pins()
    expired = rig.make(draft_ttl_s=0)
    expired.prune(keep=1)
    assert rig.backend.tables.pins() == {"someone-else": 1}


def test_abort_removes_a_draft_and_its_pin(rig: Rig) -> None:
    x = rig.commit("r1")
    draft = rig.store.begin(S1, x, 1)
    rig.store.write(draft, "picks", PICKS)
    rig.store.abort(draft)
    assert rig.backend.tables.pins() == {} and rig.store.open(draft.release_id) is None
    sealed = rig.build()
    rig.store.abort(rig.store.begin(S1, x, 1))  # the id of a sealed release: its pin stays
    assert f"release-{sealed}" in rig.backend.tables.pins()


def test_report_names_the_pins_and_measures_retained_disk_only_when_asked_or_after_a_prune(
    rig: Rig,
) -> None:
    x = rig.commit("r1")
    rig.build()
    for v in (2.0, 3.0, 4.0):
        rig.commit("r1", value=v)
    name = f"release-{S1.isoformat()}.{x}.f1"
    report = rig.store.report()
    assert report.pins == {name: x}
    assert report.releases == (f"{S1.isoformat()}.{x}.f1",) and report.current is None
    assert report.pinned_bytes is None  # never measured: status and doctor do not walk the store
    assert (rig.store.report(with_bytes=True).pinned_bytes or 0) > 0
    rig.store.prune(keep=1)  # the job records what the pins hold after its prune
    assert (rig.store.report().pinned_bytes or 0) > 0
    rig.store.prune(keep=0)
    assert rig.store.report().pinned_bytes == 0 and rig.store.report().pins == {}


def test_a_rebuild_after_a_deploy_returns_the_existing_release_not_an_error(rig: Rig) -> None:
    x = rig.commit("r1")
    first = rig.build()
    again = rig.store.begin(S1, x, 1)
    rig.store.write(again, "picks", PICKS)
    kept = rig.store.seal(again, [InputPartitions(TABLE, {S1: x})], "newcode")  # other code_sha
    assert kept.release_id == first and kept.code_sha == "abc123"
    same_code = rig.store.begin(S1, x, 1)
    rig.store.write(same_code, "picks", pa.table({"instrument_id": ["EQ:Z"], "rank": [9]}))
    with pytest.raises(ReleaseInvalidError, match="other content"):  # same code, other bytes
        rig.store.seal(same_code, [InputPartitions(TABLE, {S1: x})], "abc123")


def test_a_draft_pruned_during_the_build_cannot_be_written_sealed_or_served(rig: Rig) -> None:
    x = rig.commit("r1")
    draft = rig.store.begin(S1, x, 1)
    rig.store.write(draft, "session", SESSION)
    rig.make(draft_ttl_s=0).prune(keep=1)  # the build looked dead: folder and pin are gone
    with pytest.raises(ReleaseInvalidError, match="draft"):
        rig.store.write(draft, "picks", PICKS)
    with pytest.raises(ReleaseInvalidError, match="pin"):
        rig.store.seal(draft, [InputPartitions(TABLE, {S1: x})], "abc")
    assert rig.store.open(draft.release_id) is None and rig.store.releases() == []
    if rig.kind == "local":
        assert not (rig.root / "serving" / "drafts").exists() or not any(
            (rig.root / "serving" / "drafts").iterdir()
        )


def test_promote_refuses_a_release_whose_pin_is_gone(rig: Rig) -> None:
    rig.commit("r1")
    release_id = rig.build()
    rig.backend.tables.unpin(f"release-{release_id}")
    with pytest.raises(ReleaseInvalidError, match="pin"):
        rig.store.promote(release_id)
    assert rig.store.current() is None


def test_current_naming_a_pruned_release_is_read_again_once(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig.commit("r1")
    old = rig.build()
    rig.store.promote(old)
    rig.commit("r2", S2)
    new = rig.build(S2)
    rig.store.promote(new)
    stale = (old, "stale")
    real, calls = rig.store.current, []

    def current() -> tuple[str, str] | None:
        calls.append(1)
        return stale if len(calls) == 1 else real()

    rig.store._delete_release(old)  # type: ignore[attr-defined]
    monkeypatch.setattr(rig.store, "current", current)
    found = rig.store.current_release()
    assert found is not None and found.manifest.release_id == new


def test_a_read_racing_a_prune_raises_not_found(rig: Rig) -> None:
    rig.commit("r1")
    old = rig.build()
    rig.commit("r2", S2)
    new = rig.build(S2)
    rig.store.promote(new)
    release = rig.store.open(old)
    assert release is not None
    assert rig.store.prune(keep=0) == 1
    with pytest.raises(ReleaseNotFoundError):
        release.read("picks")
