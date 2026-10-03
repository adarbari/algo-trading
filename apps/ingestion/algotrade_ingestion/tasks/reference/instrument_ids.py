"""Assign equity / ETF instrument ids in a reference build (ADR 0018).

- A listing with a composite FIGI gets ``EQ:<FIGI>``; one without keeps ``EQ:<symbol>``.
- **A FIGI id never changes automatically** (owner decision, 2026-10-03). When the previous
  active row of the same symbol held a FIGI id, the id and its FIGI carry forward, both when
  the vendor reports no FIGI (``ids_carried``) and when it reports a *different* one
  (``figi_changes_held``; the vendor's value is kept in ``vendor_figi`` for review).
- Two listings sharing a FIGI: the one that already held the id (else the first symbol) keeps
  it; the others get symbol ids (``figi_conflicts``). Every listing of the FIGI is marked
  for review.
- An owner override (``config/site/overrides/figi.csv``: symbol -> FIGI, blank = no FIGI)
  forces the listing's FIGI and goes first. When it changes an id the listing held, the
  change is recorded in ``instruments/id_map`` like an upgrade (``ids_overridden``), so
  ``migrate-ids`` moves the stored history.
- A previous symbol id whose symbol now has a FIGI id (and no different FIGI before) is an
  **upgrade**: recorded in ``instruments/id_map``; ``rename_ids`` applies it to the previous
  snapshot, so the diff sees the same instrument rather than a delisting plus a listing.

Review state lives on the reference row: ``vendor_figi`` (the vendor's FIGI when the build
did not use it as the listing's own: a different FIGI than the one held, or one several
listings share) and ``figi_review_since`` (the session it was first seen, carried while it
persists). ``figi_review_rows`` turns them into the owner's review file.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

from algotrade.core.model.instruments import equity_id, is_figi_id

ID_MAP = "instruments/id_map"
# ``known_at``: when the upgrade was first recorded. Rows keyed by ``old_id`` that were known
# before it belong to the upgraded instrument; later ones (a reused symbol id) do not.
ID_MAP_COLUMNS = ["instrument_id", "ts", "old_id", "new_id", "symbol", "effective", "known_at"]
FIGI_REVIEW_COLUMNS = ["symbol", "held_figi", "vendor_figi", "first_seen", "note"]


@dataclass
class Assigned:
    reference: pd.DataFrame  # input rows with ``instrument_id`` (and carried ``figi``)
    upgrades: pd.DataFrame  # new id_map rows
    stats: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Held:
    """The previous active row of a symbol."""

    instrument_id: str = ""
    figi: str | None = None
    vendor_figi: str | None = None
    review_since: date | None = None

    @property
    def held_figi(self) -> str | None:
        """The FIGI its id stands for (``None`` for a symbol id)."""
        return self.figi if is_figi_id(self.instrument_id, self.figi) else None


NOTHING = Held()


def _figi(value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


def _date(value: object) -> date | None:
    if value is None or value is pd.NaT or (isinstance(value, float) and math.isnan(value)):
        return None
    return pd.Timestamp(str(value)).date()


def _previous_active(previous: pd.DataFrame | None) -> dict[str, Held]:
    """symbol -> what the previous snapshot's active row held."""
    if previous is None or previous.empty:
        return {}
    active = previous[previous["status"].eq("ACTIVE")] if "status" in previous else previous

    def column(name: str) -> pd.Series:
        return active[name] if name in active.columns else pd.Series(None, index=active.index)

    return {
        str(s): Held(str(i), _figi(f), _figi(v), _date(r))
        for s, i, f, v, r in zip(
            active["symbol"],
            active["instrument_id"],
            column("figi"),
            column("vendor_figi"),
            column("figi_review_since"),
            strict=True,
        )
    }


