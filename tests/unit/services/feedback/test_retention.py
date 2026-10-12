"""``retain`` and ``erase``: personal text is nulled in both tables (the right rows only), reads
show it at once, the superseded Parquet files are gone, a dry run writes nothing, a run twice
changes nothing, and the audit line holds counts only (ADR 0066)."""

import json
import threading
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.data import StoreReader
from algotrade.data.feedback import read_drafting_events
from algotrade.data.usage import read_llm_calls
from algotrade.services.feedback import retention
from algotrade.services.feedback.events import row_of
from algotrade.services.feedback.recorder import FeedbackRecorder
from algotrade.services.text_model.usage import UsageRecorder
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.feedback_writer import FeedbackWriter
from algotrade.storage.tables.interfaces import Backend
from algotrade.storage.tables.schemas import KNOWN
from algotrade.storage.tables.usage_writer import UsageWriter

OLD = datetime(2025, 6, 2, 15, tzinfo=UTC)
YOUNG = datetime(2026, 9, 2, 15, tzinfo=UTC)
NOW = datetime(2026, 10, 11, 12, tzinfo=UTC)
RANGE = (date(2025, 1, 1), date(2026, 12, 31))
SECRET = "my wife works at Acme, find stocks like it"


@pytest.fixture(params=["memory", "local"])
def backend(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Backend]:
    factories: dict[str, Callable[[], Backend]] = {
        "memory": MemoryBackend,
        "local": lambda: LocalBackend(tmp_path / "data"),
    }
    yield factories[request.param]()


def feedback_row(at: datetime, user: str, event: str = "draft_requested", **over: Any) -> dict:
    return row_of(
        event, "sess-" + user, user, "screen", "my-screen", at=at, sentence=SECRET,
        payload={"current_criteria": [{"field": "pe"}]}, draft_hash="h", **over,
    )  # fmt: skip


def usage_row(at: datetime, user: str, **over: Any) -> dict[str, Any]:
    row = {"ts": at, "provider": "gemini", "model": "m", "use_case": "screener-draft",
           "user": user, "input_tokens": 10, "output_tokens": 5, "latency_s": 0.4,
           "cost_usd": 0.0, "cost_basis": "free", "outcome": "failed", "fell_back_from": None,
           "error": "bad json: " + SECRET, "sentence": SECRET,
           "answer": "raw " + SECRET}  # fmt: skip
    return row | over


def record(
    backend: Backend, feedback: list[dict[str, Any]], usage: list[dict[str, Any]], at: datetime
) -> None:
    """Rows written through the real recorders, one run (so one more run per call)."""
    fb = FeedbackRecorder(FeedbackWriter(backend), clock=lambda: at)
    us = UsageRecorder(UsageWriter(backend), clock=lambda: at)
    for row in feedback:
        fb.submit(row)
    for row in usage:
        us.submit(row)
    fb.flush()
    us.flush()
    fb.close()
    us.close()


def seed(backend: Backend) -> list[dict[str, Any]]:
    """Old and young rows of two users; returns the old feedback rows."""
    old = [feedback_row(OLD, "abhi"), feedback_row(OLD, "bea")]
    record(backend, old, [usage_row(OLD, "abhi"), usage_row(OLD, "bea")], OLD)
    record(
        backend, [feedback_row(YOUNG, "abhi"), feedback_row(YOUNG, "bea")],
        [usage_row(YOUNG, "abhi"), usage_row(YOUNG, "bea")], YOUNG,
    )  # fmt: skip
    return old


def events(backend: Backend) -> pd.DataFrame:
    frame = read_drafting_events(StoreReader(backend), *RANGE)
    assert frame is not None
    return frame.sort_values(["ts", "user"]).reset_index(drop=True)


def calls(backend: Backend) -> pd.DataFrame:
    frame = read_llm_calls(StoreReader(backend), *RANGE)
    assert frame is not None
    return frame.sort_values(["ts", "user"]).reset_index(drop=True)


