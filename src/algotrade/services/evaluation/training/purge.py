"""The purge of the training frame: the session a training window must close before.

Apart from ``frame.py`` so the discovery grid can use the same cutoff without importing the frame
(the frame imports the no-ML guard, which reads the discovery's feature reads)."""

from datetime import date

from algotrade.core.time.calendar import previous_session


def purge_cutoff(frozen_from: date, horizon: int) -> date:
    """The session ``horizon`` sessions before ``frozen_from``: a training window must close before
    it (purged and embargoed by one horizon)."""
    day = frozen_from
    for _ in range(horizon):
        day = previous_session(day)
    return day
