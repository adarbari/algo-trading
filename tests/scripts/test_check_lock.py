"""`scripts/check_lock.py`: one `make check` at a time; the second waits and says who holds it."""

import subprocess
import sys
import time
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_lock.py"


def _run(lock: Path, *command: str) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, str(SCRIPT), "--lock", str(lock), "--", *command],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_the_second_check_waits_for_the_first_and_names_it(tmp_path: Path) -> None:
    lock = tmp_path / "check.lock"
    first = _run(lock, sys.executable, "-c", "import time; time.sleep(1.5)")
    time.sleep(0.5)
    assert "pid" in lock.read_text(encoding="utf-8") and "since" in lock.read_text(encoding="utf-8")
    started = time.monotonic()
    second = _run(lock, sys.executable, "-c", "print('ran')")
    out, err = second.communicate(timeout=30)
    waited = time.monotonic() - started
    first.communicate(timeout=30)
    assert first.returncode == 0
    assert second.returncode == 0 and out.strip() == "ran"
    assert waited > 0.5, "the second check did not wait for the first"
    assert "waiting for the lock held by pid" in err
    assert lock.read_text(encoding="utf-8") == ""


def test_the_command_exit_code_is_returned_and_the_lock_released(tmp_path: Path) -> None:
    lock = tmp_path / "check.lock"
    proc = _run(lock, sys.executable, "-c", "raise SystemExit(3)")
    _, err = proc.communicate(timeout=30)
    assert proc.returncode == 3 and "waiting" not in err
    again = _run(lock, sys.executable, "-c", "pass")
    _, err = again.communicate(timeout=30)
    assert again.returncode == 0 and "waiting" not in err


def test_no_command_is_a_usage_error(tmp_path: Path) -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--lock", str(tmp_path / "l"), "--"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2 and "no command" in proc.stderr
