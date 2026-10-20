"""What a ``compact-runs`` run counts (per partition, summed) and the lines it prints."""

import sys
from dataclasses import dataclass, field
from datetime import date

from algotrade.storage.tables.interfaces import CompactionReport

GB = 1e9
SHOWN = 20  # partitions listed one by one in the run record (the totals count them all)


def to_stderr(line: str) -> None:
    """The default progress sink: one flushed line on stderr (the log of a detached run)."""
    sys.stderr.write(line + "\n")
    sys.stderr.flush()


def describe(day: date, report: CompactionReport, seconds: float, worker: str = "") -> str:
    """One partition's progress line (``worker``: ``w1``, ``w2``, ...)."""
    head = f"compact-runs {f'[{worker}] ' if worker else ''}{day}:"
    if report.skipped:
        return f"{head} skipped ({report.skipped}) in {seconds:.1f} s"
    return (
        f"{head} files {report.files_before} -> {report.files_after}, "
        f"bytes {report.bytes_before} -> {report.bytes_after}, "
        f"{report.runs_dropped} runs dropped, {seconds:.1f} s"
    )


@dataclass
class Totals:
    """What the run did, summed over partitions."""

    compacted: int = 0
    unchanged: int = 0
    skipped: dict[str, int] = field(default_factory=dict)
    files_before: int = 0
    files_after: int = 0
    bytes_before: int = 0
    bytes_after: int = 0
    runs_dropped: int = 0
    swept_files: int = 0
    unswept: int = 0  # swapped partitions whose superseded files a later run sweeps
    partitions: list[dict[str, object]] = field(default_factory=list)

    def add(self, day: date, report: CompactionReport) -> bool:
        """Count one partition's report; whether it changes (or would change) anything."""
        if report.skipped:
            self.skipped[report.skipped] = self.skipped.get(report.skipped, 0) + 1
            return False
        if report.files_after == report.files_before and report.bytes_after == report.bytes_before:
            self.unchanged += 1
            return False
        self.compacted += 1
        self.files_before += report.files_before
        self.files_after += report.files_after
        self.bytes_before += report.bytes_before
        self.bytes_after += report.bytes_after
        self.runs_dropped += report.runs_dropped
        self.partitions.append(
            {
                "session": day.isoformat(),
                "files": [report.files_before, report.files_after],
                "bytes": [report.bytes_before, report.bytes_after],
                "runs_dropped": report.runs_dropped,
            }
        )
        return True

    def stats(self) -> dict[str, object]:
        listed = sorted(self.partitions, key=lambda p: str(p["session"]))[:SHOWN]
        return {
            "compacted": self.compacted,
            "unchanged": self.unchanged,
            "skipped": self.skipped,
            "files_before": self.files_before,
            "files_after": self.files_after,
            "bytes_before": self.bytes_before,
            "bytes_after": self.bytes_after,
            "saving_bytes": self.bytes_before - self.bytes_after,
            "runs_dropped": self.runs_dropped,
            "swept_files": self.swept_files,
            "unswept_partitions": self.unswept,
            "partitions": listed,
        }
