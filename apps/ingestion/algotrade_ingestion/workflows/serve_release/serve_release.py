"""Build, promote and prune the serving release (ADR 0077 decisions 2-5), under the ``serve`` lock.

``serve_release`` is the whole job: it does nothing while CURRENT already serves the default
session with every input still at its recorded stamp (the hourly watchdog and a nightly that
changed nothing are no-ops; a same-session restatement is not; ``rebuild`` builds anyway,
which is what the post-session start asks for: release r2 of the same session), else
builds the release of the default session at one pinned sequence, promotes it unless CURRENT
already names it, and prunes (which records what the pins hold). It is not the nightly's last
step: the nightly starts it after it released the ingest lock, so a failed release neither holds
back sessions nor triggers the hourly retry. A failure of any kind leaves CURRENT where it was
(the build only becomes visible at ``promote``) and is recorded as a FAILED ``serve-release`` run.
A backfill of an older date does not make CURRENT stale (only the session's own inputs are
compared): it ships with the next session's release.
"""

import subprocess
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from algotrade.data import StoreReader
from algotrade.services.jobs import RunLockedError, exclusive_run
from algotrade.services.read.session import default_session
from algotrade.services.serving.build import build_release
from algotrade.storage.backends.release.interfaces import ReleaseError, ReleaseStore
from algotrade.storage.runs import RunStatus, start_run
from algotrade.storage.tables.interfaces import Backend

JOB = "serve-release"
SERVE_LOCK = "serve"
KEEP_SESSIONS = 2  # with the current release: the newest release of the last two sessions


class ServeStatus(StrEnum):
    PROMOTED = "promoted"  # a release was built and is now the one served
    CURRENT = "current"  # CURRENT already serves the default session: nothing to do
    BUSY = "busy"  # another serve-release run holds the lock
    FAILED = "failed"  # recorded; CURRENT unchanged


@dataclass(frozen=True)
class ServeOutcome:
    status: ServeStatus
    release_id: str = ""
    reason: str = ""


def git_head(repo: Path) -> str:
    """The commit this code runs from (``unknown`` when git cannot say): the manifest's
    ``code_sha``."""
    try:
        done = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return done.stdout.strip() or "unknown"


def serve_release(
    backend: Backend,
    releases: ReleaseStore,
    now: datetime,
    code_sha: str,
    rebuild: bool = False,
    wait: bool = False,
) -> ServeOutcome:
    """One serve-release run (see the module docstring). Never raises for a failed build."""
    try:
        with exclusive_run(backend, SERVE_LOCK, wait=wait):
            return _locked(backend, releases, now, code_sha, rebuild)
    except RunLockedError as exc:
        return ServeOutcome(ServeStatus.BUSY, reason=str(exc))


def _serving_now(reader: StoreReader, releases: ReleaseStore) -> str | None:
    """The release CURRENT serves when it is fresh: for the default session and every input
    partition it was built from still has the stamp it recorded (a same-session restatement
    ships; a backfill of an older date waits for the next session's release), else ``None``."""
    day = default_session(reader)
    try:
        current = releases.current_release()
    except ReleaseError:
        return None
    if day is None or current is None or current.manifest.session != day.isoformat():
        return None
    for item in current.manifest.inputs:
        for held, stamp in item.partitions.items():
            if reader.partition_seq(item.table, held, held).get(held) != stamp:
                return None
    return current.manifest.release_id


def _locked(
    backend: Backend, releases: ReleaseStore, now: datetime, code_sha: str, rebuild: bool
) -> ServeOutcome:
    reader = StoreReader(backend)
    serving = None if rebuild else _serving_now(reader, releases)
    if serving is not None:
        return ServeOutcome(ServeStatus.CURRENT, serving)
    record = start_run(JOB, default_session(reader) or now.date(), now)
    backend.runs.save(record)
    try:
        manifest = build_release(reader, releases, code_sha)
        if releases.current() != (manifest.release_id, manifest.content_hash):
            releases.promote(manifest.release_id)
        releases.prune(KEEP_SESSIONS)
    except Exception as exc:
        record.status, record.finished_at = RunStatus.FAILED, now
        record.stats = {"error": str(exc), "code_sha": code_sha}
        backend.runs.save(record)
        return ServeOutcome(ServeStatus.FAILED, reason=str(exc))
    record.finish(now, stats={"release_id": manifest.release_id, "code_sha": code_sha})
    backend.runs.save(record)
    return ServeOutcome(ServeStatus.PROMOTED, manifest.release_id)
