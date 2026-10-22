"""The shared state of a windowed screen task's run: what each run of a session did (counted and
recorded as an item of the ingest run) and the window stats and warnings the run ends with."""

from collections import Counter
from collections.abc import Sequence
from datetime import date
from typing import Any

from algotrade_ingestion.tasks.framework.run import IngestRun


class WindowedPass:
    """One task run's state over a window of sessions (``--from`` / ``--to`` / ``--limit``)."""

    def __init__(self, run: IngestRun, limit: int | None) -> None:
        self.run, self.limit = run, limit
        self.counts: Counter[str] = Counter()

    def _note(self, key: str, status: str, count: str) -> None:
        self.run.record_item(key, status)
        self.counts[count] += 1

    def finish_window(
        self,
        days: list[date],
        start: date | None,
        end: date | None,
        extra: dict[str, Any] | None = None,
        before_limit: Sequence[str] = (),
        after_limit: Sequence[str] = (),
    ) -> None:
        """Put the counts, the window and ``extra`` into the run's stats and mark it partial for
        each warning (``before_limit`` ones first, then runs left by ``--limit``, then
        ``after_limit``)."""
        run, counts = self.run, self.counts
        run.stats.update(counts)
        run.stats.update(
            window=[start and start.isoformat(), end and end.isoformat()],
            first=days[0].isoformat() if days else None,
            last=days[-1].isoformat() if days else None,
            sessions=len(days),
            limit=self.limit,
            **(extra or {}),
        )
        for note in before_limit:
            run.partial(note)
        if counts["not_reached"]:
            run.partial(f"{counts['not_reached']} runs left by --limit: run it again to continue")
        for note in after_limit:
            run.partial(note)
