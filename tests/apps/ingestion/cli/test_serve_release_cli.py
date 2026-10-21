"""The ``serve-release`` command and the starts after a nightly and a post-session (ADR 0077)."""

import argparse
from pathlib import Path

import pytest

from algotrade_ingestion.cli import main as cli
from algotrade_ingestion.workflows.serve_release.serve_release import ServeOutcome, ServeStatus


class Calls:
    def __init__(self) -> None:
        self.runs: list[tuple[bool, bool]] = []
        self.outcome = ServeOutcome(ServeStatus.PROMOTED, "2026-10-02.7.f1")

    def serve(
        self,
        backend: object,
        releases: object,
        now: object,
        code: str,
        rebuild: bool = False,
        wait: bool = False,
    ) -> ServeOutcome:
        self.runs.append((rebuild, wait))
        return self.outcome


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Calls:
    monkeypatch.setenv("ALGOTRADE_DATA_URL", f"file://{tmp_path / 'data'}")
    monkeypatch.setattr(cli, "ensure_main_checkout", lambda: None)
    made = Calls()
    monkeypatch.setattr(cli, "serve_release", made.serve)
    return made


def test_the_command_runs_the_workflow_and_maps_its_outcome_to_an_exit_code(
    calls: Calls, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["serve-release"]) == 0
    assert cli.main(["serve-release", "--rebuild"]) == 0
    assert calls.runs == [(False, False), (True, False)]
    assert "promoted: 2026-10-02.7.f1" in capsys.readouterr().out
    calls.outcome = ServeOutcome(ServeStatus.BUSY, reason="locked")
    assert cli.main(["serve-release"]) == cli.LOCKED_EXIT
    calls.outcome = ServeOutcome(ServeStatus.FAILED, reason="over the ceiling")
    assert cli.main(["serve-release"]) == 2


def test_a_finished_nightly_starts_the_release_job_and_a_failed_one_does_not(
    calls: Calls, monkeypatch: pytest.MonkeyPatch
) -> None:
    codes = iter([0, 2])

    def ran(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
        args.ran_job = True
        return next(codes)

    monkeypatch.setattr(cli, "_run", ran)
    assert cli.main(["nightly"]) == 0
    assert cli.main(["nightly"]) == 2
    assert calls.runs == [(False, True)]  # started once, waiting for the serve lock, no rebuild


def test_a_nightly_that_found_nothing_to_do_starts_nothing(
    calls: Calls, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_run", lambda parser, args: 0)  # the quiet no-op sets no ran_job
    assert cli.main(["nightly"]) == 0
    assert calls.runs == []


def test_a_post_session_that_ran_asks_for_release_r2_and_a_no_op_one_does_not(
    calls: Calls, monkeypatch: pytest.MonkeyPatch
) -> None:
    def ran(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
        args.ran_job = True
        return 0

    monkeypatch.setattr(cli, "_run", ran)
    assert cli.main(["post-session"]) == 0
    monkeypatch.setattr(cli, "_run", lambda parser, args: 0)
    assert cli.main(["post-session"]) == 0
    assert calls.runs == [(True, True), (False, True)]


def test_a_release_that_cannot_start_never_changes_the_nightlys_exit_code(
    calls: Calls, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def ran(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
        args.ran_job = True
        return 0

    monkeypatch.setattr(cli, "_run", ran)

    def boom(*args: object, **kwargs: object) -> ServeOutcome:
        raise cli.AlgoTradeError("no store")

    monkeypatch.setattr(cli, "serve_release", boom)
    assert cli.main(["nightly"]) == 0
    assert "serve-release not started: no store" in capsys.readouterr().err
