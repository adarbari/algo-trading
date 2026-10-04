"""Summarise a run record's per-item statuses: the status code, which codes are fine, and the
items that failed grouped by a normalised reason (shared by the nightly report and the API).

An item status is ``CODE`` or ``CODE: message`` (``STALE_DATA: chain is for 2026-10-01``).
The reason is the status without what makes every item's message different (its own key,
URLs, dates, numbers), so one cause is one group however many items it hit.
"""

import re
from collections.abc import Mapping

# Item statuses that are not failures: stored, or "nothing to fetch" outcomes counted in stats.
FINE = frozenset(
    {"OK", "STORED", "PASS", "COMPLETE", "SKIPPED", "NO_SESSION", "EMPTY", "NO_FACTS"}
    | {"NO_SHARE_FACTS", "NO_INPUT"}
)
_URL = re.compile(r"https?://\S+")
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_NUMBER = re.compile(r"\b\d+(\.\d+)?\b")


def status_code(status: str) -> str:
    """``CODE: message`` -> ``CODE``."""
    return status.split(":", 1)[0].strip()


def normalise(message: str, key: str = "") -> str:
    """A failure reason without the specifics that make every item's message different."""
    # The key as a whole token only: ticker "E" must not turn STALE_DATA into STAL<id>_DATA.
    text = re.sub(rf"(?<!\w){re.escape(key)}(?!\w)", "<id>", message) if key else message
    text = _URL.sub("<url>", text)
    text = _DATE.sub("<date>", text)
    return _NUMBER.sub("<n>", text).strip()


def failed_items(items: Mapping[str, str]) -> list[tuple[str, list[tuple[str, str]]]]:
    """(reason, [(item key, status)]) for every item whose code is not ``FINE``: the largest
    group first, keys sorted within a group."""
    grouped: dict[str, list[tuple[str, str]]] = {}
    for key, status in sorted(items.items()):
        if status_code(status) not in FINE:
            grouped.setdefault(normalise(status, key), []).append((key, status))
    return sorted(grouped.items(), key=lambda kv: (-len(kv[1]), kv[0]))
