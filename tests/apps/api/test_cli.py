"""``algotrade-api``: the open-files limit it serves with; ``stamp-web``: the build stamped, and
the running API's state said."""

import json
import resource
from datetime import UTC, datetime
from pathlib import Path

import pytest

from algotrade.config.site.users import UsersSettings
from algotrade.services.feedback import retention
from algotrade.services.feedback.events import row_of
from algotrade.services.feedback.recorder import FeedbackRecorder
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.tables.feedback_writer import FeedbackWriter
from algotrade_api import cli
from algotrade_api.ops.build import STAMP
from algotrade_api.ops.schedule import OPEN_FILES


def test_stamp_web_stamps_the_build_and_warns_when_the_api_is_behind(tmp_path: Path) -> None:
    stale = {"build": {"mismatches": ["restart the API: launchctl kickstart -k x"]}}
    lines = cli.stamp_web(tmp_path, 8000, lambda url: json.dumps(stale).encode())
    assert (tmp_path / STAMP).is_file() and lines[0].startswith(f"stamped {tmp_path}")
    assert lines[1:] == [
        "WARNING: the API at http://127.0.0.1:8000 is out of step:",
        "  - restart the API: launchctl kickstart -k x",
    ]
    in_step = cli.stamp_web(tmp_path, 8000, lambda url: b'{"build": {"mismatches": []}}')
    assert "serves this build" in in_step[-1]


def test_stamp_web_without_an_api_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def refused(url: str) -> bytes:
        raise ConnectionRefusedError

    assert cli.stamp_web(tmp_path, 8123, refused)[-1] == "no API answering at http://127.0.0.1:8123"


def _limits(monkeypatch: pytest.MonkeyPatch, soft: int, hard: int) -> list[tuple[int, int]]:
    """Stub the process's open-files limits at ``(soft, hard)``; the limits set, recorded."""
    set_to: list[tuple[int, int]] = []
    monkeypatch.setattr(cli.resource, "getrlimit", lambda kind: (soft, hard))
    monkeypatch.setattr(cli.resource, "setrlimit", lambda kind, limits: set_to.append(limits))
    return set_to


def test_serving_lifts_launchds_256_open_files_soft_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    # the agent installed before its plist set NumberOfFiles still starts at 256 (2026-10-08)
    set_to = _limits(monkeypatch, 256, resource.RLIM_INFINITY)
    assert cli.raise_open_files() == OPEN_FILES
    assert set_to == [(OPEN_FILES, resource.RLIM_INFINITY)]


def test_the_open_files_limit_stays_within_the_hard_limit_and_is_never_lowered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_to = _limits(monkeypatch, 256, 1024)
    assert cli.raise_open_files() == 1024 and set_to == [(1024, 1024)]
    set_to = _limits(monkeypatch, 65536, resource.RLIM_INFINITY)
    assert cli.raise_open_files() == 65536 and set_to == []


def test_serving_raises_the_limit_before_uvicorn_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    order: list[str] = []
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(cli, "raise_open_files", lambda: order.append("limit") or OPEN_FILES)
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kw: order.append("serve"))
    cli.main([])
    assert order == ["limit", "serve"]


def test_golden_run_parses_its_flags_and_exits_with_the_command_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[object] = []
    monkeypatch.setattr(cli, "golden_run", lambda args: seen.append(args) or 7)
    with pytest.raises(SystemExit) as stop:
        cli.main(
            ["golden", "run", "--cases", "a,b", "--split", "held_out", "--provider", "x",
             "--provider", "y", "--repeat", "2", "--record", "--json", "--yes"]
        )  # fmt: skip
    assert stop.value.code == 7
    ns = seen[0]
    assert (ns.cases, ns.split, ns.provider, ns.repeat) == ("a,b", "held_out", ["x", "y"], 2)  # type: ignore[attr-defined]
    assert (ns.record, ns.as_json, ns.yes, ns.max_calls, ns.budget_usd) == (  # type: ignore[attr-defined]
        True, True, True, 60, 1.0,
    )  # fmt: skip


