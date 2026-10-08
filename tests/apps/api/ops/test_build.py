"""The build identity: the running API's stamp against the served web's and the checkout's, the
2026-10-07 incident (a web built against a newer schema than the running API) first."""

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from algotrade_api.graphql.schema import sdl
from algotrade_api.ops import build
from algotrade_api.ops.build import (
    SCHEMA,
    STAMP,
    UNKNOWN,
    Stamp,
    api_stamp,
    build_status,
    checkout_stamp,
    git_sha,
    mismatches,
    read_web_stamp,
    running_mismatches,
    schema_hash,
    write_web_stamp,
)
from algotrade_api.ops.schedule import LABEL
from tests.conftest import REPO_ROOT

STARTED = datetime(2026, 10, 7, 12, 5, tzinfo=UTC)
BUILT = datetime(2026, 10, 7, 17, 55, tzinfo=UTC)
OLD_SCHEMA = "type FieldGuide {\n  name: String!\n}\n"
NEW_SCHEMA = "type FieldGuide {\n  name: String!\n  summary: String!\n}\n"


def checkout(tmp_path: Path, schema: str) -> Path:
    """A git checkout holding ``schema`` as its committed schema snapshot."""
    repo = tmp_path / "repo"
    (repo / SCHEMA).parent.mkdir(parents=True)
    (repo / SCHEMA).write_text(schema)
    git = ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run([*git[:3], "init", "-q"], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-qm", "x"], check=True)
    return repo


def commit(repo: Path, schema: str) -> None:
    (repo / SCHEMA).write_text(schema)
    git = ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run([*git, "commit", "-qam", "y"], check=True)


def test_a_web_built_after_the_api_started_against_a_new_schema_is_reported(
    tmp_path: Path,
) -> None:
    # 2026-10-07: the API started at 12:05; GD4a added FieldGuide.summary and make web-build
    # ran at 17:55; the old process served the new web and every catalogue query failed.
    repo = checkout(tmp_path, OLD_SCHEMA)
    api = api_stamp(OLD_SCHEMA, repo, STARTED)
    commit(repo, NEW_SCHEMA)
    dist = tmp_path / "web"
    dist.mkdir()
    write_web_stamp(dist, repo, BUILT)

    report = build_status(api, dist, repo)

    assert report.stale
    assert report.web is not None and report.web.schema_hash == schema_hash(NEW_SCHEMA)
    web_says, checkout_says = report.mismatches
    assert "fields the API lacks" in web_says
    assert "launchctl kickstart -k gui/" in web_says and LABEL in web_says
    assert str(SCHEMA.as_posix()) in checkout_says and "kickstart" in checkout_says


def test_an_api_restarted_after_the_build_is_in_step(tmp_path: Path) -> None:
    repo = checkout(tmp_path, NEW_SCHEMA)
    dist = tmp_path / "web"
    dist.mkdir()
    write_web_stamp(dist, repo, STARTED)
    report = build_status(api_stamp(NEW_SCHEMA, repo, BUILT), dist, repo)
    assert (report.stale, report.mismatches) == (False, ())


def test_a_web_older_than_the_api_asks_for_a_rebuild_not_a_restart() -> None:
    api = Stamp("b", schema_hash(NEW_SCHEMA), BUILT)
    web = Stamp("a", schema_hash(OLD_SCHEMA), STARTED)
    (said,) = mismatches(api, web, None, serves_web=True)
    assert "make web-build" in said and "kickstart" not in said


def test_a_served_web_without_its_stamp_was_built_outside_make_web_build(tmp_path: Path) -> None:
    api = Stamp("a", "h", STARTED)
    (said,) = mismatches(api, read_web_stamp(tmp_path), None, serves_web=True)
    assert STAMP in said and "make web-build" in said
    assert mismatches(api, None, None, serves_web=False) == ()


def test_a_pull_without_a_restart_is_reported_by_commit(tmp_path: Path) -> None:
    repo = checkout(tmp_path, OLD_SCHEMA)
    api = api_stamp(OLD_SCHEMA, repo, STARTED)
    (repo / "README").write_text("docs only")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "d"],
        check=True,
    )
    (said,) = build_status(api, None, repo).mismatches
    assert api.git_sha[:9] in said and "kickstart" in said


def test_unknown_commits_are_never_compared(tmp_path: Path) -> None:
    api = Stamp(UNKNOWN, "h", STARTED)
    assert mismatches(api, None, Stamp("abc", "h"), serves_web=False) == ()
    assert git_sha(tmp_path) == UNKNOWN
    assert checkout_stamp(tmp_path) is None
    with pytest.raises(FileNotFoundError):
        write_web_stamp(tmp_path, tmp_path)


def test_the_stamp_round_trips_and_a_broken_one_reads_as_none(tmp_path: Path) -> None:
    repo = checkout(tmp_path, OLD_SCHEMA)
    written = write_web_stamp(tmp_path, repo, BUILT)
    assert read_web_stamp(tmp_path) == written
    (tmp_path / STAMP).write_text("{not json")
    assert read_web_stamp(tmp_path) is None


def test_the_live_schema_hashes_as_the_committed_snapshot() -> None:
    # The API hashes its live SDL, the web stamp the committed file: one text, one hash.
    assert schema_hash(sdl()) == schema_hash((REPO_ROOT / SCHEMA).read_text())
    assert build.REPO == REPO_ROOT


def test_running_mismatches_reads_a_running_api() -> None:
    def health(build: object) -> bytes:
        return json.dumps({"status": "ok", "build": build}).encode()

    said = {"mismatches": ["restart"], "stale": True}
    assert running_mismatches("http://x", lambda url: health(said)) == ("restart",)
    assert running_mismatches("http://x", lambda url: health({"mismatches": []})) == ()

    def refused(url: str) -> bytes:
        raise ConnectionRefusedError

    assert running_mismatches("http://x", refused) is None
    (old,) = running_mismatches("http://x", lambda url: b'{"status": "ok"}') or ()
    assert "predates" in old and "kickstart" in old
