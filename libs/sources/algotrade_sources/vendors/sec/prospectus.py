"""SEC EDGAR 424B4 final prospectus: the IPO facts in its text (ADR 0050, edge build D8; free).

``fetch`` reads one filing's main document, ``/Archives/edgar/data/<cik>/<accession, no
dashes>/<document>`` (the name the submissions JSON gives), or, for an old filing that lists none,
the whole submission text ``/Archives/edgar/data/<cik>/<accession>.txt``; the document is saved as
received (HTML or text; raw retention is a few days, the task's table keeps the facts). A 404 is
"no such document" (``None``). Same pacing, ``User-Agent`` and ``sec`` limiter as the other SEC
sources.

``normalize`` returns ``parsed["ipo_facts"]``, one row (``IPO_COLUMNS``), by the rules below.
Nothing is guessed: a fact the text does not state is null and ``extraction`` says why.

Text: tags dropped, entities decoded, whitespace collapsed. **Rules (``RULES_VERSION``):**

- ``is_ipo``: a strong marker of a first public offering (no public market for the stock
  before this offering, "this is our initial public offering"). A follow-on offering has none.
  Direct listings and spin-offs file no 424B4 and are out of scope.
- ``prospectus_date``: ``Prospectus dated <Month D, YYYY>`` (the cover), else "the date of this
  prospectus is ...". The lock-up clock runs from it (the pricing date; the first trade is
  usually the next session and is not taken from the prospectus).
- ``offer_price``: the first dollar amount after "initial public offering price" (the cover
  table's per-share column), 0.5 to 5,000.
- ``ticker`` / ``exchange``: the first quoted ``symbol "XXXX"`` and the first named exchange
  (``NASDAQ`` or ``NYSE`` family).
- **Lock-up terms**: only inside sentences about a lock-up (naming one, or next to one that
  does; not the over-allotment option's), and only a term anchored to the prospectus date
  ("180 days after the date of this prospectus", "the 180-day period beginning on the date of this
  prospectus", "six months ... the date of this prospectus"). ``lockup_terms``
  lists every distinct term with its count ("180 days x14; 90 days x3"). ``lockup_n`` /
  ``lockup_unit`` (days or months; a year is 12 months) are set only when one term is the answer:
  the only one, or the most frequent with at least twice the count of the next (the main lock-up
  is repeated in every section, a carve-out for one holder is not). Otherwise ``extraction`` is
  ``AMBIGUOUS`` and both are null. A day term from another anchor (the closing, the underwriting
  agreement) is ``UNANCHORED``; no term at all is ``NO_LOCKUP``; a blank check company is
  ``SPAC`` (its founders' lock-up runs from a business combination, no date at the IPO). Not an
  IPO: ``NOT_IPO``. ``EXTRACTED`` is the one status with a term.
- **Early release** (``early_release``, ``early_release_text``): a sentence about a lock-up with
  a contractual trigger (an earnings release, a price threshold or volume-weighted price, a
  staged share of the holdings). The representatives' discretionary release, in every prospectus,
  is not one. The term is the nominal length; an early release only shortens it.
"""

import html
import re
from datetime import UTC, date, datetime

import pandas as pd

from algotrade.core.model.instruments import pad_cik
from algotrade_sources.framework.base import FetchRequest, Normalized
from algotrade_sources.framework.http import Http
from algotrade_sources.framework.series import (
    IPO_COLUMNS,
    IPO_EXTRACTED,
    IPO_FRAME,
    IPO_RULES_VERSION,
    ProspectusRequest,
)

