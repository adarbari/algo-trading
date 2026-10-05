"""Which keys (CIKs) an incremental reference task refetches this run, spread over the window.

Incremental tasks (``company_details``, ``shares``, ``ibkr_contracts``, and the profile
task ``descriptions``) fetch a key when it was never fetched,
then once per ``refresh_days``. Refetching every key ``refresh_days`` after it was fetched
would bring all ~6k CIKs of a one-night backfill due again on the same night, so each key
gets its own **slot day** in the window instead:

- slot = ``crc32(key) % refresh_days`` (stable across processes and runs);
- on session D the key's latest slot day is the last day ``<= D`` whose ordinal
  ``% refresh_days`` is the slot;
- a stored key is due when it was last fetched before that day.

After a backfill on one day the keys come due spread evenly over the next ``refresh_days``
days, then each once per window; a slot day without a run is picked up by the next run, so
no key goes longer than ``refresh_days`` plus the gap between runs. ``refresh_days = 0``
refetches every stored key; ``force`` refetches everything. New keys come first, then the
stalest, so ``--limit`` works through a backlog oldest first.
"""

import zlib
from collections.abc import Iterable, Mapping
from datetime import date, timedelta


def slot_day(key: str, session: date, refresh_days: int) -> date:
    """The latest day on or before ``session`` that is ``key``'s slot day."""
    if refresh_days <= 0:
        return session + timedelta(days=1)  # every stored key is due
    slot = zlib.crc32(key.encode()) % refresh_days
    return session - timedelta(days=(session.toordinal() - slot) % refresh_days)


def due_keys(
    keys: Iterable[str],
    fetched: Mapping[str, date],
    session: date,
    refresh_days: int,
    force: bool = False,
) -> list[str]:
    """Keys to fetch on ``session``: never fetched (sorted), then stored keys whose slot day
    passed since they were fetched (stalest first); every key with ``force``."""
    wanted = sorted(set(keys))
    if force:
        return wanted
    new = [k for k in wanted if k not in fetched]
    stale = [k for k in wanted if k in fetched and fetched[k] < slot_day(k, session, refresh_days)]
    return new + sorted(stale, key=lambda k: (fetched[k], k))
