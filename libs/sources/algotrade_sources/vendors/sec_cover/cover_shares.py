"""SEC periodic-filing cover XBRL -> shares outstanding per share class (free, no key).

A 10-K / 10-Q / 20-F / 40-F tags its cover page in the filing's XBRL instance:
``dei:EntityCommonStockSharesOutstanding`` once per class, each in a context whose only dimension
is ``us-gaap:StatementClassOfStockAxis`` (the member is ``us-gaap:CommonClassAMember`` or a
company's own, ``goog:CapitalClassAMember``), and ``dei:TradingSymbol`` / ``dei:Security12bTitle``
in the context of the same member. A single-class filer tags the shares in a context with no
dimension (its ``class_member`` is ``None``). A class with no symbol fact (unlisted) keeps a null
``trading_symbol``; a filing with no cover tags (most 40-F) gives an empty answer.

Two requests per filing, on the shared ``sec`` limiter (10 requests a second at most, contact
``User-Agent``; ``[sec_edgar]``): the filing's ``index.json`` (the instance file is only used when
it is listed there) and the instance, ``<primary document stem>_htm.xml`` under
``https://www.sec.gov/Archives/edgar/data/<cik>/<accession without dashes>/``. A 404 on either is
an empty answer (no XBRL for this filing); an empty body or a block page raises
``TransientFetchError``; XML that does not parse, a document type declaration (entity expansion
is an attack) or a share count that is not a whole number raises ``CoverParseError``.

``fetch`` saves the parsed rows as compact JSON (never the instance); ``normalize`` returns
``parsed[COVER_SHARES_FRAME]``. ``parse_cover_shares`` is pure and returns ``ClassShares`` rows
sorted by class member (the undimensioned row first), so the same instance always gives the same
answer. ``as_of`` is the date the shares were counted (the fact's context instant, a few weeks
after the period); ``period_end`` is the report's own period (``dei:DocumentPeriodEndDate``).
Nothing is stored here: the task that stores the rows stamps ``known_from`` and the instrument id.
"""

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

import pandas as pd

from algotrade.core.model.instruments import pad_cik
from algotrade_sources.framework.base import FetchRequest, Normalized, TransientFetchError
from algotrade_sources.framework.http import Http
from algotrade_sources.framework.series import (
    COVER_SHARES_COLUMNS,
    COVER_SHARES_FRAME,
    FilingTextRequest,
)

SOURCE = "sec_edgar"
DATASET = "cover_shares"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{name}"
PERIODIC_FORMS = ("10-K", "10-Q", "20-F", "40-F")
_ACCESSION = re.compile(r"\d{10}-\d{2}-\d{6}")
_DOCUMENT = re.compile(r"[A-Za-z0-9][\w.\-]*\.(?:htm|html)", re.IGNORECASE)
_BLOCKED = (b"Request Rate Threshold", b"Undeclared Automated Tool")  # SEC's 200-status block pages
_XBRLI = "{http://www.xbrl.org/2003/instance}"
_XBRLDI = "{http://xbrl.org/2006/xbrldi}"
_DEI = "http://xbrl.sec.gov/dei/"
_CLASS_AXIS = "us-gaap:StatementClassOfStockAxis"
_SHARES, _SYMBOL, _TITLE, _PERIOD_END = (
    "EntityCommonStockSharesOutstanding",
    "TradingSymbol",
    "Security12bTitle",
    "DocumentPeriodEndDate",
)


class CoverParseError(ValueError):
    """The instance is not XML we accept, or a cover fact is not what its tag promises."""


@dataclass(frozen=True)
class ClassShares:
    """One share class of one filing: shares outstanding as of ``as_of``."""

    cik: str  # 10 digits
    accession: str
    class_member: str | None  # ``us-gaap:CommonClassAMember``; None: the filing has one class
    shares: int
    as_of: date
    period_end: date | None
    trading_symbol: str | None
    security_title: str | None


def _day(text: str, what: str) -> date:
    try:
        return date.fromisoformat(text.strip())
    except ValueError as exc:
        raise CoverParseError(f"{what} is not a date: {text!r}") from exc


