"""The option-history root (ADR 0084): no URL, no folder, no sentinel are each an error that names
the fix, and a drive that is not mounted is never created on the boot disk."""

from pathlib import Path

import pytest

from algotrade.config import env
from algotrade.data.option_history.store import (
    SENTINEL,
    HistoryUnavailableError,
    init_root,
    open_history,
)


def url(path: Path) -> str:
    return f"file://{path}"


def test_no_url_is_unavailable_with_the_variable_named() -> None:
    with pytest.raises(HistoryUnavailableError, match="ALGOTRADE_OPTION_HISTORY_URL"):
        open_history(None)


def test_an_unmounted_drive_is_an_error_and_nothing_is_created(tmp_path: Path) -> None:
    gone = tmp_path / "Volumes" / "drive" / "option-history"
    with pytest.raises(HistoryUnavailableError, match="mounted"):
        open_history(url(gone))
    with pytest.raises(HistoryUnavailableError, match="mounted"):
        init_root(url(gone))
    assert not (tmp_path / "Volumes").exists()


def test_a_directory_without_the_sentinel_is_refused_until_it_is_initialised(
    tmp_path: Path,
) -> None:
    with pytest.raises(HistoryUnavailableError, match="--init"):
        open_history(url(tmp_path))
    assert init_root(url(tmp_path)) == tmp_path
    assert (tmp_path / SENTINEL).is_file()
    assert sorted(p.name for p in tmp_path.iterdir()) == [SENTINEL]  # the probe left nothing
    assert open_history(url(tmp_path)) is not None


def test_a_memory_store_needs_no_sentinel() -> None:
    assert open_history("memory://") is not None


def test_the_environment_getter_has_no_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(env.OPTION_HISTORY_URL, raising=False)
    assert env.option_history_url() is None
    monkeypatch.setenv(env.OPTION_HISTORY_URL, " file:///Volumes/x/h ")
    assert env.option_history_url() == "file:///Volumes/x/h"
    assert env.option_history_url("memory://") == "memory://"