def assign_ids(
    current: pd.DataFrame,
    previous: pd.DataFrame | None,
    session: date,
    overrides: Mapping[str, str | None] | None = None,
) -> Assigned:
    """``current`` needs ``symbol`` (unique) and ``figi`` (the vendor's, may be null);
    ``previous`` is the last reference snapshot (ids already held); ``overrides`` maps a
    symbol to the FIGI the owner fixed for it (``None``: no FIGI, a symbol id)."""
    overrides = overrides or {}
    before = _previous_active(previous)
    ref = current.copy()
    symbols = [str(s) for s in ref["symbol"]]
    vendor = [_figi(f) for f in ref["figi"]]
    figis, changed, carried = list(vendor), [False] * len(ref), 0
    for n, symbol in enumerate(symbols):
        held = before.get(symbol, NOTHING).held_figi
        if symbol in overrides:
            figis[n] = overrides[symbol]
        elif held is not None and figis[n] != held:
            carried += figis[n] is None
            changed[n] = figis[n] is not None
            figis[n] = held
    ref["figi"] = figis
    wanted = [equity_id(s, f) for s, f in zip(symbols, figis, strict=True)]
    rank = [
        0 if s in overrides else 1 if before.get(s, NOTHING).instrument_id == w else 2
        for s, w in zip(symbols, wanted, strict=True)
    ]
    ids, taken, conflicts = [""] * len(ref), set(), 0
    for n in sorted(range(len(ref)), key=lambda n: (rank[n], symbols[n])):
        iid = wanted[n]
        if iid in taken:
            iid, conflicts = equity_id(symbols[n]), conflicts + 1
        ids[n] = iid
        taken.add(iid)
    ref["instrument_id"] = ids
    upgrades, forced = _id_changes(ref, before, previous, overrides)
    _mark_review(ref, vendor, changed, before, overrides, session)
    active = ref["status"].eq("ACTIVE") if "status" in ref else pd.Series(True, index=ref.index)
    by_figi = sum(
        is_figi_id(i, f)
        for i, f, a in zip(ref["instrument_id"], ref["figi"], active, strict=True)
        if a
    )
    stats = {
        "ids_by_figi": int(by_figi),
        "ids_by_symbol": int(active.sum()) - int(by_figi),
        "ids_carried": carried,
        "ids_upgraded": len(upgrades) - forced,
        "ids_overridden": forced,
        "figi_conflicts": conflicts,
        "figi_changes_held": sum(changed),
        "figi_review": int((ref["vendor_figi"].notna() & active).sum()),
    }
    return Assigned(ref, id_map_rows(upgrades, session), stats)


def _id_changes(
    ref: pd.DataFrame,
    before: Mapping[str, Held],
    previous: pd.DataFrame | None,
    overrides: Mapping[str, str | None],
) -> tuple[list[dict[str, str]], int]:
    """-> (id_map rows: upgrades + owner-forced changes, how many were forced)."""
    previous_ids = set(previous["instrument_id"]) if previous is not None else set()
    rows, forced = [], 0
    for symbol, iid, figi in zip(ref["symbol"], ref["instrument_id"], ref["figi"], strict=True):
        old = before.get(str(symbol), NOTHING)
        if not old.instrument_id or old.instrument_id == iid:
            continue
        row = {"old_id": old.instrument_id, "new_id": iid, "symbol": str(symbol)}
        if str(symbol) in overrides:
            rows.append(row)
            forced += 1
        elif (
            is_figi_id(iid, figi)
            and old.held_figi is None
            and old.figi in (None, figi)
            and iid not in previous_ids
        ):
            rows.append(row)
    return rows, forced


def _mark_review(
    ref: pd.DataFrame,
    vendor: list[str | None],
    changed: list[bool],
    before: Mapping[str, Held],
    overrides: Mapping[str, str | None],
    session: date,
) -> None:
    """Fill ``vendor_figi`` / ``figi_review_since`` in place: a held FIGI the vendor now
    reports differently, and every active listing of a FIGI several listings share."""
    active = ref["status"].eq("ACTIVE") if "status" in ref else pd.Series(True, index=ref.index)
    figi = ref["figi"].where(active & ~ref["symbol"].isin(list(overrides)))
    shared = figi.notna() & figi.duplicated(keep=False)
    marks = [
        vendor[n] if changed[n] else str(figi.iloc[n]) if shared.iloc[n] else None
        for n in range(len(ref))
    ]
    since: list[date | None] = []
    for symbol, mark in zip(ref["symbol"], marks, strict=True):
        old = before.get(str(symbol), NOTHING)
        if mark is None:
            since.append(None)
        else:
            same = old.vendor_figi == mark and old.review_since is not None
            since.append(old.review_since if same else session)
    ref["vendor_figi"] = marks
    ref["figi_review_since"] = pd.Series(since, index=ref.index, dtype=object)