def _member(context: ET.Element) -> tuple[bool, str | None]:
    """(usable, class member): usable unless the context has a dimension other than the class
    axis; the member is None when it has no dimension at all."""
    members = list(context.iter(f"{_XBRLDI}explicitMember")) + list(
        context.iter(f"{_XBRLDI}typedMember")
    )
    if not members:
        return True, None
    if len(members) == 1 and members[0].get("dimension") == _CLASS_AXIS:
        return True, (members[0].text or "").strip() or None
    return False, None


def _contexts(root: ET.Element) -> dict[str, tuple[str | None, date | None]]:
    """context id -> (class member, instant) for the contexts the cover can use."""
    out: dict[str, tuple[str | None, date | None]] = {}
    for context in root.iter(f"{_XBRLI}context"):
        usable, member = _member(context)
        cid = context.get("id")
        if not usable or not cid:
            continue
        instant = context.find(f"{_XBRLI}period/{_XBRLI}instant")
        text = instant.text if instant is not None and instant.text else None
        out[cid] = (member, _day(text, f"context {cid} instant") if text else None)
    return out


def _count(text: str) -> int:
    try:
        count = Decimal(text.replace(",", ""))
    except InvalidOperation as exc:
        raise CoverParseError(f"shares outstanding is not a number: {text!r}") from exc
    if count != count.to_integral_value() or count < 0:
        raise CoverParseError(f"shares outstanding is not a whole count: {text!r}")
    return int(count)


def _local(tag: str) -> tuple[str, str]:
    namespace, _, name = tag.rpartition("}")
    return namespace.lstrip("{"), name


def parse_cover_shares(xml: bytes, cik: str, accession: str) -> tuple[ClassShares, ...]:
    """The cover share classes of one XBRL instance, sorted (module doc). Empty when the
    instance tags no ``EntityCommonStockSharesOutstanding``."""
    padded = pad_cik(cik)
    if padded is None or _ACCESSION.fullmatch(accession) is None:
        raise ValueError(f"not a CIK / accession: {cik!r} / {accession!r}")
    if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
        raise CoverParseError("XBRL instance has a document type declaration")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise CoverParseError(f"XBRL instance is not well-formed XML: {exc}") from exc
    contexts = _contexts(root)
    shares: dict[str | None, tuple[date, int]] = {}  # member -> (as_of, shares), latest as_of wins
    symbols: dict[str | None, set[str]] = {}
    titles: dict[str | None, set[str]] = {}
    period_end: date | None = None
    for fact in root.iter():
        namespace, name = _local(fact.tag)
        if not namespace.startswith(_DEI) or name not in (_SHARES, _SYMBOL, _TITLE, _PERIOD_END):
            continue
        context = contexts.get(fact.get("contextRef", ""))
        text = (fact.text or "").strip()
        if context is None or not text:
            continue  # a nil or empty fact, or a context with more dimensions
        member, instant = context
        if name == _PERIOD_END and member is None:
            period_end = _day(text, "DocumentPeriodEndDate")
        elif name == _SYMBOL:
            symbols.setdefault(member, set()).add(text)
        elif name == _TITLE:
            titles.setdefault(member, set()).add(text)
        elif name == _SHARES:
            if instant is None:
                raise CoverParseError(f"shares outstanding for {member!r} has no instant")
            if member not in shares or instant > shares[member][0]:
                shares[member] = (instant, _count(text))
    rows = [
        ClassShares(
            cik=padded,
            accession=accession,
            class_member=member,
            shares=count,
            as_of=as_of,
            period_end=period_end,
            trading_symbol=min(symbols[member]) if member in symbols else None,
            security_title=min(titles[member]) if member in titles else None,
        )
        for member, (as_of, count) in shares.items()
    ]
    return tuple(sorted(rows, key=lambda r: (r.class_member is not None, r.class_member or "")))


def instance_name(primary_document: str) -> str:
    """The inline-XBRL instance file of a primary document: ``aapl-20240928.htm`` ->
    ``aapl-20240928_htm.xml`` (a file name, never a path)."""
    if _DOCUMENT.fullmatch(primary_document) is None:
        raise ValueError(f"unexpected primary document name: {primary_document!r}")
    return primary_document.rsplit(".", 1)[0] + "_htm.xml"