def parquet_files(backend: Backend) -> int:
    assert isinstance(backend, LocalBackend)
    return len(list(backend.root.rglob("*.parquet")))


def test_retain_nulls_only_old_rows_and_keeps_the_skeleton(backend: Backend) -> None:
    seed(backend)
    done = retention.retain(backend, NOW, apply=True)
    fb, us = events(backend), calls(backend)
    assert len(fb) == 4 and len(us) == 4  # counts still add up
    old, young = (
        fb[fb["ts"] < pd.Timestamp("2026-01-01", tz="UTC")],
        fb[fb["ts"] > pd.Timestamp("2026-01-01", tz="UTC")],
    )
    assert old[["sentence", "payload"]].isna().all().all()
    assert (old["draft_hash"] == "h").all() and set(old["user"]) == {"abhi", "bea"}
    assert (young["sentence"] == SECRET).all() and young["payload"].notna().all()
    uold = us[us["ts"] < pd.Timestamp("2026-01-01", tz="UTC")]
    assert uold[["sentence", "answer", "error"]].isna().all().all()
    assert (uold["outcome"] == "failed").all() and (uold["input_tokens"] == 10).all()
    assert (us[us["ts"] > pd.Timestamp("2026-01-01", tz="UTC")]["sentence"] == SECRET).all()
    assert done.rows(retention.FEEDBACK) == 2 and done.rows(retention.USAGE) == 2


def test_retain_spares_a_curated_event_and_the_calls_it_lists(
    backend: Backend, tmp_path: Path
) -> None:
    old = [feedback_row(OLD, "abhi", call_ids=["c1"]), feedback_row(OLD, "bea")]
    record(
        backend,
        old,
        [usage_row(OLD, "abhi", call_id="c1"), usage_row(OLD, "bea", call_id="c2")],
        OLD,
    )
    cases = tmp_path / "cases"
    cases.mkdir()
    (cases / "x.json").write_text(json.dumps({"id": "x", "source_event": old[0]["event_id"]}))
    retention.retain(backend, NOW, golden_cases=cases, apply=True)
    fb, us = events(backend), calls(backend)
    kept = fb[fb["event_id"] == old[0]["event_id"]].iloc[0]
    assert kept["sentence"] == SECRET and pd.notna(kept["payload"])
    assert pd.isna(fb[fb["event_id"] == old[1]["event_id"]].iloc[0]["sentence"])
    assert us[us["call_id"] == "c1"].iloc[0]["sentence"] == SECRET
    assert pd.isna(us[us["call_id"] == "c2"].iloc[0]["sentence"])


def test_the_old_parquet_files_are_physically_gone_after_the_rewrite(tmp_path: Path) -> None:
    local = LocalBackend(tmp_path / "data")
    seed(local)
    before = parquet_files(local)
    done = retention.retain(local, NOW, apply=True)
    assert done.superseded_runs == 2  # the old feedback run and the old usage run
    assert parquet_files(local) == before  # each rewritten partition: one file replaced by one
    # the text appears nowhere in a file of an old partition
    for path in (tmp_path / "data").rglob("date=2025-*/*.parquet"):
        assert SECRET.encode() not in path.read_bytes()


