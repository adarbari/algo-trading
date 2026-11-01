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
- A vendor listing with no snapshot row (``assign_listing_ids``, ``instruments/listing_history``,
  ADR 0018 amendment 2026-10-08, ADR 0087), in this order, each step only for a listing the
  earlier ones gave no id and only for a listing with a start date (a null start is a null id): (1)
  the previous snapshot's id on the same key, never upgraded (``ids_held`` counts those the
  rules would now give another id); (2) the overlapping ``symbol_history`` row's id; (3)
  ``EQ:TIINGO:<permaTicker>`` through ``equity_id``, unless another listing already holds it
  (``perma_held``); (4) the composite FIGI through ``equity_id``, only when it is on one listing
  of the frame and its id is held in ``symbol_history``, ``id_map`` or the frame by none
  (``figi_shared``, ``figi_held``: a ticker change of an instrument that has an id, never a new
  listing); (5) none, with the reason in ``no_id_reason``. ``equity_id`` is never called without
  a FIGI or a permaTicker: never ``EQ:<symbol>``.
- A listing's ``permaTicker`` (``match_perma``): from Tiingo's meta rows of its ticker by a UNIQUE
  match only, never a guess (see there).

Review state lives on the reference row: ``vendor_figi`` (the vendor's FIGI when the build
did not use it as the listing's own: a different FIGI than the one held, or one several
listings share) and ``figi_review_since`` (the session it was first seen, carried while it
persists). ``figi_review_rows`` turns them into the owner's review file.
"""

import math
from collections import Counter
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import pandas as pd

from algotrade.core.model.instruments import equity_id, is_figi_id, is_perma_id

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


def _history_ids(history: pd.DataFrame | None) -> dict[str, list[tuple[date, date | None, str]]]:
    """symbol -> (valid_from, valid_to or None, instrument_id) of its symbol_history rows."""
    out: dict[str, list[tuple[date, date | None, str]]] = {}
    if history is None or history.empty:
        return out
    start = pd.to_datetime(history["valid_from"]).dt.date
    end = pd.to_datetime(history["valid_to"]).dt.date
    for symbol, s, e, i in zip(
        history["symbol"], start, end, history["instrument_id"], strict=True
    ):
        out.setdefault(str(symbol).strip().upper(), []).append(
            (s, None if pd.isna(e) else e, str(i))
        )
    return out


TIINGO = "tiingo"
OUT_OF_SCOPE = "out_of_scope"
NO_START = "no_start"
NO_PERMA = "no_perma"
PERMA_HELD = "perma_held"
FIGI_SHARED = "figi_shared"
FIGI_HELD = "figi_held"
BY_HISTORY, BY_PERMA, BY_FIGI = "symbol_history", "perma", "figi"
HistoryIds = Mapping[str, list[tuple[date, date | None, str]]]
CarryKey = tuple[object, ...]


def _history_id(
    known: HistoryIds, ticker: object, start: date | None, end: date | None
) -> str | None:
    """The ``symbol_history`` id of ``ticker`` whose dates overlap the listing's."""
    if start is None:
        return None
    return next(
        (
            i
            for s, e, i in known.get(str(ticker), [])
            if (e is None or e >= start) and (end is None or s <= end)
        ),
        None,
    )


def history_matches(listings: pd.DataFrame, history: pd.DataFrame | None) -> pd.Series:
    """Per listing: its ticker and dates overlap a ``symbol_history`` row (step 2 of the id
    order), so the id needs no ``permaTicker``."""
    known = _history_ids(history)
    found = [
        _history_id(known, t, _date(s), _date(e)) is not None
        for t, s, e in zip(
            listings["ticker"], listings["start_date"], listings["end_date"], strict=True
        )
    ]
    return pd.Series(found, index=listings.index, dtype=bool)


def _column(frame: pd.DataFrame, name: str, default: object = None) -> list[Any]:
    return list(frame[name]) if name in frame.columns else [default] * len(frame)


def _label(value: Any) -> str | None:
    """The stripped text of a cell, ``None`` for a null or blank one."""
    if value is None or pd.isna(value) or not str(value).strip():
        return None
    return str(value).strip()