SOURCE = "sec_edgar"
DATASET = "prospectus"
RULES_VERSION = IPO_RULES_VERSION  # bump with any rule below: the task re-reads older rows
DOCUMENT_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{folder}/{document}"
SUBMISSION_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}.txt"
EXTRACTED, NOT_IPO, NO_LOCKUP = IPO_EXTRACTED, "NOT_IPO", "NO_LOCKUP"
AMBIGUOUS, UNANCHORED, SPAC = "AMBIGUOUS", "UNANCHORED", "SPAC"
DOMINANCE = 2  # the main term has at least this many times the next one's mentions
EARLY_TEXT_CHARS = 400
_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "eighteen": 18,
}  # fmt: skip
_COUNT = rf"(?P<n>\d{{1,3}}|{'|'.join(_NUMBERS)})"
_ANCHOR = r"the\s+date\s+of\s+(?:this|the\s+final)\s+(?:final\s+)?prospectus"
_TERM = re.compile(
    rf"{_COUNT}[\s-]+(?P<unit>day|month|year)s?(?:[\s-]+(?:lock-?up\s+)?(?:restricted\s+)?period)?"
    rf"(?:\s+(?:immediately\s+)?(?:after|from|following|beginning\s+on|commencing\s+on|"
    rf"starting\s+on)\s+{_ANCHOR})",
    re.IGNORECASE,
)
_ANY_DAYS = re.compile(r"\b(?P<n>\d{2,3})[\s-]+days?\b", re.IGNORECASE)
_LOCKUP = re.compile(r"lock-?\s?up", re.IGNORECASE)
_OPTION = re.compile(r"over-?allotment|option\s+to\s+purchase|option\s+to\s+buy", re.IGNORECASE)
_SENTENCE = re.compile(r"(?<=[.;])\s+(?=[A-Z\"“(])")
_IPO = re.compile(
    r"(?:there\s+(?:has\s+been|was|is)\s+no\s+(?:established\s+)?public\s+(?:trading\s+)?market\s+for"
    r"|prior\s+to\s+this\s+offering,?\s+there\s+(?:has\s+been|was)\s+no\s+public"
    r"|this\s+is\s+(?:the|our)\s+(?:company's\s+)?(?:initial\s+public\s+offering|first\s+public))",
    re.IGNORECASE,
)
_SPAC = re.compile(r"blank\s+check\s+company", re.IGNORECASE)
_DATED = re.compile(
    r"prospectus\s+dated\s+(?P<d>[A-Z][a-z]+\.?\s+\d{1,2},\s+\d{4})"
    r"|the\s+date\s+of\s+this\s+prospectus\s+is\s+(?P<e>[A-Z][a-z]+\.?\s+\d{1,2},\s+\d{4})",
    re.IGNORECASE,
)
_PRICE = re.compile(
    r"initial\s+public\s+offering\s+price(?:\s+(?:of|is|was))?(?:\s+per\s+\w+)?[\s:.]*\$\s*"
    r"(?P<p>\d[\d,]*(?:\.\d+)?)",
    re.IGNORECASE,
)
_SYMBOL = re.compile(r"symbols?\s+[“\"']\s*(?P<s>[A-Z][A-Z.\-]{0,5})\s*[”\"']")
_EXCHANGE = re.compile(
    r"(?P<x>nasdaq\s+(?:global\s+select\s+market|global\s+market|capital\s+market)|nasdaq|"
    r"new\s+york\s+stock\s+exchange|nyse\s+american|nyse\s+arca|nyse)",
    re.IGNORECASE,
)
_EARLY = re.compile(
    r"earnings\s+(?:release|announcement|report)|volume[\s-]weighted|"
    r"(?:closing|trading|last\s+reported\s+sale)\s+price|"
    r"(?:exceeds?|above|at\s+least)\s+\d+(?:\.\d+)?\s*%|"
    r"\d+(?:\.\d+)?\s*%\s+of\s+(?:the\s+)?(?:shares|securities|holdings)|"
    r"(?:one|two|three|\d+)\s+(?:trading|business)\s+days?\s+(?:after|following)\s+(?:the\s+)?"
    r"(?:public\s+)?(?:release|announcement)",
    re.IGNORECASE,
)
_TAGS = re.compile(r"<[^>]+>")
_SKIP_BLOCKS = re.compile(r"<(script|style)\b.*?</\1>", re.IGNORECASE | re.DOTALL)


def plain_text(payload: bytes) -> str:
    """The document's visible text: scripts dropped, tags replaced by spaces, entities decoded,
    whitespace collapsed (a ``.txt`` submission passes through, its SGML wrapper tags dropped)."""
    text = _SKIP_BLOCKS.sub(" ", payload.decode("utf-8", errors="replace"))
    return " ".join(html.unescape(_TAGS.sub(" ", text)).replace("\xa0", " ").split())


def _count(raw: str) -> int:
    return int(raw) if raw.isdigit() else _NUMBERS[raw.lower()]


def _months(n: int, unit: str) -> tuple[int, str]:
    return (n * 12, "months") if unit == "year" else (n, "months" if unit == "month" else "days")


def lockup_sentences(text: str) -> list[str]:
    """The sentences about a lock-up: those that name one and their neighbours (a heading
    "Lock-Up Agreements" ends no sentence, but the term may sit one sentence away), without the
    over-allotment option's, whose "30 days after the date of this prospectus" is no lock-up."""
    parts = _SENTENCE.split(text)
    named = [bool(_LOCKUP.search(p)) for p in parts]
    near = [
        any(named[max(0, i - 1) : i + 2]) and not _OPTION.search(parts[i])
        for i in range(len(parts))
    ]
    return [p for p, keep in zip(parts, near, strict=True) if keep]


def lockup_terms(sentences: list[str]) -> dict[tuple[int, str], int]:
    """(length, unit) -> mentions, of the prospectus-date-anchored terms in ``sentences``."""
    found: dict[tuple[int, str], int] = {}
    for sentence in sentences:
        for match in _TERM.finditer(sentence):
            term = _months(_count(match["n"]), match["unit"].lower())
            found[term] = found.get(term, 0) + 1
    return found


def describe(terms: dict[tuple[int, str], int]) -> str | None:
    """``"180 days x14; 90 days x3"``: the terms, most mentioned first."""
    ordered = sorted(terms.items(), key=lambda kv: (-kv[1], kv[0][1], kv[0][0]))
    return "; ".join(f"{n} {unit} x{count}" for (n, unit), count in ordered) or None


