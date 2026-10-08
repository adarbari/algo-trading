"""Run one screener and produce an auditable result.

Rules from the screener specs (for example the VRP scanner):
- every universe instrument is processed exactly once, and none is silently dropped;
- data failures are reported, and a run below the coverage threshold is PARTIAL;
- a COMPLETE run is the only kind that may claim "no qualified candidates".

With the regime gate on (ADR 0049, ``engines.screening.gate``) the screener's picks are PAUSED
in the regimes it pauses in before the rows are audited; PAUSED rows count as processed.
EXCLUDED rows (ADR 0054, ``engines.screening.exclusions``) are out of the coverage denominator.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from algotrade.core.model.errors import AlgoTradeError
from algotrade.core.views.feature_view import FeatureView
from algotrade.engines.screening.exclusions import exclude_rows
from algotrade.engines.screening.gate import RegimeGate, gate_rows
from algotrade.strategies.screeners.base import Decision, Screener, ScreenRow

DEFAULT_MIN_COVERAGE = 0.98


class RunCoverage(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNIVERSE_INCOMPLETE = "UNIVERSE_INCOMPLETE"
    EMPTY_SELECTION = "EMPTY_SELECTION"  # the strategy's selection matched nothing


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
        return sum(1 for r in self.rows if r.decision.processed)

    @property
    def excluded(self) -> int:
        return sum(1 for r in self.rows if r.decision is Decision.EXCLUDED)

    @property
    def coverage_pct(self) -> float:
        """Processed over the instruments left after the excluded ones (0 when none is left)."""
        left = self.unique_instruments - self.excluded
        return self.processed / left if left > 0 else 0.0

    def counts(self) -> dict[str, int]:
        return dict(Counter(r.decision.value for r in self.rows))

    def skipped_reasons(self) -> dict[str, int]:
        return dict(
            Counter(
                r.reasons[0] if r.reasons else "unspecified"
                for r in self.rows
                if not r.decision.processed and r.decision is not Decision.EXCLUDED
            )
        )

    def excluded_reasons(self) -> dict[str, int]:
        return dict(
            Counter(
                r.reasons[0] if r.reasons else "unspecified"
                for r in self.rows
                if r.decision is Decision.EXCLUDED
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
            "skipped": self.unique_instruments - self.processed - self.excluded,
            "excluded": self.excluded,
            "coverage_pct": round(self.coverage_pct, 4),
            "decisions": self.counts(),
            "skipped_reasons": self.skipped_reasons(),
            "excluded_reasons": self.excluded_reasons(),
        }


def run_screen(
    screener: Screener,
    view: FeatureView,
    universe: Sequence[str],
    min_coverage: float = DEFAULT_MIN_COVERAGE,
    gate: RegimeGate | None = None,
    excluded: Mapping[str, str] | None = None,
) -> ScreenRun:
    if sorted(set(universe)) and set(view.instruments) != set(universe):
        raise AlgoTradeError("FeatureView must contain exactly the universe instruments")
    rows = exclude_rows(gate_rows(screener.screen(view), gate), excluded or {}) if universe else []
    return audit_rows(screener.name, rows, universe, min_coverage)


def audit_rows(
    screener: str,
    rows: Sequence[ScreenRow],
    universe: Sequence[str],
    min_coverage: float = DEFAULT_MIN_COVERAGE,
) -> ScreenRun:
    """Check ``rows`` (a screener's output) cover ``universe`` exactly once and grade the
    run's coverage. ``run_screen`` screens then audits; a rule screen audits its own rows."""
    unique = sorted(set(universe))
    if not unique:
        return ScreenRun(screener, (), len(universe), 0, 0, RunCoverage.UNIVERSE_INCOMPLETE)
    by_id: dict[str, ScreenRow] = {}
    for row in rows:
        if row.instrument_id in by_id:
            raise AlgoTradeError(f"{screener} returned {row.instrument_id} twice")
        by_id[row.instrument_id] = row
    if set(by_id) != set(unique):
        raise AlgoTradeError(f"{screener} must return one row per universe instrument")
    ordered = tuple(by_id[i] for i in unique)
    run = ScreenRun(
        screener,
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