def _carry_key(
    source: object,
    ticker: object,
    exchange: object,
    asset: object,
    start: date | None,
    end: date | None,
) -> CarryKey:
    """What a listing row is on from one snapshot to the next: a Tiingo row by its table key, a
    Massive-only row (its start may be null) by (ticker, last trading day)."""
    if source == TIINGO:
        return (TIINGO, ticker, _label(exchange), _label(asset), start, end)
    return (source, ticker, end)


def _previous_listing_ids(previous: pd.DataFrame | None) -> dict[CarryKey, tuple[str, str]]:
    """Carry key -> (id, ``id_source``) of the previous snapshot's rows that held an id. A
    partition written before ``id_source`` existed gave its ids by ``symbol_history`` or the
    permaTicker only."""
    out: dict[CarryKey, tuple[str, str]] = {}
    if previous is None or previous.empty:
        return out
    cells = zip(
        _column(previous, "source", TIINGO), previous["ticker"], _column(previous, "exchange"),
        _column(previous, "asset_type"), previous["start_date"], previous["end_date"],
        _column(previous, "instrument_id"), _column(previous, "id_source"),
        _column(previous, "scope_reason"), strict=True,
    )  # fmt: skip
    for source, ticker, exchange, asset, start, end, iid, how, scope in cells:
        if _label(iid) is None or not pd.isna(scope):
            continue
        by = _label(how) or (BY_PERMA if is_perma_id(str(iid)) else BY_HISTORY)
        key = _carry_key(source, ticker, exchange, asset, _date(start), _date(end))
        out.setdefault(key, (str(iid), by))
    return out


