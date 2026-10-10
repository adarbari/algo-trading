"""The site's trial log reads the records of the legacy owners (``LEGACY_SITE_OWNERS``) from before
``LEGACY_SITE_CUTOFF`` as its own, each trial once."""

from datetime import UTC, datetime

from algotrade.services.evaluation.cross_section.harness import _prior_trials


def test_the_sites_trial_log_includes_the_legacy_local_runs() -> None:
    class Record:
        def __init__(self, hash_: str) -> None:
            self.stats = {"trials": [{"variant": "momo", "config_hash": hash_, "horizon": 2}]}
            self.finished_at = self.started_at = datetime(2026, 10, 5, tzinfo=UTC)

    class Writer:
        def runs_for(self, job: str) -> list[Record]:
            known = {"edge-eval:drift:site": "a", "edge-eval:drift:local": "b"}
            return [Record(known[job])] if job in known else []

    seen = _prior_trials(Writer(), "drift", "site")  # type: ignore[arg-type]
    assert seen == {("main", "momo", "a", 2), ("main", "momo", "b", 2)}
    assert _prior_trials(Writer(), "drift", "alice") == set()  # a user's log is their own


def test_the_legacy_log_counts_a_trial_once_and_only_before_the_cutoff() -> None:
    class Record:
        def __init__(self, at: datetime) -> None:
            self.stats = {"trials": [{"variant": "momo", "config_hash": "h", "horizon": 2}]}
            self.finished_at, self.started_at = at, at

    before = datetime(2026, 10, 5, tzinfo=UTC)
    after = datetime(2026, 10, 12, tzinfo=UTC)

    class Writer:
        def runs_for(self, job: str) -> list[Record]:
            return [Record(before)] if job.endswith(":site") else [Record(before), Record(after)]

    assert _prior_trials(Writer(), "drift", "site") == {("main", "momo", "h", 2)}  # once

    class Later:
        def runs_for(self, job: str) -> list[Record]:
            return [] if job.endswith(":site") else [Record(after)]

    assert _prior_trials(Later(), "drift", "site") == set()  # a local run after the cutoff
