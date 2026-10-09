"""The deploy hold (ADR 0057): busy while the ingest or the deploy lock is taken, else the
command runs and its exit code passes through."""

from pathlib import Path

import pytest

from algotrade.services.jobs import INGEST_LOCK
from algotrade.storage.backends.local import LocalBackend
from algotrade_ingestion.cli import main as cli
from algotrade_ingestion.ops.hold import BUSY, DEPLOY_LOCK, hold


def test_hold_runs_when_nothing_is_taken(tmp_path: Path) -> None:
    assert hold(LocalBackend(tmp_path), lambda: 7) == 7


@pytest.mark.parametrize("name", [INGEST_LOCK, DEPLOY_LOCK])
def test_hold_is_busy_while_another_process_holds_a_lock(tmp_path: Path, name: str) -> None:
    other = LocalBackend(tmp_path).lock(name)  # another FileLock on the same file, as a process
    assert other.acquire(wait=False)
    try:
        assert hold(LocalBackend(tmp_path), lambda: pytest.fail("must not run")) == BUSY
    finally:
        other.release()
    assert hold(LocalBackend(tmp_path), lambda: 0) == 0  # and releases what it took


def test_hold_releases_the_deploy_lock_when_the_ingest_lock_is_taken(tmp_path: Path) -> None:
    backend = LocalBackend(tmp_path)
    ingest = backend.lock(INGEST_LOCK)
    assert ingest.acquire(wait=False)
    try:
        assert hold(backend, lambda: 0) == BUSY
        free = LocalBackend(tmp_path).lock(DEPLOY_LOCK)
        assert free.acquire(wait=False)
        free.release()
    finally:
        ingest.release()


def test_the_cli_passes_the_exit_code_through_and_is_not_an_ingest_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setenv("ALGOTRADE_DATA_URL", f"file://{tmp_path}/data")
    assert cli.main(["deploy-hold", "--", "sh", "-c", "exit 3"]) == 3
    held = LocalBackend(tmp_path / "data").lock(INGEST_LOCK)
    assert held.acquire(wait=False)
    try:
        assert cli.main(["deploy-hold", "--", "sh", "-c", "exit 0"]) == BUSY
    finally:
        held.release()


def test_deploy_only_runs_while_the_ingest_lock_is_held(tmp_path: Path) -> None:
    ingest = LocalBackend(tmp_path).lock(INGEST_LOCK)
    assert ingest.acquire(wait=False)
    try:
        assert hold(LocalBackend(tmp_path), lambda: 4, ingest=False) == 4
    finally:
        ingest.release()


def test_deploy_only_is_still_busy_while_the_deploy_lock_is_held(tmp_path: Path) -> None:
    other = LocalBackend(tmp_path).lock(DEPLOY_LOCK)
    assert other.acquire(wait=False)
    try:
        busy = hold(LocalBackend(tmp_path), lambda: pytest.fail("must not run"), ingest=False)
        assert busy == BUSY
    finally:
        other.release()


def test_the_cli_deploy_only_flag_skips_the_ingest_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setenv("ALGOTRADE_DATA_URL", f"file://{tmp_path}/data")
    held = LocalBackend(tmp_path / "data").lock(INGEST_LOCK)
    assert held.acquire(wait=False)
    try:
        assert cli.main(["deploy-hold", "--deploy-only", "--", "sh", "-c", "exit 3"]) == 3
    finally:
        held.release()