def test_erase_touches_only_the_named_user_and_leaves_a_skeleton_that_joins_to_nothing(
    backend: Backend,
) -> None:
    seed(backend)
    done = retention.erase(backend, "abhi", NOW, apply=True)
    fb, us = events(backend), calls(backend)
    assert len(fb) == 4 and len(us) == 4 and done.rows() == 4  # counts still add up
    theirs = fb[fb["user"] == "bea"]
    mine = fb[fb["user"].str.startswith("erased-")]
    assert len(mine) == 2 and len(theirs) == 2 and "abhi" not in set(fb["user"])
    assert mine[["sentence", "payload"]].isna().all().all()
    for column in ("user", "doc_id", "draft_session_id", "draft_hash"):
        assert mine[column].str.startswith("erased-").all() and mine[column].is_unique
    assert (mine["event"] == "draft_requested").all() and (mine["doc_kind"] == "screen").all()
    assert (mine["ts"] == mine["ts"].dt.floor("D")).all()  # the day, not the time
    assert (theirs["sentence"] == SECRET).all() and theirs["payload"].notna().all()
    assert (theirs["doc_id"] == "my-screen").all() and (theirs["draft_hash"] == "h").all()
    assert (theirs["ts"] != theirs["ts"].dt.floor("D")).all()
    gone, kept = us[us["user"].str.startswith("erased-")], us[us["user"] == "bea"]
    assert len(gone) == 2 and gone["user"].is_unique
    assert gone[["sentence", "answer", "error"]].isna().all().all()
    assert (gone["outcome"] == "failed").all() and (gone["input_tokens"] == 10).all()
    assert (gone["ts"] == gone["ts"].dt.floor("D")).all()
    assert kept["error"].notna().all() and (kept["sentence"] == SECRET).all()


def test_erase_keeps_a_curated_events_criteria_but_never_its_text(
    backend: Backend, tmp_path: Path
) -> None:
    old = [feedback_row(OLD, "abhi"), feedback_row(OLD, "abhi")]
    record(backend, old, [], OLD)
    folder = case_folder(tmp_path, {"chain_id": "s", "source_events": [old[0]["event_id"]]})
    retention.erase(backend, "abhi", NOW, golden_cases=folder, apply=True)
    fb = events(backend).set_index("event_id")
    assert fb.loc[old[0]["event_id"], "sentence"] is None or pd.isna(
        fb.loc[old[0]["event_id"], "sentence"]
    )
    assert pd.notna(fb.loc[old[0]["event_id"], "payload"])
    assert pd.isna(fb.loc[old[1]["event_id"], "payload"])
    assert not fb["user"].eq("abhi").any()


def test_a_dry_run_writes_nothing(backend: Backend) -> None:
    seed(backend)
    before = (backend.tables.visible_seq(), events(backend), calls(backend))
    for done in (retention.retain(backend, NOW), retention.erase(backend, "abhi", NOW)):
        assert not done.applied and done.rows() > 0 and done.run_id is None
    assert backend.tables.pending_runs() == [] and backend.tables.visible_seq() == before[0]
    pd.testing.assert_frame_equal(events(backend), before[1])
    pd.testing.assert_frame_equal(calls(backend), before[2])
    assert "dry run" in retention.retain(backend, NOW).lines()[-1]


def test_a_second_run_changes_nothing(backend: Backend) -> None:
    seed(backend)
    retention.retain(backend, NOW, apply=True)
    seq = backend.tables.visible_seq()
    again = retention.retain(backend, NOW, apply=True)
    assert again.rows() == 0 and again.run_id is None and backend.tables.visible_seq() == seq
    retention.erase(backend, "abhi", NOW, apply=True)
    assert retention.erase(backend, "abhi", NOW, apply=True).rows() == 0


def test_it_refuses_while_a_run_has_pending_writes(backend: Backend) -> None:
    seed(backend)
    frame = backend.tables.read(retention.FEEDBACK, date(2026, 9, 2))
    assert frame is not None
    backend.tables.write(retention.FEEDBACK, date(2026, 9, 2), "busy", frame, pending=True)
    with pytest.raises(ConfigurationError, match="pending"):
        retention.retain(backend, NOW, apply=True)
    backend.tables.abort_run("busy")
    retention.retain(backend, NOW, apply=True)


def test_it_refuses_while_another_retention_command_runs(backend: Backend) -> None:
    seed(backend)
    lock = backend.lock(retention.LOCK)
    assert lock.acquire(wait=False)
    try:
        with pytest.raises(ConfigurationError, match="running"):
            retention.erase(backend, "abhi", NOW, apply=True)
    finally:
        lock.release()