def _note(row: object, held: str | None, marked: pd.DataFrame) -> str:
    symbol, iid, vendor = row.symbol, row.instrument_id, row.vendor_figi  # type: ignore[attr-defined]
    if held is not None and held != vendor:
        return f"vendor reports a different FIGI; {symbol} keeps {iid}"
    others = marked.loc[marked["vendor_figi"].eq(vendor) & marked["symbol"].ne(symbol), "symbol"]
    shared = ", ".join(sorted(str(s) for s in others))
    if held is not None:
        return f"FIGI shared with {shared}; {symbol} holds {iid}"
    return f"FIGI shared with {shared}; {symbol} keeps the symbol id {iid}"


def figi_review_rows(reference: pd.DataFrame) -> list[dict[str, str]]:
    """Active listings marked for FIGI review (``FIGI_REVIEW_COLUMNS``): a held FIGI the
    vendor reports differently, or a FIGI several listings share. The owner resolves one with
    a row in ``config/site/overrides/figi.csv``, or it clears when the vendor agrees again."""
    if "vendor_figi" not in reference.columns:
        return []
    marked = reference[reference["status"].eq("ACTIVE") & reference["vendor_figi"].notna()]
    rows = []
    for r in marked.sort_values("symbol").itertuples():
        held = _figi(r.figi) if is_figi_id(str(r.instrument_id), _figi(r.figi)) else None
        since = _date(r.figi_review_since)
        rows.append(
            {
                "symbol": str(r.symbol),
                "held_figi": held or "",
                "vendor_figi": str(r.vendor_figi),
                "first_seen": "" if since is None else since.isoformat(),
                "note": _note(r, held, marked),
            }
        )
    return rows


def rename_ids(frame: pd.DataFrame | None, id_map: pd.DataFrame) -> pd.DataFrame | None:
    """``frame`` with every ``old_id`` in ``id_map`` replaced by the id it ends up with. The
    changes apply in the order they were recorded (``known_at``), so a chain within one
    session (DFAC, 2026-10-02: ``EQ:DFAC -> A``, ``A -> B``, then the override ``B -> A``)
    lands on its last id rather than stopping after one step. A reference snapshot that then
    holds an id twice (an override moved a listing onto an id a delisted row still carries)
    keeps the active row."""
    if frame is None or id_map.empty:
        return frame
    mapping = _final_ids(id_map)
    renamed = frame.assign(instrument_id=frame["instrument_id"].replace(mapping))
    if "status" not in renamed.columns or not renamed["instrument_id"].duplicated().any():
        return renamed
    first = renamed["status"].ne("ACTIVE").astype(int)
    order = first.sort_values(kind="stable").index
    kept = renamed.loc[order].drop_duplicates("instrument_id", keep="first")
    return kept.sort_index()


def _final_ids(id_map: pd.DataFrame) -> dict[str, str]:
    """old id -> the id it ends up with after every change, applied in ``known_at`` order
    (unknown last, else map order)."""
    ordered = id_map
    if "known_at" in id_map.columns:
        known = pd.to_datetime(id_map["known_at"], utc=True)
        ordered = id_map.assign(_known=known).sort_values(
            "_known", kind="stable", na_position="last"
        )
    final: dict[str, str] = {}  # an id at the start -> where it is now
    holders: dict[str, set[str]] = {}  # an id now -> the starting ids it holds
    for old, new in zip(ordered["old_id"].astype(str), ordered["new_id"].astype(str), strict=True):
        moving = holders.pop(old, set()) | ({old} if old not in final else set())
        for start in moving:
            final[start] = new
        holders.setdefault(new, set()).update(moving)
    return {start: now for start, now in final.items() if start != now}


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
