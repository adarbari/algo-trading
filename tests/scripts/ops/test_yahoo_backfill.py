"""`scripts/ops/yahoo_backfill.sh`: loops the one-batch task until nothing is due, waits (and
retries) on a held lock, an incomplete nightly and a 429, and stops on a stall or an error."""

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "ops" / "yahoo_backfill.sh"
BATCH = '{"progress": %d, "due_remaining": %d, "rate_limited": %s}'


def drive(tmp_path: Path, replies: list[tuple[int, str]]) -> tuple[int, str]:
    """Run the loop over a stub ingest command replaying ``replies`` (exit code, stdout)."""
    script = ['n=$(($(cat "$0.n" 2>/dev/null || echo 0) + 1)); echo $n >"$0.n"', "case $n in"]
    for i, (code, out) in enumerate(replies, 1):
        script.append(f"  {i}) echo '{out}'; exit {code};;")
    script.append("  *) exit 9;; esac")
    stub = tmp_path / "ingest"
    stub.write_text("#!/bin/sh\n" + "\n".join(script) + "\n")
    stub.chmod(0o755)
    env = {
        **os.environ,
        "YAHOO_BACKFILL_CMD": str(stub),
        "YAHOO_BACKFILL_LOGS": str(tmp_path / "logs"),
        "YAHOO_BACKFILL_PAUSE": "0",
        "YAHOO_BACKFILL_LOCKED": "0",
        "YAHOO_BACKFILL_WAIT": "0",
        "YAHOO_BACKFILL_COOLDOWNS": "0 0 0",
    }
    done = subprocess.run(
        [str(SCRIPT)], check=False, env=env, capture_output=True, text=True, timeout=60
    )
    return done.returncode, (tmp_path / "logs" / "yahoo-backfill.status").read_text()


def test_it_runs_batches_until_nothing_is_due(tmp_path: Path) -> None:
    code, status = drive(
        tmp_path, [(0, BATCH % (300, 500, "false")), (0, BATCH % (200, 0, "false"))]
    )
    assert code == 0 and status.startswith("state=done batches=2 due=0")


def test_it_waits_out_a_held_lock_an_incomplete_nightly_and_a_429(tmp_path: Path) -> None:
    replies = [
        (3, ""),  # the nightly holds the ingest lock
        (0, '{"waiting": "the nightly of 2026-10-16 is not complete", "due_remaining": null}'),
        (0, BATCH % (10, 90, "true")),  # a 429 stopped the batch
        (0, BATCH % (90, 0, "false")),
    ]
    code, status = drive(tmp_path, replies)
    assert code == 0 and status.startswith("state=done batches=2 due=0")  # only real batches count


def test_three_429s_in_a_row_block_it_and_a_clean_batch_resets_the_count(tmp_path: Path) -> None:
    limited = (0, BATCH % (5, 90, "true"))
    clean = (0, BATCH % (50, 40, "false"))
    code, status = drive(tmp_path, [limited, limited, clean, limited, limited, limited])
    assert code == 1 and status.startswith("state=blocked batches=6 due=90")


def test_three_batches_that_answer_nothing_stall_it(tmp_path: Path) -> None:
    code, status = drive(tmp_path, [(1, BATCH % (0, 50, "false"))] * 3)
    assert code == 1 and status.startswith("state=stalled batches=3 due=50")


def test_a_batch_that_cannot_run_ends_it_with_its_exit_code(tmp_path: Path) -> None:
    code, status = drive(tmp_path, [(2, "")])
    assert code == 2 and status.startswith("state=error exit=2")
