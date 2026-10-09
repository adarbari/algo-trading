"""``write_draft``: a candidate edge draft only from a winners study run that passed the gate,
outside ``config/site``, written whole or not at all."""

import tomllib
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.services.evaluation.discovery.drafts import DRAFT_HORIZON, write_draft
from algotrade.services.evaluation.discovery.persist import write_winners_study
from algotrade.services.evaluation.discovery.tells import find_tells
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.result_writer import ResultWriter
from tests.unit.services.evaluation.discovery.conftest import settings
from tests.unit.services.evaluation.discovery.test_tells import frames, independent

NOW = datetime(2026, 10, 9, 12, tzinfo=UTC)


def stored(passed: bool = True) -> tuple[ResultWriter, str]:
    found = find_tells(frames(independent), settings(permutations=10))
    assert found.passed
    backend = MemoryBackend()
    writer = ResultWriter(backend)
    return writer, write_winners_study(writer, replace(found, passed=passed), NOW).run_id


def test_a_passing_run_writes_a_candidate_draft_with_todos_and_a_short_outcome(
    tmp_path: Path,
) -> None:
    writer, run_id = stored()
    path = write_draft(writer, run_id, tmp_path / "var" / "edge_drafts")
    doc = tomllib.loads(path.read_text())
    assert doc["status"] == "candidate" and doc["frozen_from"].isoformat() == "2026-04-01"
    assert doc["outcome"]["horizon_sessions"] == [DRAFT_HORIZON] and DRAFT_HORIZON in (63, 252)
    assert 504 not in doc["outcome"]["horizon_sessions"]
    answers = [doc["mechanism"], doc["persistence"], *doc["quality_bar"].values()]
    assert len(answers) == 9 and set(answers) == {"TODO"}
    assert "[criteria.tell_1]" in path.read_text()
    assert [p.name for p in path.parent.iterdir()] == [path.name]  # no temp file left


def test_drafts_outside_config_site(tmp_path: Path) -> None:
    """A draft is never written under ``config/site`` (the owner moves a reviewed one by hand);
    the default goes to ``var/edge_drafts``. Catches: a draft landing in the site config, where
    it would be read as a real edge."""
    writer, run_id = stored()
    config = tmp_path / "config"
    for bad in (config / "site" / "edges", config / "site"):
        with pytest.raises(ConfigurationError, match="never go under"):
            write_draft(writer, run_id, bad, config)
        assert not bad.exists()
    ok = write_draft(writer, run_id, tmp_path / "var" / "edge_drafts", config)
    assert (tmp_path / "config" / "site") not in ok.parents


def test_a_run_that_failed_the_gate_writes_nothing(tmp_path: Path) -> None:
    """Catches: a draft written for a study that found nothing."""
    writer, run_id = stored(passed=False)
    out = tmp_path / "drafts"
    with pytest.raises(ConfigurationError, match="did not pass the gate"):
        write_draft(writer, run_id, out)
    assert not out.exists()


def test_an_unknown_run_or_another_jobs_run_writes_nothing(tmp_path: Path) -> None:
    writer, _ = stored()
    with pytest.raises(ConfigurationError, match="not a winners study run"):
        write_draft(writer, "nope", tmp_path / "d")
    assert not (tmp_path / "d").exists()


def test_draft_refuses_version_1_run(tmp_path: Path) -> None:
    """Catches: a draft from a run before W4 (controls matched on two variables, no
    winners-vs-losers gate), like the first real run that passed on volatility tells."""
    writer, run_id = stored()
    record = writer.load_run(run_id)
    assert record is not None
    record.stats["table_version"] = 1
    writer.save_run(record)
    out = tmp_path / "drafts"
    with pytest.raises(ConfigurationError, match="version 1 winners study run"):
        write_draft(writer, run_id, out)
    assert not out.exists()