def test_feedback_commands_are_a_dry_run_until_yes_and_audit_only_what_they_applied(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    url = f"file://{tmp_path / 'data'}"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(cli, "data_url", lambda: url)
    rec = FeedbackRecorder(FeedbackWriter(LocalBackend(tmp_path / "data")))
    rec.submit(row_of("draft_requested", "s", "abhi", "screen", "x", sentence="private"))
    rec.flush()
    rec.close()
    audit = tmp_path / "audit" / "feedback-retention.log"
    monkeypatch.setattr(retention, "AUDIT_LOG", audit)  # the real one is the repo's
    for argv in (
        ["feedback", "erase", "--user", "abhi"],
        ["feedback", "erase", "--user", "abhi", "--dry-run"],
    ):
        with pytest.raises(SystemExit) as stop:
            cli.main(argv)
        assert stop.value.code == 0 and not audit.exists()
    assert "dry run" in capsys.readouterr().out
    with pytest.raises(SystemExit) as stop:
        cli.main(["feedback", "erase", "--user", "abhi", "--dry-run", "--yes"])
    assert stop.value.code == 2 and not audit.exists()
    with pytest.raises(SystemExit) as stop:
        cli.main(["feedback", "erase", "--user", "abhi", "--yes"])
    out = capsys.readouterr().out
    assert (
        stop.value.code == 0 and "reminder: backups" in out and "private" not in audit.read_text()
    )
    with pytest.raises(SystemExit) as stop:
        cli.main(["feedback", "retain", "--older-than-days", "30", "--yes"])
    assert stop.value.code == 0 and len(audit.read_text().splitlines()) == 2


def test_golden_candidates_and_curate_parse_and_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[object] = []
    monkeypatch.setattr(cli, "golden_candidates_cmd", lambda args: seen.append(args) or 0)
    monkeypatch.setattr(cli, "golden_curate_cmd", lambda args: seen.append(args) or 3)
    with pytest.raises(SystemExit) as stop:
        cli.main(["golden", "candidates", "--user", "u", "--limit", "5", "--json"])
    assert stop.value.code == 0
    with pytest.raises(SystemExit) as stop:
        cli.main(["golden", "curate", "--from", "c.json", "--dry-run"])
    assert stop.value.code == 3
    cand, cur = seen
    assert (cand.user, cand.limit, cand.per_user_month, cand.as_json) == ("u", 5, 5, True)  # type: ignore[attr-defined]
    assert (str(cur.source), cur.dry_run, cur.yes) == ("c.json", True, False)  # type: ignore[attr-defined]


def _rows() -> list[dict[str, object]]:
    ts = datetime(2026, 10, 1, tzinfo=UTC)
    final = {"criteria": {"c1": {"field": "feature.pe_ratio", "op": "lt", "value": 15}}}
    base = {"draft_session_id": "s", "user": "u", "doc_id": "d", "ts": ts}
    return [
        {**base, "event_id": "r", "event": "draft_requested", "sentence": "cheap on earnings",
         "payload": None},
        {**base, "event_id": "f", "event": "screen_finalised", "sentence": None,
         "payload": json.dumps({"saved_criteria": final})},
    ]  # fmt: skip


def test_golden_candidates_prints_the_cards(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "drafting_rows", lambda since: (_rows(), False))
    args = cli._parser().parse_args(["golden", "candidates", "--json"])
    assert cli.golden_candidates_cmd(args) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["candidates"][0]["chain_id"] == "f" and out["coverage"]["groups"] == {"feature": 1}


def test_golden_curate_needs_yes_to_write_and_refuses_a_copied_sentence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "drafting_rows", lambda since: (_rows(), False))
    monkeypatch.setattr(cli, "open_store", lambda *a: type("S", (), {"configs": None})())
    monkeypatch.setattr(cli, "resolve_rule_draft", lambda *a: None)
    src = tmp_path / "c.json"
    src.write_text(json.dumps([{"source_event": "f", "sentences": ["valuation looks low"]}]))

    def run(*flags: str) -> int:
        return cli.golden_curate_cmd(
            cli._parser().parse_args(["golden", "curate", "--from", str(src), *flags])
        )

    assert run("--dry-run") == 0 and run() == 2
    assert not list(tmp_path.rglob("golden-*.json"))
    assert run("--yes") == 0
    (written,) = tmp_path.rglob("golden-*.json")
    assert json.loads(written.read_text())["source_event"] == "f"
    src.write_text(json.dumps([{"source_event": "f", "sentences": ["Cheap on earnings"]}]))
    assert run("--yes") == 1 and "copies a real sentence" in capsys.readouterr().err


def test_golden_curate_refuses_when_the_read_hit_its_cap(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "drafting_rows", lambda since: (_rows(), True))
    monkeypatch.setattr(cli, "open_store", lambda *a: type("S", (), {"configs": None})())
    src = tmp_path / "c.json"
    src.write_text(json.dumps([{"source_event": "f", "sentences": ["valuation looks low"]}]))
    args = cli._parser().parse_args(["golden", "curate", "--from", str(src), "--yes"])
    assert cli.golden_curate_cmd(args) == 1 and "the cap" in capsys.readouterr().err


def test_golden_candidates_warn_on_a_capped_read_and_need_an_admin(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "drafting_rows", lambda since: (_rows(), True))
    args = cli._parser().parse_args(["golden", "candidates"])
    assert cli.golden_candidates_cmd(args) == 0
    assert "newest 500 events only" in capsys.readouterr().err
    monkeypatch.undo()
    monkeypatch.setenv("ALGOTRADE_USER", "nobody")
    monkeypatch.setattr(cli, "open_store", lambda *a: type("S", (), {"configs": None})())
    users = {"user": [{"id": "boss", "role": "admin"}, {"id": "nobody", "role": "trader"}]}
    monkeypatch.setattr(cli, "load_users", lambda configs: UsersSettings.from_document(users))
    assert cli.golden_candidates_cmd(args) == 1
    assert "need an admin" in capsys.readouterr().err
