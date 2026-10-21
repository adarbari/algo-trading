"""Build one serving release (ADR 0077 decisions 1-3): the session record, read at one pinned
commit sequence ``X``.

``X`` is the store's published sequence, taken once; every read of the build goes through
``reader.pinned(X)``, so the release equals "the store as of X", and ``begin`` pins ``X`` so the
versions it names survive recommits. A version lost before the pin took hold (a
``StaleSnapshotError``) restarts the build at a fresh ``X``, at most ``MAX_TRIES`` times, then
the error goes to the caller. The session record is the resolved default session without
``newer`` (that stays live: ADR 0077 decision 7), as fixed-order string and boolean columns, so
two builds of one store are byte for byte equal. Purpose-shaped tables come later, one
operation at a time, when a measured cold compute is over budget (the design note).
"""

import dataclasses
import json
from datetime import date, datetime

import pandas as pd

from algotrade.data import StoreReader
from algotrade.services.read.session import NIGHTLY, Session, resolve_session
from algotrade.storage.backends.release.interfaces import (
    Draft,
    InputPartitions,
    ReleaseStore,
    Reservation,
)
from algotrade.storage.backends.release.manifest import Manifest
from algotrade.storage.backends.run_selection import StaleSnapshotError

FORMAT = 1
MAX_TRIES = 3
SESSION_TABLE = "session"
SESSION_COLUMNS = (
    "date",
    "is_latest",
    "latest_with_bars",
    "reference_snapshot",
    "pre_snapshot",
    "present",
    "missing",
    "unavailable",
    "complete",
    "cutoff",
)


def _day(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def session_frame(session: Session) -> pd.DataFrame:
    """The one-row session record: dates as ISO text, ``present`` / ``missing`` / ``unavailable``
    as canonical JSON, ``newer`` left out."""
    cutoff: datetime | None = session.cutoff
    row = {
        "date": _day(session.date),
        "is_latest": session.is_latest,
        "latest_with_bars": _day(session.latest_with_bars),
        "reference_snapshot": _day(session.reference_snapshot),
        "pre_snapshot": session.pre_snapshot,
        "present": _json(list(session.present)),
        "missing": _json(list(session.missing)),
        "unavailable": _json([dataclasses.asdict(u) for u in session.unavailable]),
        "complete": session.complete,
        "cutoff": None if cutoff is None else cutoff.isoformat(),
    }
    return pd.DataFrame([row], columns=list(SESSION_COLUMNS))


def input_partitions(pinned: StoreReader, session: Session) -> list[InputPartitions]:
    """The session-day partitions the record was built from, each with its stamp at the pin."""
    day = session.date
    names = list(session.present)
    found = []
    for table in names:
        stamp = pinned.partition_seq(table, day, day).get(day)
        if stamp is not None:
            found.append(InputPartitions(table, {day: stamp}))
    return found


def build_release(reader: StoreReader, store: ReleaseStore, code_sha: str) -> Manifest:
    """Build, seal and return the release of the default session at the current sequence.
    Raises ``NotFoundError`` for an empty store, ``ReleaseError`` when the store refuses the
    build, ``StaleSnapshotError`` after ``MAX_TRIES`` lost pins. Never promotes.

    Order matters (point in time): the nightly run records are read first (``runs`` ignores the
    pin, and a COMPLETE record is saved after the commits it names, so records read before X
    name only sessions whose tables are inside X); then X is taken, then reserved (pinned, with
    the destructive epoch) before the first read; the session is resolved on the pinned reader
    over those records; ``begin`` turns the reservation into the release's pin and ``seal``
    refuses if the epoch moved since the reservation."""
    lost: StaleSnapshotError | None = None
    for _ in range(MAX_TRIES):
        frozen = reader.with_runs_frozen([NIGHTLY])
        x = frozen.visible_seq()
        reservation = store.reserve(x)
        draft = None
        try:
            pinned = frozen.pinned(x)
            session = resolve_session(pinned, None)
            draft = store.begin(session.date, x, FORMAT, reservation)
            store.write_frame(draft, SESSION_TABLE, session_frame(session))
            return store.seal(draft, input_partitions(pinned, session), code_sha)
        except StaleSnapshotError as exc:  # a version went before the pin held it: start again
            lost = exc
            _give_back(store, draft, reservation)
        except BaseException:
            _give_back(store, draft, reservation)
            raise
    assert lost is not None
    raise lost


def _give_back(store: ReleaseStore, draft: Draft | None, reservation: Reservation) -> None:
    """Undo a failed attempt: the draft and its pin once begun, else the reservation."""
    if draft is not None:
        store.abort(draft)
    else:
        store.drop_reservation(reservation)
