"""The reviewed dossier of a name (ADR 0050 decision 6, EV5): the schema of the TOML file the
``event-deep-dive`` skill writes (documented in the skill's ``dossier-format.md``), its
validation and its rows. Pure: the ticker resolver and the session are arguments, nothing is read
or stored.

A dossier is checked whole and either yields every row or a list of every problem (an import
stores nothing from a file with one): the ticker resolves to an instrument id, the review date is
no later than the import session, factors have a unique slug id, a kind and a status from the
closed sets, dated occurrences and expected windows are well formed, and every reviewed
attribution names a past session, a cause of the taxonomy, a confidence in [0, 1] and cites its
evidence. Rows carry ``known_from`` = the import session (a session before the import never sees
them) and, for the attributions, ``source = "analyst_review"``."""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from algotrade.core.time.calendar import is_session
from algotrade.services.attributing.taxonomy import CAUSES
from algotrade.storage.tables.schemas import FACTOR_KINDS, FACTOR_STATUSES

SCHEMA = 1
SOURCE = "analyst_review"
SLUG = re.compile(r"^[a-z][a-z0-9_-]{1,40}$")
FIRST_DAY = date(2018, 1, 1)  # the history the event study holds


class DossierError(ValueError):
    """A dossier that fails validation; ``problems`` lists every one, ``str`` joins them."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass
class Dossier:
    instrument_id: str
    reviewed_on: date
    factors: list[dict[str, Any]] = field(default_factory=list)
    occurrences: list[dict[str, Any]] = field(default_factory=list)
    attributions: list[dict[str, Any]] = field(default_factory=list)


def _midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


class _Reader:
    """Accumulates problems with the path of the table they came from."""

    def __init__(self) -> None:
        self.problems: list[str] = []

    def text(self, table: Mapping[str, Any], key: str, where: str, *, required: bool = True) -> str:
        value = table.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if required or value is not None:
            self.problems.append(f"{where}: `{key}` must be a non-empty string")
        return ""

    def day(
        self, table: Mapping[str, Any], key: str, where: str, *, required: bool = True
    ) -> date | None:
        value = table.get(key)
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if required or value is not None:
            self.problems.append(f"{where}: `{key}` must be a TOML date (YYYY-MM-DD)")
        return None


def _factor(r: _Reader, entry: Mapping[str, Any], n: int, seen: set[str]) -> dict[str, Any] | None:
    where = f"factor[{n}]"
    fid = r.text(entry, "id", where)
    if fid and not SLUG.match(fid):
        r.problems.append(f"{where}: id {fid!r} is not a slug (lower case, digits, - and _)")
    if fid in seen:
        r.problems.append(f"{where}: duplicate factor id {fid!r}")
    seen.add(fid)
    kind = r.text(entry, "kind", where)
    if kind and kind not in FACTOR_KINDS:
        r.problems.append(f"{where}: kind {kind!r} is not one of {', '.join(FACTOR_KINDS)}")
    status = str(entry.get("status", "active"))
    if status not in FACTOR_STATUSES:
        r.problems.append(f"{where}: status {status!r} is not active or retired")
    description = r.text(entry, "description", where)
    return {"factor_id": fid, "kind": kind, "status": status, "description": description}


def _occurrences(
    r: _Reader, entry: Mapping[str, Any], fid: str, n: int, iid: str, session: date
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[date] = set()  # the table key is (ts, factor): a day holds one entry per factor
    for m, item in enumerate(entry.get("occurrence", []) or []):
        where = f"factor[{n}].occurrence[{m}]"
        day = r.day(item, "date", where)
        label = r.text(item, "label", where)
        if day is None:
            continue
        if day < FIRST_DAY:
            r.problems.append(f"{where}: date {day} is before {FIRST_DAY}")
        if day in seen:
            r.problems.append(f"{where}: factor already has an entry starting {day}")
        seen.add(day)
        out.append(_occurrence_row(iid, fid, _midnight(day), label, "dated", None))
    for m, item in enumerate(entry.get("watch", []) or []):
        where = f"factor[{n}].watch[{m}]"
        start = r.day(item, "expected_from", where)
        end = r.day(item, "expected_to", where)
        label = r.text(item, "label", where)
        if start is None or end is None:
            continue
        if start in seen:
            r.problems.append(f"{where}: factor already has an entry starting {start}")
        seen.add(start)
        if end < start:
            r.problems.append(f"{where}: expected_to {end} is before expected_from {start}")
        elif end < session:
            r.problems.append(
                f"{where}: the window ends {end}, before the import session {session}"
            )
        out.append(_occurrence_row(iid, fid, _midnight(start), label, "window", end))
    return out


def _occurrence_row(
    iid: str, fid: str, ts: datetime, label: str, kind: str, end: date | None
) -> dict[str, Any]:
    return {
        "instrument_id": iid, "ts": ts, "factor_id": fid, "label": label, "date_kind": kind,
        "window_end": end,
    }  # fmt: skip


def _attribution(
    r: _Reader, entry: Mapping[str, Any], n: int, iid: str, session: date, reviewed: date | None
) -> dict[str, Any] | None:
    where = f"attribution[{n}]"
    day = r.day(entry, "date", where)
    cause = r.text(entry, "cause", where)
    text = r.text(entry, "text", where)
    evidence = r.text(entry, "evidence", where)
    ref = r.text(entry, "evidence_ref", where, required=False)
    confidence = entry.get("confidence")
    if cause and cause not in CAUSES:
        r.problems.append(f"{where}: cause {cause!r} is not in the taxonomy ({', '.join(CAUSES)})")
    if isinstance(confidence, bool) or not isinstance(confidence, int | float):
        r.problems.append(f"{where}: `confidence` must be a number in 0..1")
        confidence = 0.0
    elif not 0 <= confidence <= 1:
        r.problems.append(f"{where}: confidence {confidence} is outside 0..1")
    if day is None:
        return None
    if not is_session(day):
        r.problems.append(f"{where}: {day} is not a trading session")
    elif day > session or (reviewed and day > reviewed):
        r.problems.append(f"{where}: {day} is after the review / import date")
    elif day < FIRST_DAY:
        r.problems.append(f"{where}: {day} is before {FIRST_DAY}")
    return {
        "instrument_id": iid, "ts": _midnight(day), "session_date": day, "cause_class": cause,
        "cause_text": text, "confidence": float(confidence), "evidence": evidence,
        "evidence_ref": ref or None, "model": None, "prompt_version": None,
    }  # fmt: skip


def parse_dossier(
    doc: Mapping[str, Any], session: date, resolve: Callable[[str], str | None]
) -> Dossier:
    """The validated dossier of ``doc`` (a parsed TOML file) for an import on ``session``;
    ``resolve`` turns a ticker into an instrument id (None: unknown). Raises ``DossierError``
    with every problem found."""
    r = _Reader()
    if doc.get("schema") != SCHEMA:
        r.problems.append(f"`schema` must be {SCHEMA}")
    ticker = r.text(doc, "ticker", "dossier")
    iid = resolve(ticker) if ticker else None
    if ticker and iid is None:
        r.problems.append(f"dossier: ticker {ticker!r} is not in the reference snapshot")
    reviewed = r.day(doc, "reviewed_on", "dossier")
    if reviewed and reviewed > session:
        r.problems.append(f"dossier: reviewed_on {reviewed} is after the import session {session}")
    out = Dossier(iid or "", reviewed or session)
    attributed: set[date] = set()
    seen: set[str] = set()
    for n, entry in enumerate(doc.get("factor", []) or []):
        factor = _factor(r, entry, n, seen)
        if factor is not None:
            out.factors.append(factor)
            out.occurrences += _occurrences(r, entry, factor["factor_id"], n, iid or "", session)
    if not out.factors:
        r.problems.append("dossier: at least one [[factor]] (the review date lives on the factors)")
    for n, entry in enumerate(doc.get("attribution", []) or []):
        row = _attribution(r, entry, n, iid or "", session, reviewed)
        if row is not None:
            if row["session_date"] in attributed:
                r.problems.append(f"attribution[{n}]: {row['session_date']} is attributed twice")
            attributed.add(row["session_date"])
            out.attributions.append(row)
    if r.problems:
        raise DossierError(r.problems)
    return out
