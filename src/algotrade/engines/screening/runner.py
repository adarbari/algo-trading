"""Run one screener and produce an auditable result.

Rules from the screener specs (for example the VRP scanner):
- every universe instrument is processed exactly once, and none is silently dropped;
- data failures are reported, and a run below the coverage threshold is PARTIAL;
- a COMPLETE run is the only kind that may claim "no qualified candidates".
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from algotrade.core.errors import AlgoTradeError
from algotrade.core.feature_view import FeatureView
from algotrade.strategies.screeners.base import Decision, Screener, ScreenRow

DEFAULT_MIN_COVERAGE = 0.98


class RunCoverage(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNIVERSE_INCOMPLETE = "UNIVERSE_INCOMPLETE"


@dataclass(frozen=True)
class ScreenRun:
    screener: str
    rows: tuple[ScreenRow, ...]
    universe_rows: int
    unique_instruments: int
    duplicates_removed: int
    coverage: RunCoverage

    @property
    def processed(self) -> int:
        return sum(1 for r in self.rows if r.decision is not Decision.UNKNOWN)

    @property
    def coverage_pct(self) -> float:
        return self.processed / self.unique_instruments if self.unique_instruments else 0.0

    def counts(self) -> dict[str, int]:
        return dict(Counter(r.decision.value for r in self.rows))

    def skipped_reasons(self) -> dict[str, int]:
        return dict(
            Counter(
                r.reasons[0] if r.reasons else "unspecified"
                for r in self.rows
                if r.decision is Decision.UNKNOWN
            )
        )

    def audit(self) -> dict[str, object]:
        return {
            "screener": self.screener,
            "coverage": self.coverage.value,
            "universe_rows": self.universe_rows,
            "unique_instruments": self.unique_instruments,
            "duplicates_removed": self.duplicates_removed,
            "processed": self.processed,
            "skipped": self.unique_instruments - self.processed,
            "coverage_pct": round(self.coverage_pct, 4),
            "decisions": self.counts(),
            "skipped_reasons": self.skipped_reasons(),
        }


def run_screen(
    screener: Screener,
    view: FeatureView,
    universe: Sequence[str],
    min_coverage: float = DEFAULT_MIN_COVERAGE,
) -> ScreenRun:
    unique = sorted(set(universe))
    if not unique:
        return ScreenRun(screener.name, (), len(universe), 0, 0, RunCoverage.UNIVERSE_INCOMPLETE)
    if set(view.instruments) != set(unique):
        raise AlgoTradeError("FeatureView must contain exactly the universe instruments")
    rows = screener.screen(view)
    by_id: dict[str, ScreenRow] = {}
    for row in rows:
        if row.instrument_id in by_id:
            raise AlgoTradeError(f"{screener.name} returned {row.instrument_id} twice")
        by_id[row.instrument_id] = row
    if set(by_id) != set(unique):
        raise AlgoTradeError(f"{screener.name} must return one row per universe instrument")
    ordered = tuple(by_id[i] for i in unique)
    run = ScreenRun(
        screener.name,
        ordered,
        len(universe),
        len(unique),
        len(universe) - len(unique),
        RunCoverage.COMPLETE,
    )
    if run.coverage_pct < min_coverage:
        run = ScreenRun(
            run.screener,
            run.rows,
            run.universe_rows,
            run.unique_instruments,
            run.duplicates_removed,
            RunCoverage.PARTIAL,
        )
    return run