def main_term(terms: dict[tuple[int, str], int]) -> tuple[int, str] | None:
    """The one term that is the lock-up: the only one, or the most mentioned with at least
    ``DOMINANCE`` times the next; ``None`` otherwise (module doc)."""
    ranked = sorted(terms.items(), key=lambda kv: -kv[1])
    if not ranked:
        return None
    if len(ranked) == 1 or ranked[0][1] >= DOMINANCE * ranked[1][1]:
        return ranked[0][0]
    return None


def early_release(sentences: list[str]) -> str | None:
    """The first sentence about a lock-up with a contractual early-release trigger."""
    for sentence in sentences:
        if _EARLY.search(sentence):
            return sentence[:EARLY_TEXT_CHARS]
    return None


def _date(text: str) -> date | None:
    cleaned = text.replace(".", "").split()
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(" ".join(cleaned), fmt).replace(tzinfo=UTC).date()
        except ValueError:
            continue
    return None


def _prospectus_date(text: str) -> date | None:
    match = _DATED.search(text)
    return _date(match["d"] or match["e"]) if match else None


def _offer_price(text: str) -> float | None:
    match = _PRICE.search(text)
    price = float(match["p"].replace(",", "")) if match else None
    return price if price is not None and 0.5 <= price <= 5000 else None


def _exchange(text: str) -> str | None:
    match = _EXCHANGE.search(text)
    if match is None:
        return None
    return "NASDAQ" if match["x"].lower().startswith("nasdaq") else "NYSE"


def extract(text: str) -> dict[str, object]:
    """One prospectus's IPO facts (``IPO_COLUMNS``) by the module doc's rules."""
    ipo = _IPO.search(text) is not None
    sentences = lockup_sentences(text)
    terms = lockup_terms(sentences)
    symbol = _SYMBOL.search(text)
    row: dict[str, object] = {
        "is_ipo": ipo,
        "prospectus_date": _prospectus_date(text),
        "ticker": symbol["s"] if symbol else None,
        "exchange": _exchange(text),
        "offer_price": _offer_price(text),
        "lockup_n": None,
        "lockup_unit": None,
        "lockup_terms": describe(terms),
        "early_release": False,
        "early_release_text": None,
        "extraction": NOT_IPO,
        "reason": "no first-public-offering marker: a follow-on or a debt offering",
    }
    if not ipo:
        return row
    clause = early_release(sentences)
    row["early_release"], row["early_release_text"] = clause is not None, clause
    if _SPAC.search(text):
        row["extraction"] = SPAC
        row["reason"] = (
            "blank check company: the founders' lock-up runs from a business combination"
        )
    elif not terms:
        unanchored = sorted({int(m["n"]) for s in sentences for m in _ANY_DAYS.finditer(s)})
        row["extraction"] = UNANCHORED if unanchored else NO_LOCKUP
        row["reason"] = (
            f"lock-up of {', '.join(map(str, unanchored))} days not counted from the prospectus "
            "date"
            if unanchored
            else "no lock-up term counted from the prospectus date in the text"
        )
    elif (term := main_term(terms)) is None:
        row["extraction"], row["reason"] = AMBIGUOUS, f"no dominant lock-up term: {describe(terms)}"
    else:
        row["lockup_n"], row["lockup_unit"] = term
        row["extraction"], row["reason"] = EXTRACTED, None
    return row


def parse_facts(payload: bytes) -> pd.DataFrame:
    """The one-row IPO facts frame (``IPO_COLUMNS``) of a prospectus document."""
    text = plain_text(payload)
    if not text:
        raise ValueError("SEC prospectus document is empty")
    frame = pd.DataFrame([extract(text)], columns=list(IPO_COLUMNS))
    frame["lockup_n"] = frame["lockup_n"].astype("Int64")
    frame["offer_price"] = frame["offer_price"].astype("float64")
    return frame


def prospectus_request(request: FetchRequest) -> ProspectusRequest:
    """``request`` as a ``ProspectusRequest`` (this source takes no other kind)."""
    if not isinstance(request, ProspectusRequest):
        raise TypeError(f"SEC prospectus needs a ProspectusRequest, got {type(request).__name__}")
    return request


def document_url(request: ProspectusRequest) -> str:
    """Where the prospectus is: its main document, else the whole submission text."""
    cik = pad_cik(request.cik)
    if cik is None:
        raise ValueError(f"not a CIK: {request.cik!r}")
    if "/" in request.document or "\\" in request.document or ".." in request.document:
        raise ValueError(f"unexpected prospectus document name: {request.document!r}")
    if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", request.key):
        raise ValueError(f"not an accession number: {request.key!r}")
    if request.document:
        folder = request.key.replace("-", "")
        return DOCUMENT_URL.format(cik=int(cik), folder=folder, document=request.document)
    return SUBMISSION_URL.format(cik=int(cik), accession=request.key)


class SecProspectus:
    """Implements ``sources.base.Source``. Request: a ``ProspectusRequest``."""

    name = SOURCE
    dataset = DATASET

    def __init__(self, http: Http) -> None:
        self._http = http  # paced by the shared ``sec`` limiter; sets the User-Agent itself

    def fetch(self, request: FetchRequest) -> bytes | None:
        return self._http.get(document_url(prospectus_request(request)))

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        return Normalized(session_date=None, tables={}, parsed={IPO_FRAME: parse_facts(payload)})
