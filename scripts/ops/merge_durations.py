"""Merge the per-shard pytest-split duration files into one `.test_durations`.

CI's shards each record the durations of the tests they ran; the `tests` job on main merges
them over the previous file (tests no shard ran this time keep their old time) and caches the
result for the next run's `--splitting-algorithm least_duration`. Entries under 0.1 s are
dropped to keep the file small: pytest-split gives an unknown test the average time.
"""

import json
import sys
from pathlib import Path

MIN_SECONDS = 0.1


def merge(base: dict[str, float], recorded: list[dict[str, float]]) -> dict[str, float]:
    """`base` overlaid with every recorded file, the small entries dropped."""
    merged = dict(base)
    for durations in recorded:
        merged.update(durations)
    return {name: round(secs, 2) for name, secs in merged.items() if secs >= MIN_SECONDS}


def main(argv: list[str]) -> int:
    source, target = Path(argv[1]), Path(argv[2])
    base = json.loads(target.read_text()) if target.exists() else {}
    recorded = [json.loads(f.read_text()) for f in sorted(source.rglob(".durations-*.json"))]
    if not recorded:
        print(f"no durations under {source}", file=sys.stderr)
        return 1
    target.write_text(json.dumps(merge(base, recorded), separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