def test_a_row_the_recorder_adds_after_the_rewrite_is_kept(backend: Backend) -> None:
    seed(backend)
    retention.retain(backend, NOW, apply=True)
    record(backend, [feedback_row(NOW, "abhi")], [], NOW)
    assert (events(backend).iloc[-1]["sentence"] == SECRET) and len(events(backend)) == 5


def test_the_audit_line_holds_counts_only(backend: Backend, tmp_path: Path) -> None:
    seed(backend)
    done = retention.erase(backend, "abhi", NOW, apply=True)
    log = tmp_path / "var" / "logs" / "audit.log"
    retention.append_audit(log, retention.audit_record(done, NOW, {"older_than_days": None}))
    line = json.loads(log.read_text())
    assert line["rows"][retention.FEEDBACK] == 2 and line["rows"][retention.USAGE] == 2
    assert "abhi" not in log.read_text() and SECRET not in log.read_text()


def test_erase_needs_a_user(backend: Backend) -> None:
    with pytest.raises(ConfigurationError):
        retention.erase(backend, "", NOW)


def case_folder(tmp_path: Path, *cases: dict[str, Any]) -> Path:
    folder = tmp_path / "cases"
    folder.mkdir()
    for i, case in enumerate(cases):
        (folder / f"c{i}.json").write_text(json.dumps(case))
    return folder


def test_a_curated_chain_spares_every_event_of_it(backend: Backend, tmp_path: Path) -> None:
    chain = [
        feedback_row(OLD, "abhi", "draft_requested", call_ids=["c1"]),
        feedback_row(OLD, "abhi", "draft_returned"),
        feedback_row(OLD, "abhi", "screen_finalised"),
    ]
    loose = feedback_row(OLD, "bea")
    record(backend, [*chain, loose], [usage_row(OLD, "abhi", call_id="c1")], OLD)
    ids = [r["event_id"] for r in chain]
    folder = case_folder(
        tmp_path, {"chain_id": "sess-abhi", "source_events": ids, "source_event": ids[-1]}
    )
    retention.retain(backend, NOW, golden_cases=folder, apply=True)
    fb = events(backend).set_index("event_id")
    assert all(fb.loc[i, "sentence"] == SECRET or fb.loc[i, "payload"] for i in ids[:1])
    assert fb.loc[ids[0], "sentence"] == SECRET and pd.isna(fb.loc[loose["event_id"], "sentence"])
    assert calls(backend).iloc[0]["sentence"] == SECRET


def test_retain_fails_closed_without_the_golden_cases(backend: Backend, tmp_path: Path) -> None:
    seed(backend)
    with pytest.raises(ConfigurationError, match="missing"):
        retention.retain(backend, NOW, golden_cases=tmp_path / "nope", apply=True)
    bad = case_folder(tmp_path, {"chain_id": "s", "source_events": []})
    with pytest.raises(ConfigurationError, match="no source events"):
        retention.retain(backend, NOW, golden_cases=bad, apply=True)
    assert (events(backend)["sentence"] == SECRET).all()  # nothing was nulled


def test_hand_written_cases_name_no_events_and_the_defaults_are_the_repo_not_the_cwd() -> None:
    assert retention.GOLDEN_CASES.is_absolute() and retention.AUDIT_LOG.is_absolute()
    assert retention.GOLDEN_CASES.is_dir()
    assert retention.curated_events(retention.GOLDEN_CASES) >= frozenset()


def test_a_run_committed_with_an_older_ts_after_the_rewrite_survives(backend: Backend) -> None:
    seed(backend)
    retention.erase(backend, "abhi", NOW, apply=True)
    late = feedback_row(OLD.replace(hour=14), "bea")  # older ts than the partition's newest
    record(backend, [late], [], NOW)
    assert late["event_id"] in set(events(backend)["event_id"]) and len(events(backend)) == 5


