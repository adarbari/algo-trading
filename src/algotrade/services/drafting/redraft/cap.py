"""The per-user daily cap on part re-drafts (owner decision 2026-10-11, ADR 0041 amended
2026-10-12: ``[limits] part_redrafts_per_day`` in ``llm.toml``, 30 by default).

A part's re-draft is a model call a trader can repeat as often as they like, so each user gets
a number a day (the exchange calendar date, as the usage log partitions). Only a call that
returned a draft counts: a failed, refused or unavailable one gives its place back. The count is
**read from the usage log** (``usage/llm_calls``: the answered calls of ``USE_CASE`` by that user
on that day, ``data.usage.calls_of``), not kept in a counter that a restart resets (the API
restarts at every deploy). The log is written in the background, so a call made a moment ago may
not be in it yet: this process also remembers, until the day turns, the calls it made (their ids,
so a call that reached the log is counted once) and the places held by the calls in flight, and
counts the union. One API process is assumed, as the usage ledger does (ADR 0058). A request is
admitted under a lock, so requests that arrive together cannot all pass the last place. A count
that cannot be read (the store fails) fails closed: no re-draft, never an unlimited one. At the
limit the request is a
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
    """One admitted re-draft, holding one place until the block ends: the use case tells it the
    call it made (``note``) as soon as the model has answered, which swaps the place's token for
    the call's id under the cap's lock (the log's row for that call is then not counted twice)."""

    def __init__(self, cap: "PartRedraftCap", user: str, day: date, key: str) -> None:
        self._cap, self._user, self._day = cap, user, day
        self.key = key  # what the place is counted as: a token, then the call's id

    def note(self, call_id: str | None) -> None:
        if call_id:
            self._cap._swap(self._user, self._day, self, call_id)


class PartRedraftCap:
    """Counts a user's part re-drafts of the exchange day against ``limit()`` (called per
    request, so a changed ``llm.toml`` applies without a restart). Only a call that returned a
    draft uses up a place (owner decision 2026-10-12): the place is reserved when the request is
    admitted, so that requests in flight count, and given back when the block raises (a failed,
    refused or unavailable call); the log counts only answered calls (``calls_of``)."""

    def __init__(
        self,
        reader: StoreReader,
        limit: Callable[[], int],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._reader, self._limit, self._clock = reader, limit, clock
        self._lock = threading.Lock()
        # (user, day) -> the calls made or being made: a call id, or a token while not known
        self._made: dict[tuple[str, date], set[str]] = defaultdict(set)
        self._tokens = 0

    @contextmanager
    def slot(self, user: str) -> Iterator[Slot]:
        """Admit one re-draft of ``user`` or raise ``DailyLimitError``; a place is held from here
        on. What the block raises gives the place back (what the log already holds stays)."""
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
            slot = Slot(self, user, day, f"pending-{self._tokens}")
            made.add(slot.key)
        try:
            yield slot
        except BaseException:
            with self._lock:
                self._made[(user, day)].discard(slot.key)
            raise

    def _swap(self, user: str, day: date, slot: Slot, call_id: str) -> None:
        with self._lock:
            made = self._made[(user, day)]
            made.discard(slot.key)
            made.add(call_id)
            slot.key = call_id

    def _stored(self, user: str, day: date) -> set[str]:
        try:
            return calls_of(self._reader, day, USE_CASE, user)
        except Exception as exc:
            log.exception("the part re-draft count could not be read")
            raise ModelUnavailableError(
                "part re-drafts are paused: the usage log could not be read, so the daily "
                "limit cannot be checked"
            ) from exc


def _until_tomorrow(now: datetime, day: date) -> int:
    """Seconds until the exchange day after ``day`` starts (at least one)."""
    midnight = datetime.combine(day + timedelta(days=1), time.min, tzinfo=EXCHANGE_TZ)
    return max(1, math.ceil((midnight - now).total_seconds()))
