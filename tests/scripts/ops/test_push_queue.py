"""`scripts/ops/push_queue.py`: ordering, stale cleanup, slot limit, priority counting and the
`gh` failure fallback. Regression for the 2026-11-02 overload: five `make changed` at once."""

import importlib.util
import json
import os
import subprocess
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "ops" / "push_queue.py"
spec = importlib.util.spec_from_file_location("push_queue", SCRIPT)
assert spec and spec.loader
pq = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pq)


def t(pid: int, priority: int, at: float) -> dict:
    return {"pid": pid, "branch": f"b{pid}", "pr": None, "priority": priority, "enqueued_at": at}


def test_order_is_priority_desc_then_fifo() -> None:
    ordered = pq.order_tickets([t(1, 0, 1.0), t(2, 2, 3.0), t(3, 2, 2.0), t(4, 1, 0.5)])
    assert [x["pid"] for x in ordered] == [3, 2, 4, 1]


def test_a_later_push_with_more_dependants_goes_first() -> None:
    tickets = [t(1, 0, 1.0), t(2, 3, 9.0)]
    assert pq.may_run(2, tickets, busy_slots=1, slots=2)
    assert not pq.may_run(1, tickets, busy_slots=1, slots=2)


def test_slot_limit() -> None:
    assert not pq.may_run(1, [t(1, 0, 1.0)], busy_slots=2, slots=2)
    assert pq.may_run(1, [t(1, 0, 1.0)], busy_slots=1, slots=2)


def test_stale_by_dead_pid_or_age() -> None:
    now = 10_000.0
    assert pq.is_stale(t(1, 0, now), now, lambda pid: False)
    assert pq.is_stale(t(1, 0, now - pq.STALE_SECONDS - 1), now, lambda pid: True)
    assert not pq.is_stale(t(1, 0, now), now, lambda pid: True)


def test_stale_files_are_removed_and_live_kept(tmp_path: Path) -> None:
    dead = subprocess.Popen(["true"])
    dead.wait()
    (tmp_path / f"ticket.{dead.pid}.json").write_text(json.dumps(t(dead.pid, 0, time.time())))
    (tmp_path / "ticket.live.json").write_text(json.dumps(t(os.getpid(), 0, time.time())))
    slot = tmp_path / "slot.0"
    slot.mkdir()
    (slot / "ticket.json").write_text(json.dumps(t(dead.pid, 0, time.time())))
    assert [x["pid"] for x in pq._live(tmp_path, "ticket.*.json", time.time())] == [os.getpid()]
    assert pq._live(tmp_path, "slot.*", time.time()) == []
    assert not slot.exists()


PRS = [
    {"number": 10, "headRefName": "mine", "baseRefName": "main", "body": ""},
    {"number": 11, "headRefName": "child", "baseRefName": "mine", "body": ""},
    {"number": 12, "headRefName": "other", "baseRefName": "main", "body": "Stacked on #10"},
    {"number": 13, "headRefName": "grand", "baseRefName": "child", "body": "x"},
    {"number": 14, "headRefName": "near", "baseRefName": "main", "body": "this NEEDS #100"},
    {
        "number": 15,
        "headRefName": "w",
        "baseRefName": "main",
        "body": "Waits on #10 and depends on #10",
    },
    {"number": 16, "headRefName": "d", "baseRefName": "main", "body": "unrelated"},
]


def test_priority_counts_stacked_and_named_once() -> None:
    # 11 by base, 12 and 15 by body (15 twice, once), 13 by descendant ref; 14 names #100 only
    assert pq.count_dependants(10, PRS, {"grand"}, "mine") == 4


def test_no_pr_yet_counts_only_stacked_branches() -> None:
    assert pq.count_dependants(None, PRS, {"grand"}, "newbranch") == 1


def test_gh_failure_gives_zero_with_a_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(args: list[str]) -> str:
        if args[0] == "git":
            return "mine\n"
        raise subprocess.TimeoutExpired(args, 1)

    monkeypatch.setattr(pq, "_run", fake)
    monkeypatch.delenv("PUSH_PRIORITY", raising=False)
    priority, _pr, reason = pq.compute_priority()
    assert priority == 0 and "unavailable" in reason


def test_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pq, "_run", lambda args: "mine\n" if args[0] == "git" else '{"number": 7}')
    monkeypatch.setenv("PUSH_PRIORITY", "5")
    assert pq.compute_priority() == (5, 7, "PUSH_PRIORITY")


def test_an_unblocks_line_counts_each_id_once_beside_the_open_dependants() -> None:
    body = "What\n\nUnblocks: V10, v11, O3, V10, #7\n"
    assert pq.parse_unblocks(body) == {"V10", "V11", "O3", "#7"}
    prs = [{"number": 8, "headRefName": "x", "baseRefName": "main", "body": "Depends on #5"}]
    # one open dependant (#8) + four distinct unblocked ids
    assert pq.count_dependants(5, prs, own_ref="mine", own_body=body) == 5
    # a #N that is already an open dependant, or the PR itself, is not counted twice
    twice = "Unblocks: #8, #5, V1"
    assert pq.count_dependants(5, prs, own_ref="mine", own_body=twice) == 2


def test_unblocks_ignores_prose_and_missing_bodies() -> None:
    assert pq.parse_unblocks(None) == set()
    assert pq.parse_unblocks("Unblocks:\nUnblocks: nothing yet, none") == set()
    assert pq.parse_unblocks("This unblocks V4 maybe") == set()
    assert pq.count_dependants(None, [], own_body="unblocks: S2, S3") == 2
