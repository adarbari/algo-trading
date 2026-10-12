"""The per-user daily cap on part re-drafts (owner decision 2026-10-11, ADR 0041 amended
2026-10-12: ``[limits] part_redrafts_per_day`` in ``llm.toml``, 30 by default).

A part's re-draft is a model call a trader can repeat as often as they like, so each user gets
a number a day (the exchange calendar date, as the usage log partitions). The count is **read
from the usage log** (``usage/llm_calls``: the calls of ``USE_CASE`` by that user on that day,
``data.usage.calls_of``), not kept in a counter that a restart resets (the API restarts at every
deploy). The log is written in the background, so a call made a moment ago may not be in it yet:
this process also remembers, until the day turns, the calls it made (their ids, so a call that
reached the log is counted once) and the calls it is making now, and counts the union. One API
process is assumed, as the usage ledger does (ADR 0058). A request is admitted under a lock, so
requests that arrive together cannot all pass the last place. A count that cannot be read (the
store fails) fails closed: no re-draft, never an unlimited one. At the limit the request is a
``DailyLimitError`` (429, code ``CODE``, with the seconds until the exchange day turns)."""

import logging
import math
import threading
from collections import defaultdict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, time, timedelta

from algotrade.core.model.errors import DailyLimitError, ModelUnavailableError
from algotrade.core.time.calendar import EXCHANGE_TZ, exchange_date
from algotrade.data import StoreReader
from algotrade.data.usage import calls_of

log = logging.getLogger(__name__)
USE_CASE = "screener-draft-part"  # the ``CallTag`` kind of a part's re-draft (the usage log's)
CODE = "part_redraft_limit"  # what the web keys its "limit reached" state on


class Slot:
    """One admitted re-draft: the use case tells it the call it made (``note``) as soon as the
    model has answered, so that call counts even if what follows fails."""

    def __init__(self) -> None:
        self.asked = False
        self.call_id: str | None = None

    def note(self, call_id: str | None) -> None:
        self.asked, self.call_id = True, call_id


class PartRedraftCap:
    """Counts a user's part re-drafts of the exchange day against ``limit()`` (called per
    request, so a changed ``llm.toml`` applies without a restart)."""

    def __init__(
        self,
        reader: StoreReader,
        limit: Callable[[], int],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._reader, self._limit, self._clock = reader, limit, clock
        self._lock = threading.Lock()
        # (user, day) -> the calls made or being made: a call id, or a token while it is not known
        self._made: dict[tuple[str, date], set[str]] = defaultdict(set)
        self._tokens = 0

    @contextmanager
    def slot(self, user: str) -> Iterator[Slot]:
        """Admit one re-draft of ``user`` or raise ``DailyLimitError``; counted from here on.
        What the block raises before the model was asked (``Slot.note``, or an error that names
        its call) gives the place back; once asked, it stays counted."""
        now = self._clock()
        day, limit = exchange_date(now), self._limit()
        with self._lock:
            for key in [k for k in self._made if k[1] < day]:
                del self._made[key]  # yesterday's calls are in the log for good
            stored = self._stored(user, day)
            made = self._made[(user, day)]
            if len(stored | made) >= limit:
                raise DailyLimitError("part re-drafts", CODE, limit, _until_tomorrow(now, day))
            self._tokens += 1
            token = f"pending-{self._tokens}"
            made.add(token)
        slot = Slot()
        try:
            yield slot
        except BaseException as exc:
            slot.asked = slot.asked or getattr(exc, "call_id", None) is not None
            slot.call_id = slot.call_id or getattr(exc, "call_id", None)
            self._settle(user, day, token, slot, keep=slot.asked)
            raise
        self._settle(user, day, token, slot, keep=True)

    def _stored(self, user: str, day: date) -> set[str]:
        try:
            return calls_of(self._reader, day, USE_CASE, user)
        except Exception as exc:
            log.exception("the part re-draft count could not be read")
            raise ModelUnavailableError(
                "part re-drafts are paused: the usage log could not be read, so the daily "
                "limit cannot be checked"
            ) from exc

    def _settle(self, user: str, day: date, token: str, slot: Slot, keep: bool) -> None:
        with self._lock:
            made = self._made[(user, day)]
            made.discard(token)
            if keep:  # the call's id (counted once with the log's row), else a token of its own
                made.add(slot.call_id or token)


def _until_tomorrow(now: datetime, day: date) -> int:
    """Seconds until the exchange day after ``day`` starts (at least one)."""
    midnight = datetime.combine(day + timedelta(days=1), time.min, tzinfo=EXCHANGE_TZ)
    return max(1, math.ceil((midnight - now).total_seconds()))