class _ListingIds:
    """The id order of ``assign_listing_ids_counted``, one method per step, over parallel lists
    (one entry per row of ``listings``)."""

    def __init__(
        self,
        listings: pd.DataFrame,
        history: pd.DataFrame | None,
        previous: pd.DataFrame | None,
        mapped: Collection[str],
    ) -> None:
        self.n = len(listings)
        self.ticker = _column(listings, "ticker")
        self.exchange = _column(listings, "exchange")
        self.asset = _column(listings, "asset_type")
        self.start = [_date(v) for v in listings["start_date"]]
        self.end = [_date(v) for v in listings["end_date"]]
        self.source = _column(listings, "source", TIINGO)
        self.perma = [_label(v) for v in _column(listings, "perma_ticker")]
        self.figi = [_label(v) for v in _column(listings, "figi")]
        self.scope = _column(listings, "scope_reason")
        self.reason = [_label(v) for v in _column(listings, "no_id_reason")]
        self.ids: list[str | None] = [None] * self.n
        self.via: list[str | None] = [None] * self.n
        self.known = _history_ids(history)
        self.held = {str(i) for i in history["instrument_id"]} if history is not None else set()
        self.held |= set(mapped)
        self.before = _previous_listing_ids(previous)
        self.taken: set[str] = set()  # the ids the frame holds so far
        self.carried: list[int] = []
        self.shared = Counter(f for f in self.figi if f is not None)
        self._mark_unplaceable()
        self.order = sorted(
            (i for i in range(self.n) if pd.isna(self.scope[i]) and self.start[i] is not None),
            key=lambda i: (
                self.source[i] != TIINGO,
                str(self.ticker[i]),
                self.start[i],
                self.end[i] or date.max,
            ),
        )

    def _mark_unplaceable(self) -> None:
        """A row out of scope has no id; a null start is a null id, never guessed."""
        for i in range(self.n):
            if not pd.isna(self.scope[i]):
                self.reason[i] = OUT_OF_SCOPE
            elif self.start[i] is None:
                self.reason[i] = self.reason[i] or NO_START

    def _give(self, i: int, wanted: str, how: str) -> None:
        self.ids[i], self.via[i] = wanted, how
        self.taken.add(wanted)

    def carry(self) -> None:
        """1. The previous snapshot's id on the same key: an id once given is never upgraded."""
        for i in self.order:
            key = _carry_key(
                self.source[i], self.ticker[i], self.exchange[i], self.asset[i],
                self.start[i], self.end[i],
            )  # fmt: skip
            if key in self.before:
                self._give(i, *self.before[key])
                self.carried.append(i)

    def history(self) -> None:
        """2. The ``symbol_history`` id overlapping the listing."""
        for i in self.order:
            found = _history_id(self.known, self.ticker[i], self.start[i], self.end[i])
            if self.ids[i] is None and found is not None:
                self._give(i, found, BY_HISTORY)

    def perma_ids(self) -> None:
        """3. ``EQ:TIINGO:<permaTicker>``, unless another listing already holds the id."""
        for i in self.order:
            perma = self.perma[i]
            if self.ids[i] is not None or perma is None:
                continue
            wanted = equity_id(str(self.ticker[i]), perma_ticker=perma)
            if wanted in self.taken:
                self.reason[i] = PERMA_HELD
            else:
                self._give(i, wanted, BY_PERMA)

    def figi_ids(self) -> None:
        """4. The composite FIGI, only when one listing of the frame names it and no id holds it."""
        for i in self.order:
            figi = self.figi[i]
            if self.ids[i] is not None or figi is None:
                continue
            wanted = equity_id(str(self.ticker[i]), figi=figi)
            if self.shared[figi] > 1:
                self.reason[i] = FIGI_SHARED
            elif wanted in self.held or wanted in self.taken:
                self.reason[i] = FIGI_HELD
            else:
                self._give(i, wanted, BY_FIGI)

    def rule_id(self, i: int) -> str | None:
        """What the rules (steps 2 to 4, no holder check) give row ``i``."""
        found = _history_id(self.known, self.ticker[i], self.start[i], self.end[i])
        if found is None and self.perma[i] is not None:
            found = equity_id(str(self.ticker[i]), perma_ticker=self.perma[i])
        figi = self.figi[i]
        if found is None and figi is not None and self.shared[figi] == 1:
            found = equity_id(str(self.ticker[i]), figi=figi)
        return found

    def frame(self, listings: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
        """5. ``listings`` + the ids, their source and the reason of every row without one."""
        for i in self.order:
            if self.ids[i] is None and self.reason[i] is None:
                self.reason[i] = NO_PERMA
        why = [None if self.ids[i] is not None else self.reason[i] for i in range(self.n)]
        out = listings.assign(
            instrument_id=pd.Series(self.ids, index=listings.index, dtype=object),
            id_source=pd.Series(self.via, index=listings.index, dtype=object),
            no_id_reason=pd.Series(why, index=listings.index, dtype=object),
        )
        stats = {
            "ids_carried": len(self.carried),
            "ids_held": sum(self.rule_id(i) != self.ids[i] for i in self.carried),
        }
        stats.update({f"ids_by_{k}": v for k, v in Counter(v for v in self.via if v).items()})
        stats.update({f"no_id_{k}": v for k, v in Counter(w for w in why if w).items()})
        return out, stats


def assign_listing_ids(
    listings: pd.DataFrame,
    history: pd.DataFrame | None,
    previous: pd.DataFrame | None = None,
    mapped: Collection[str] = (),
) -> pd.DataFrame:
    """``assign_listing_ids_counted``'s frame alone."""
    return assign_listing_ids_counted(listings, history, previous, mapped)[0]


def assign_listing_ids_counted(
    listings: pd.DataFrame,
    history: pd.DataFrame | None,
    previous: pd.DataFrame | None = None,
    mapped: Collection[str] = (),
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Ids of the rows of ``instruments/listing_history`` (ADR 0018 amendment 2026-10-08, ADR
    0087), in the order of the module docstring: carry, ``symbol_history``, permaTicker, FIGI.
    ``listings``: ``ticker``, ``start_date``, ``end_date``, ``perma_ticker`` and, when present,
    ``source`` (default Tiingo), ``exchange``, ``asset_type``, ``figi``, ``scope_reason`` (a row
    out of scope has no id: ``out_of_scope``) and ``no_id_reason`` (a reason already known, kept
    for a row that stays without an id). ``previous``: the previous snapshot's rows; ``mapped``:
    the ``new_id`` of ``instruments/id_map``. Returns ``listings`` + ``instrument_id``,
    ``id_source`` (``symbol_history`` | ``perma`` | ``figi``) and ``no_id_reason``, and the stats
    (``ids_carried``, ``ids_held``, ``ids_by_<source>``, ``no_id_<reason>``). A row is handled in
    a fixed order (Tiingo first, then by ticker, start and end), so the first of several rows
    claiming one id gets it."""
    ids = _ListingIds(listings, history, previous, mapped)
    ids.carry()
    ids.history()
    ids.perma_ids()
    ids.figi_ids()
    return ids.frame(listings)


NO_META = "no_meta"
AMBIGUOUS = "ambiguous"


def match_perma(
    listings: pd.DataFrame, meta: pd.DataFrame, need: pd.Series | None = None
) -> tuple[pd.Series, dict[str, int]]:
    """``match_perma_reasons`` without the reasons."""
    found, _, stats = match_perma_reasons(listings, meta, need)
    return found, stats


def match_perma_reasons(
    listings: pd.DataFrame, meta: pd.DataFrame, need: pd.Series | None = None
) -> tuple[pd.Series, pd.Series, dict[str, int]]:
    """The ``permaTicker`` of the listings in ``need`` (default: all), from Tiingo's meta rows
    (``ticker``, ``perma_ticker``, ``is_active``; one per listing that ever used the ticker)
    -> (a string per listing of ``listings``, ``""`` when none, stats).

    A listing is matched only when the match is unique, ticker by ticker over ALL ``listings`` of
    the ticker (those in ``need`` and those that already have an id), never by a guess: the one
    open listing (null ``end_date``) takes the one active row, the one delisted listing the one
    inactive row (a delisted listing never takes an active row). Anything else (two or more
    delisted listings or inactive rows, extra rows) leaves the listings without a ``permaTicker``
    (``ambiguous``), a ticker with no meta row too (``no_meta``). The result holds the
    ``permaTicker`` of every matched listing of a ticker that has a listing in ``need`` (one that
    already has an id keeps it: ``assign_listing_ids`` prefers ``symbol_history``); the stats
    count only the listings in ``need``. Stats: ``perma_matched``, ``perma_no_meta``,
    ``perma_ambiguous``. The second result says why a listing in ``need`` has none
    (``perma_no_meta`` / ``perma_ambiguous``, ``""`` for the others), the ``no_id_reason`` it
    keeps when no later step gives it an id."""
    wanted = pd.Series(True, index=listings.index) if need is None else need.astype(bool)
    found = pd.Series("", index=listings.index, dtype=object)
    why = pd.Series("", index=listings.index, dtype=object)
    stats = {"perma_matched": 0, f"perma_{NO_META}": 0, f"perma_{AMBIGUOUS}": 0}
    by_ticker = {str(t): g for t, g in meta.groupby("ticker")}
    for ticker, group in listings.groupby(listings["ticker"].astype(str).str.upper()):
        rows = by_ticker.get(str(ticker))
        mine = group[wanted.loc[group.index]]
        if mine.empty:
            continue
        if rows is None or rows.empty:
            stats[f"perma_{NO_META}"] += len(mine)
            why.loc[mine.index] = f"perma_{NO_META}"
            continue
        open_ = group["end_date"].isna()
        active = rows["is_active"].astype(bool)
        pairs = []
        for listed, row_mask in ((group[open_], active), (group[~open_], ~active)):
            chosen = rows[row_mask]  # an open listing takes only an active row, and vice versa
            if len(listed) == 1 and len(chosen) == 1:
                pairs.append((listed.index[0], chosen["perma_ticker"].iloc[0]))
        for index, perma in pairs:  # every matched listing of the ticker, with an id or not
            found.loc[index] = str(perma)
        matched = sum(1 for i, _ in pairs if wanted.loc[i])
        stats["perma_matched"] += matched
        stats[f"perma_{AMBIGUOUS}"] += len(mine) - matched
        paired = {i for i, _ in pairs}
        why.loc[[i for i in mine.index if i not in paired]] = f"perma_{AMBIGUOUS}"
    return found, why, stats
