"""The site's trial log reads the records of the legacy owners (``LEGACY_SITE_OWNERS``) from before
``LEGACY_SITE_CUTOFF`` as its own, each trial once; a trial's statistics read the series its
unit calls for."""

from datetime import UTC, date, datetime, timedelta

import pytest

from algotrade.quant.edges.statistics import sharpe
from algotrade.services.evaluation.cross_section.detail.windows import SeriesFacts
from algotrade.services.evaluation.cross_section.harness import (
    VariantResult,
    _prior_trials,
    _slice_rows,
)
from algotrade.services.evaluation.cross_section.measures import SessionStat


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


def test_a_cushion_or_ratio_result_reads_the_excess_wins_and_a_return_its_mean() -> None:
    """ADR 0064 amendment 2026-10-11: the harness reads the unit off the result's series and
    passes it to the slice rows, so a non-return Sharpe ratio is of the excess wins."""
    day = date(2026, 1, 5)
    stats = tuple(
        SessionStat(day + timedelta(days=i), "BULL", (2.0, 2.0), 1 + i % 2, (8, 0.5, 0.0), 6)
        for i in range(6)
    )
    for unit, wins in (("cushion", True), ("ratio", True), ("excess_return", False)):
        result = VariantResult("v", "screener", "h", 15, stats, (), series=SeriesFacts((), unit))
        assert result.unit == unit and result.wins is wins
    assert not VariantResult("v", "screener", "h", 15, stats, ()).wins  # no series: a return
    (all_, *_), _ = _slice_rows(stats, None, False, False, None, None, 0.0, wins=True)
    assert all_.sharpe == pytest.approx(sharpe([s.excess_wins for s in stats]))
    (plain, *_), _ = _slice_rows(stats, None, False, False, None, None, 0.0)
    assert plain.sharpe is None  # every session's mean is 2.0: no spread, no Sharpe ratio