def archive_url(cik: str, accession: str, name: str) -> str:
    """The archive URL of one file of a filing (``cik`` without leading zeros, the accession
    without dashes)."""
    padded = pad_cik(cik)
    if padded is None or _ACCESSION.fullmatch(accession) is None:
        raise ValueError(f"not a CIK / accession: {cik!r} / {accession!r}")
    return ARCHIVE_URL.format(cik=int(padded), accession=accession.replace("-", ""), name=name)


def _listed(index: bytes) -> set[str]:
    try:
        items = json.loads(index)["directory"]["item"]
        return {str(item["name"]) for item in items}
    except (ValueError, KeyError, TypeError) as exc:
        raise CoverParseError(f"filing index.json is not a directory listing: {exc}") from exc


def cover_request(request: FetchRequest) -> FilingTextRequest:
    """``request`` as the filing to read (a ``FilingTextRequest``: ``key`` the accession, ``cik``,
    ``form`` a periodic form or its amendment, ``primary_document``; ``items`` is not used)."""
    if not isinstance(request, FilingTextRequest):
        raise TypeError(f"SEC cover shares need a FilingTextRequest, got {type(request).__name__}")
    if request.form.removesuffix("/A") not in PERIODIC_FORMS:
        raise ValueError(f"not a periodic report form: {request.form!r}")
    return request


def payload_of(rows: tuple[ClassShares, ...]) -> bytes:
    """The compact JSON ``fetch`` saves: the parsed rows, never the instance (3-10 MB)."""
    document = {
        "rows": [
            {
                **asdict(r),
                "as_of": r.as_of.isoformat(),
                "period_end": r.period_end.isoformat() if r.period_end else None,
            }
            for r in rows
        ]
    }
    return json.dumps(document, separators=(",", ":")).encode("utf-8")


class SecCoverShares:
    """Implements ``sources.base.Source``. Request: a ``FilingTextRequest`` for a periodic
    report. ``fetch`` answers ``None`` when the filing has no instance and a payload with no rows
    when it tags no cover shares; ``normalize`` returns ``parsed[COVER_SHARES_FRAME]``
    (``COVER_SHARES_COLUMNS``). The task that stores the rows is a later change."""

    name = SOURCE
    dataset = DATASET

    def __init__(self, http: Http) -> None:
        self._http = http  # paced by the shared ``sec`` limiter; sets the User-Agent itself

    def _get(self, url: str) -> bytes | None:
        body = self._http.get(url)
        if body is None:
            return None
        if not body.strip() or any(mark in body[:20_000] for mark in _BLOCKED):
            raise TransientFetchError(f"SEC {url}: empty or a block page")
        return body

    def read(
        self, cik: str, accession: str, primary_document: str
    ) -> tuple[ClassShares, ...] | None:
        """The cover classes of one filing; ``None`` when it has no instance (404, or not listed
        in its ``index.json``), empty when it tags no cover shares."""
        name = instance_name(primary_document)
        index = self._get(archive_url(cik, accession, "index.json"))
        if index is None or name not in _listed(index):
            return None
        xml = self._get(archive_url(cik, accession, name))
        return None if xml is None else parse_cover_shares(xml, cik, accession)

    def fetch(self, request: FetchRequest) -> bytes | None:
        wanted = cover_request(request)
        rows = self.read(wanted.cik, wanted.key, wanted.primary_document)
        return None if rows is None else payload_of(rows)

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        document = json.loads(payload)
        frame = pd.DataFrame(document["rows"], columns=list(COVER_SHARES_COLUMNS))
        for column in ("as_of", "period_end"):
            frame[column] = frame[column].map(lambda t: date.fromisoformat(t) if t else None)
        frame = frame.astype({"shares": "int64"}).astype(object)
        frame = frame.where(frame.notna(), None)  # a missing symbol / date is None, not NaN
        return Normalized(session_date=None, tables={}, parsed={COVER_SHARES_FRAME: frame})