def test_the_recorders_wait_for_the_retention_lock(backend: Backend) -> None:
    lock = backend.lock(retention.FEEDBACK_WRITERS)
    assert lock.acquire()
    rec = FeedbackRecorder(FeedbackWriter(backend), clock=lambda: OLD)
    rec.submit(feedback_row(OLD, "abhi"))
    done = threading.Thread(target=rec.flush)
    done.start()
    done.join(0.3)
    assert done.is_alive() and backend.tables.dates(retention.FEEDBACK) == []  # held back
    lock.release()
    done.join(5)
    assert not done.is_alive() and backend.tables.dates(retention.FEEDBACK) != []
    rec.close()


def test_a_crash_between_the_commit_and_the_purge_is_finished_by_the_next_run(
    backend: Backend, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed(backend)
    real = backend.tables.purge_runs

    def crash(*args: Any) -> int:
        raise OSError("disk went away")

    monkeypatch.setattr(backend.tables, "purge_runs", crash)
    with pytest.raises(OSError):
        retention.retain(backend, NOW, apply=True)
    monkeypatch.setattr(backend.tables, "purge_runs", real)
    assert (
        events(backend)[events(backend)["ts"] < pd.Timestamp("2026-01-01", tz="UTC")]["sentence"]
        .isna()
        .all()
    )  # reads are clean already
    dry = retention.retain(backend, NOW)
    assert dry.rows() == 0 and dry.to_purge == 2  # a dry run reports the runs still on disk
    done = retention.retain(backend, NOW, apply=True)
    assert done.rows() == 0 and done.superseded_runs == 2 and done.run_id is None
    assert retention.retain(backend, NOW).to_purge == 0


def test_a_purge_that_leaves_runs_behind_fails_the_command(
    backend: Backend, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed(backend)
    monkeypatch.setattr(backend.tables, "purge_runs", lambda *a: 0)
    with pytest.raises(RuntimeError, match="still on disk"):
        retention.retain(backend, NOW, apply=True)


def test_other_partitions_files_are_not_touched(tmp_path: Path) -> None:
    local = LocalBackend(tmp_path / "data")
    seed(local)
    young = {p: p.read_bytes() for p in (tmp_path / "data").rglob("date=2026-09-02/*.parquet")} | {
        p: p.read_bytes() for p in (tmp_path / "data").rglob("_runs.json") if "2026-09" in str(p)
    }
    assert young
    retention.retain(local, NOW, apply=True)
    retention.erase(local, "nobody", NOW, apply=True)
    for path, data in young.items():
        assert path.read_bytes() == data


def test_every_personal_table_is_registered_with_its_text_columns() -> None:
    registered = {t.table: t for t in retention.PERSONAL}
    names = [n for n in KNOWN if n.startswith(("feedback/", "usage/"))]
    assert names, "no feedback or usage table found"
    for name in names:
        assert name in registered, f"{name} holds text: register it in retention.PERSONAL"
        t, spec = registered[name], KNOWN[name]
        strings = {c.name for c in spec.columns if c.type == "string"}
        covered = {*t.text, *t.criteria, t.user, *t.tokenized, *t.safe, "source", "run_id"}
        assert strings <= covered, f"{name}: classify {sorted(strings - covered)} (text or safe)"
        assert {*t.text, *t.criteria, t.user, *t.tokenized} <= {c.name for c in spec.columns}


def test_erased_feature_requests_never_collide_on_their_key() -> None:
    """The table key is (user, ref, session_date): a fixed placeholder would merge two erased
    users who asked for the same thing on a day; every row gets a fresh token."""
    frame = pd.DataFrame({
        "ts": pd.to_datetime(["2026-10-01T10:00Z", "2026-10-01T11:00Z", "2026-10-01T12:00Z"]),
        "user": ["abhi", "abhi", "bea"], "ref": ["r1", "r2", "r1"],
        "span": ["secret a", "secret b", "secret c"], "draft_session_id": ["s1", "s1", "s2"],
        "call_id": ["c1", None, "c3"],
    })  # fmt: skip
    table = next(t for t in retention.PERSONAL if t.table == retention.FEATURE_REQUESTS)
    redaction = retention.erase_redactions("abhi", {}, [table])[0]
    out, changed = redaction.redact(frame)
    assert (
        changed == 2 and out["span"].tolist()[:2] == [None, None] and out["span"][2] == "secret c"
    )
    assert out["user"][2] == "bea" and out["ref"].tolist() == ["r1", "r2", "r1"]
    assert out["user"][:2].is_unique and pd.isna(out["call_id"][1])
    assert (out["ts"][:2] == pd.Timestamp("2026-10-01", tz="UTC")).all()


def test_an_erase_that_crashed_before_its_purge_is_finished_without_duplicating_rows(
    backend: Backend, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed(backend)
    real = backend.tables.purge_runs
    monkeypatch.setattr(backend.tables, "purge_runs", lambda *a: (_ for _ in ()).throw(OSError()))
    with pytest.raises(OSError):
        retention.erase(backend, "abhi", NOW, apply=True)
    monkeypatch.setattr(backend.tables, "purge_runs", real)
    done = retention.erase(backend, "abhi", NOW, apply=True)
    assert done.rows() == 0 and done.superseded_runs >= 2
    assert len(events(backend)) == 4 and len(calls(backend)) == 4
    assert not events(backend)["user"].eq("abhi").any()


def test_a_retain_finishes_the_purge_an_erase_crash_left_in_a_recent_partition(
    backend: Backend, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed(backend)  # the young partitions are not retain's to rewrite
    real = backend.tables.purge_runs
    monkeypatch.setattr(backend.tables, "purge_runs", lambda *a: (_ for _ in ()).throw(OSError()))
    with pytest.raises(OSError):
        retention.erase(backend, "abhi", NOW, apply=True)
    monkeypatch.setattr(backend.tables, "purge_runs", real)
    assert len(calls(backend)) == 6  # old and erased copies both read: cost counted twice
    assert retention.retain(backend, NOW).to_purge > 0  # a dry run says so
    retention.retain(backend, NOW, apply=True)
    assert len(events(backend)) == 4 and len(calls(backend)) == 4
    assert (
        not events(backend)["user"].eq("abhi").any()
        and (calls(backend)["sentence"] == SECRET).sum() == 1
    )
    assert retention.retain(backend, NOW).to_purge == 0


def test_no_erased_row_keeps_a_time_of_day_in_any_column(backend: Backend) -> None:
    seed(backend)
    retention.erase(backend, "abhi", NOW, apply=True)
    for frame in (events(backend), calls(backend)):
        erased = frame[frame["user"].str.startswith("erased-")]
        assert len(erased) == 2
        for column in ("ts", "knowledge_ts"):
            assert (erased[column] == erased[column].dt.floor("D")).all()
        kept = frame[~frame["user"].str.startswith("erased-")]
        assert (kept["knowledge_ts"] != kept["knowledge_ts"].dt.floor("D")).all()


def test_a_run_that_fails_its_verification_is_still_audited(
    backend: Backend, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed(backend)
    monkeypatch.setattr(backend.tables, "purge_runs", lambda *a: 0)
    seen: list[retention.Outcome] = []
    with pytest.raises(RuntimeError):
        retention.retain(backend, NOW, apply=True, audit=seen.append)
    assert len(seen) == 1 and seen[0].error == "RuntimeError" and seen[0].run_id
    assert retention.audit_record(seen[0], NOW, {})["error"] == "RuntimeError"


def test_close_does_not_wait_forever_on_a_full_queue(backend: Backend) -> None:
    lock = backend.lock(retention.FEEDBACK_WRITERS)
    assert lock.acquire()  # the writer thread is stuck behind a retention run
    rec = FeedbackRecorder(FeedbackWriter(backend), maxsize=1, clock=lambda: OLD)
    rec.submit(feedback_row(OLD, "abhi"))
    rec.submit(feedback_row(OLD, "abhi"))  # taken by the thread, then queued
    rec.submit(feedback_row(OLD, "abhi"))
    started = datetime.now(UTC)
    rec.close(timeout_s=0.3)
    assert (datetime.now(UTC) - started).total_seconds() < 3
    lock.release()


def two_recorder_runs(backend: Backend) -> None:
    """Two live recorder runs in one partition each, no retention run anywhere."""
    first = YOUNG.replace(hour=14)  # run ids have one-second resolution: never seed's own
    record(backend, [feedback_row(first, "abhi")], [usage_row(first, "abhi")], first)
    later = YOUNG.replace(hour=16)
    record(backend, [feedback_row(later, "bea")], [usage_row(later, "bea")], later)


def snapshot(backend: Backend) -> dict[str, object]:
    runs = {
        (t.table, day): backend.tables.partition_runs(t.table, day)
        for t in retention.PERSONAL
        for day in backend.tables.dates(t.table)
    }
    files: dict[str, bytes] = {}
    if isinstance(backend, LocalBackend):
        files = {str(p): p.read_bytes() for p in backend.root.rglob("*") if p.is_file()}
        files = {k: v for k, v in files.items() if "/locks/" not in k and "_txn" not in k}
    return {"runs": runs, "files": files}


def test_a_partition_with_only_recorder_runs_keeps_every_run_and_row(backend: Backend) -> None:
    two_recorder_runs(backend)
    runs = backend.tables.partition_runs(retention.FEEDBACK, date(2026, 9, 2))
    assert len(runs) == 2 and not any(r.startswith(retention.JOB) for r in runs)
    assert retention.retain(backend, NOW).to_purge == 0  # (b) the dry run reports nothing
    assert retention.erase(backend, "nobody", NOW).to_purge == 0
    before = snapshot(backend)
    done = retention.retain(backend, NOW, apply=True)  # (c) a no-op leaves every file alone
    assert done.superseded_runs == 0 and snapshot(backend) == before
    done = retention.erase(backend, "nobody", NOW, apply=True)
    assert done.superseded_runs == 0 and snapshot(backend) == before
    assert len(events(backend)) == 2 and len(calls(backend)) == 2  # (a) all rows
    assert (events(backend)["sentence"] == SECRET).all()
    retention.erase(backend, "abhi", NOW, apply=True)
    assert len(events(backend)) == 2 and len(calls(backend)) == 2
    (only,) = backend.tables.partition_runs(retention.FEEDBACK, date(2026, 9, 2))
    assert only.startswith(retention.JOB)  # the erase of a real user supersedes both runs
    assert (events(backend)["user"] == "bea").sum() == 1


def test_after_a_real_retain_only_the_superseded_runs_of_rewritten_partitions_are_gone(
    backend: Backend,
) -> None:
    seed(backend)
    two_recorder_runs(backend)
    young = date(2026, 9, 2)
    young_runs = backend.tables.partition_runs(retention.FEEDBACK, young)
    old_runs = backend.tables.partition_runs(retention.FEEDBACK, date(2025, 6, 2))
    retention.retain(backend, NOW, apply=True)
    assert backend.tables.partition_runs(retention.FEEDBACK, young) == young_runs  # untouched
    now_old = backend.tables.partition_runs(retention.FEEDBACK, date(2025, 6, 2))
    assert len(now_old) == 1 and now_old[0].startswith(retention.JOB)
    assert not set(old_runs) & set(now_old)
    assert len(events(backend)) == 6


def test_purge_refuses_a_run_no_retention_run_supersedes(backend: Backend) -> None:
    two_recorder_runs(backend)
    day = date(2026, 9, 2)
    live = backend.tables.partition_runs(retention.FEEDBACK, day)
    with pytest.raises(RuntimeError, match="refusing"):
        retention._purge(backend, retention.FEEDBACK, day, live[:-1])
    assert backend.tables.partition_runs(retention.FEEDBACK, day) == live
