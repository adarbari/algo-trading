"""Assign equity / ETF instrument ids in a reference build (ADR 0018).

- A listing with a composite FIGI gets ``EQ:<FIGI>``; one without keeps ``EQ:<symbol>``.
- No FIGI today, but yesterday the same active symbol had a FIGI id: the id and FIGI carry
  forward (a FIGI id never changes).
- Two listings sharing a FIGI: the one that already held the id (else the first symbol) keeps
  it; the others get symbol ids and are counted as conflicts.
- Yesterday's symbol id whose symbol now has a FIGI id (and no different FIGI before) is an
  **upgrade**: recorded in ``instruments/id_map``; ``rename_ids`` applies it to the previous
  snapshot, so the diff sees the same instrument rather than a delisting plus a listing.
"""

from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

from algotrade.core.instruments import equity_id, is_figi_id

ID_MAP = "instruments/id_map"
# ``known_at``: when the upgrade was first recorded. Rows keyed by ``old_id`` that were known
# before it belong to the upgraded instrument; later ones (a reused symbol id) do not.
ID_MAP_COLUMNS = ["instrument_id", "ts", "old_id", "new_id", "symbol", "effective", "known_at"]


@dataclass
class Assigned:
    reference: pd.DataFrame  # input rows with ``instrument_id`` (and carried ``figi``)
    upgrades: pd.DataFrame  # new id_map rows
    stats: dict[str, int] = field(default_factory=dict)


def _figi(value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


def _previous_active(previous: pd.DataFrame | None) -> dict[str, tuple[str, str | None]]:
    """symbol -> (id, figi) for yesterday's active rows."""
    if previous is None or previous.empty:
        return {}
    active = previous[previous["status"].eq("ACTIVE")] if "status" in previous else previous
    figis = active["figi"] if "figi" in active.columns else pd.Series(None, index=active.index)
    return {
        str(s): (str(i), _figi(f))
        for s, i, f in zip(active["symbol"], active["instrument_id"], figis, strict=True)
    }


def assign_ids(current: pd.DataFrame, previous: pd.DataFrame | None, session: date) -> Assigned:
    """``current`` needs ``symbol`` (unique) and ``figi`` (may be null); ``previous`` is the
    last reference snapshot (ids already held)."""
    before = _previous_active(previous)
    ref = current.copy()
    figis = [_figi(f) for f in ref["figi"]]
    carried = 0
    for n, symbol in enumerate(ref["symbol"]):
        old_id, old_figi = before.get(str(symbol), ("", None))
        if figis[n] is None and old_figi is not None and is_figi_id(old_id, old_figi):
            figis[n], carried = old_figi, carried + 1
    ref["figi"] = figis
    wanted = [equity_id(str(s), f) for s, f in zip(ref["symbol"], figis, strict=True)]
    held = [
        before.get(str(s), ("", None))[0] == w for s, w in zip(ref["symbol"], wanted, strict=True)
    ]
    order = sorted(range(len(ref)), key=lambda n: (not held[n], str(ref["symbol"].iloc[n])))
    ids, taken, conflicts = [""] * len(ref), set(), 0
    for n in order:
        iid = wanted[n]
        if iid in taken:
            iid, conflicts = equity_id(str(ref["symbol"].iloc[n])), conflicts + 1
        ids[n] = iid
        taken.add(iid)
    ref["instrument_id"] = ids
    previous_ids = set(previous["instrument_id"]) if previous is not None else set()
    upgrades = []
    for symbol, iid, figi in zip(ref["symbol"], ref["instrument_id"], ref["figi"], strict=True):
        old_id, old_figi = before.get(str(symbol), ("", None))
        if (
            old_id
            and old_id != iid
            and is_figi_id(iid, figi)
            and not is_figi_id(old_id, old_figi)
            and old_figi in (None, figi)
            and iid not in previous_ids
        ):
            upgrades.append({"old_id": old_id, "new_id": iid, "symbol": str(symbol)})
    active = ref["status"].eq("ACTIVE") if "status" in ref else pd.Series(True, index=ref.index)
    stats = {
        "ids_by_figi": int(
            sum(
                is_figi_id(i, f)
                for i, f, a in zip(ref["instrument_id"], ref["figi"], active, strict=True)
                if a
            )
        ),
        "ids_carried": carried,
        "ids_upgraded": len(upgrades),
        "figi_conflicts": conflicts,
    }
    stats["ids_by_symbol"] = int(active.sum()) - stats["ids_by_figi"]
    return Assigned(ref, id_map_rows(upgrades, session), stats)


def rename_ids(frame: pd.DataFrame | None, id_map: pd.DataFrame) -> pd.DataFrame | None:
    """``frame`` with every ``old_id`` in ``id_map`` replaced by its ``new_id``."""
    if frame is None or id_map.empty:
        return frame
    mapping = dict(zip(id_map["old_id"], id_map["new_id"], strict=True))
    return frame.assign(instrument_id=frame["instrument_id"].replace(mapping))


def id_map_rows(upgrades: list[dict[str, str]], session: date) -> pd.DataFrame:
    """Today's upgrades; ``known_at`` is filled by ``cumulative_map``."""
    rows = [
        {
            **u,
            "instrument_id": u["new_id"],
            "ts": pd.Timestamp(session, tz="UTC"),
            "effective": session,
            "known_at": None,
        }
        for u in upgrades
    ]
    return pd.DataFrame(rows, columns=ID_MAP_COLUMNS)


def cumulative_map(
    previous_map: pd.DataFrame | None, upgrades: pd.DataFrame, now: datetime
) -> pd.DataFrame:
    """The last full map plus today's upgrades; an upgrade already recorded keeps its
    original ``effective`` and ``known_at``."""
    today = upgrades.assign(known_at=pd.Timestamp(now))
    frames = [f[ID_MAP_COLUMNS] for f in (previous_map, today) if f is not None and not f.empty]
    if not frames:
        return today
    merged = pd.concat(frames, ignore_index=True)
    merged["known_at"] = pd.to_datetime(merged["known_at"], utc=True)
    merged = merged.drop_duplicates(["old_id", "new_id"], keep="first")
    return merged.sort_values(["effective", "old_id"]).reset_index(drop=True)
