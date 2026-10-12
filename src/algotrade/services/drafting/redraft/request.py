"""The request of one part's re-draft, re-validated (ADR 0041, amended 2026-10-12). The browser
sends back the draft it holds (the sentence, the Builder's current document, the explained parts
and the items they point at) and says which part's words are retyped and as what. Nothing in it
is trusted: the sentence is normalised as ``draft_screen`` does, every part's ``words`` must be
the sentence's own slice at its UTF-16 offsets (in order, not overlapping), every id a part
names must be an item the draft holds (a criterion the trader deleted from the document since is
only dropped from the part, not an error; one criterion in two parts is), the part retyped must
have words of its own (not the ``kept`` / ``unplaced`` catch-alls), the new words are at most
``MAX_WORDS`` characters, and the sentence with them in place at most ``MAX_TEXT``. A request that
fails any check is a ``ConfigurationError`` (400) before anything is asked or counted. ``kind``
of a part is the server's, so the one the browser sends is not read. Pure."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from algotrade.core.model.errors import ConfigurationError
from algotrade.services.drafting.contract.formulas import DraftFormula, DroppedFormula
from algotrade.services.drafting.contract.gaps import Alternative, MissingFeature, Unresolved
from algotrade.services.drafting.contract.suggestions import DroppedSuggestion, Suggestion
from algotrade.services.drafting.parts.build import kind_of
from algotrade.services.drafting.parts.model import (
    KEPT_ID,
    MAX_PARTS,
    MAX_READING,
    MAX_WORDS,
    UNPLACED_ID,
    Part,
)
from algotrade.services.drafting.screens import MAX_TEXT, DroppedCriterion, ScreenDraft
from algotrade.services.preview.expressions import DryRun, SampleValue

MAX_ITEMS = 40  # of each list of a draft a request may carry back (the merge keeps within it)
MAX_CRITERIA = 60  # criteria in the Builder's document
CATCH_ALLS = (KEPT_ID, UNPLACED_ID)
SHARED = ("missing",)  # a request may be named by two parts (one key, two spans)


@dataclass(frozen=True)
class PartRequest:
    """A re-draft request that holds together. ``prior`` is the draft the browser holds (its
    ``document`` the Builder's, edits included; ``parts`` and the items as sent); ``part`` the one
    whose ``old_words`` become ``new_words`` (normalised); ``merged`` the sentence with them in
    place; ``spans`` the code-point (start, end) of every part that has words, in ``sentence``."""

    screener_id: str
    sentence: str
    prior: ScreenDraft
    part: Part
    old_words: str
    new_words: str
    merged: str
    spans: Mapping[str, tuple[int, int]]

    @property
    def criteria(self) -> Mapping[str, Any]:
        """The criteria of the Builder's current document."""
        held = self.prior.document.get("criteria")
        return held if isinstance(held, Mapping) else {}


def check_request(screener_id: str, body: Mapping[str, Any]) -> PartRequest:
    """The re-draft request of ``body`` (the browser's draft and ``part_id``, ``new_words``), or
    ``ConfigurationError`` naming the check it fails."""
    sentence = " ".join(str(body.get("sentence") or "").split())
    if not sentence:
        raise ConfigurationError(f"{screener_id}: the sentence is empty")
    if len(sentence) > MAX_TEXT:
        raise ConfigurationError(f"{screener_id}: the sentence is over {MAX_TEXT} characters")
    new_words = " ".join(str(body.get("new_words") or "").split())
    if not new_words:
        raise ConfigurationError(f"{screener_id}: the new words are empty")
    if len(new_words) > MAX_WORDS:
        raise ConfigurationError(f"{screener_id}: the new words are over {MAX_WORDS} characters")
    document = _checked_document(screener_id, body.get("document"))
    parts = [_part(p) for p in body.get("parts") or ()]
    spans = _spans(screener_id, sentence, parts)
    prior = _prior(screener_id, sentence, document, parts, body)
    _refs(screener_id, prior)
    chosen = next((p for p in parts if p.id == body.get("part_id")), None)
    if chosen is None:
        raise ConfigurationError(f"{screener_id}: the draft has no part {body.get('part_id')!r}")
    if chosen.id not in spans:
        raise ConfigurationError(
            f"{screener_id}: part {chosen.id!r} has no words of its own to retype"
        )
    start, end = spans[chosen.id]
    merged = sentence[:start] + new_words + sentence[end:]
    if len(merged) > MAX_TEXT:
        raise ConfigurationError(
            f"{screener_id}: the sentence with the new words is over {MAX_TEXT} characters"
        )
    return PartRequest(screener_id, sentence, prior, chosen, chosen.words, new_words, merged, spans)


def _checked_document(screener_id: str, document: Any) -> Mapping[str, Any]:
    """The Builder's document has a criteria table of at most ``MAX_CRITERIA`` criteria, each a
    table with a ``field`` and an ``op`` (what the merge and the prompt read)."""
    held = document.get("criteria", {}) if isinstance(document, Mapping) else None
    if not isinstance(held, Mapping):
        raise ConfigurationError(f"{screener_id}: the document has no criteria table")
    if len(held) > MAX_CRITERIA:
        raise ConfigurationError(f"{screener_id}: the document has over {MAX_CRITERIA} criteria")
    for cid, criterion in held.items():
        if (
            not isinstance(criterion, Mapping)
            or not isinstance(criterion.get("field"), str)
            or not isinstance(criterion.get("op"), str)
        ):
            raise ConfigurationError(f"{screener_id}: criterion {cid!r} has no field and op")
    return cast(Mapping[str, Any], document)


def _part(raw: Mapping[str, Any]) -> Part:
    """A part as the browser sends it back; its ``kind`` is recomputed, never read."""
    refs = {
        key: tuple(str(i) for i in raw.get(key) or ())
        for key in ("criteria", "dropped", "formulas", "unresolved", "missing", "suggestions")
    }
    reading = raw.get("reading")
    text = " ".join(reading.split())[:MAX_READING].rstrip() if isinstance(reading, str) else ""
    source = "model" if text and raw.get("reading_source") == "model" else "server"
    rank = bool(raw.get("rank"))
    origin = str(raw.get("origin"))
    return Part(
        str(raw.get("id")), str(raw.get("words") or ""), int(raw.get("start") or 0),
        int(raw.get("end") or 0), text or None, source, kind_of(_groups(refs, rank)), origin,
        refs["criteria"], refs["dropped"], refs["formulas"], refs["unresolved"],
        refs["missing"], refs["suggestions"], rank,
    )  # fmt: skip


def _groups(refs: Mapping[str, Sequence[str]], rank: bool) -> dict[str, Sequence[str]]:
    """The refs of a part as ``kind_of`` reads them."""
    return {**{k: v for k, v in refs.items() if v}, **({"rank": ["rank"]} if rank else {})}


def _code_points(sentence: str, units: int, who: str) -> int:
    """``units`` UTF-16 code units into ``sentence`` as code points."""
    raw = sentence.encode("utf-16-le")
    if units < 0 or units * 2 > len(raw):
        raise ConfigurationError(f"{who}: an offset is outside the sentence")
    try:
        return len(raw[: units * 2].decode("utf-16-le"))
    except UnicodeDecodeError as exc:
        raise ConfigurationError(f"{who}: an offset falls inside a character") from exc


def _spans(screener_id: str, sentence: str, parts: Sequence[Part]) -> dict[str, tuple[int, int]]:
    """The code-point spans of the parts that carry words, checked: ids unique, at most
    ``MAX_PARTS`` with words, the catch-alls only ``kept`` / ``unplaced`` with no words, each
    part's words the sentence's own slice, in order and not overlapping."""
    if len({p.id for p in parts}) != len(parts):
        raise ConfigurationError(f"{screener_id}: two parts have the same id")
    spans: dict[str, tuple[int, int]] = {}
    cursor = 0
    for part in parts:
        who = f"{screener_id}: part {part.id!r}"
        if part.origin in ("kept", "unplaced"):
            if part.id not in CATCH_ALLS or part.words or part.start or part.end:
                raise ConfigurationError(f"{who} is a catch-all with words")
            continue
        if part.origin not in ("words", "gap") or part.id in CATCH_ALLS or not part.words:
            raise ConfigurationError(f"{who} has no words, or an origin it cannot have")
        start = _code_points(sentence, part.start, who)
        end = _code_points(sentence, part.end, who)
        if sentence[start:end] != part.words:
            raise ConfigurationError(
                f"{who}: its words are not the sentence's words at its offsets"
            )
        if start < cursor:
            raise ConfigurationError(f"{who} overlaps the part before it, or is out of order")
        spans[part.id] = (start, end)
        cursor = end
    if len(spans) > MAX_PARTS:
        raise ConfigurationError(f"{screener_id}: the draft has over {MAX_PARTS} parts with words")
    return spans


def _prior(
    screener_id: str,
    sentence: str,
    document: Mapping[str, Any],
    parts: Sequence[Part],
    body: Mapping[str, Any],
) -> ScreenDraft:
    """The draft the browser holds, rebuilt from what it sent."""
    return ScreenDraft(
        screener_id,
        dict(document),
        tuple(
            DroppedCriterion(str(d["id"]), str(d["field"]), str(d["reason"]))
            for d in body.get("dropped") or ()
        ),
        tuple(str(n) for n in body.get("notes") or ()),
        formulas=tuple(_formula(f) for f in body.get("formulas") or ()),
        formulas_dropped=tuple(
            DroppedFormula(str(d["name"]), str(d["reason"]), d.get("existing"))
            for d in body.get("formulas_dropped") or ()
        ),
        missing=tuple(_missing(m) for m in body.get("missing") or ()),
        unresolved=tuple(_unresolved(u) for u in body.get("unresolved") or ()),
        suggestions=tuple(
            Suggestion(dict(s["criterion"]), str(s["why"]), s.get("source"), str(s["id"]))
            for s in body.get("suggestions") or ()
        ),
        suggestions_dropped=tuple(
            DroppedSuggestion(str(d["field"]), str(d["reason"]))
            for d in body.get("suggestions_dropped") or ()
        ),
        sentence=sentence,
        parts=tuple(parts),
    )


def _formula(raw: Mapping[str, Any]) -> DraftFormula:
    run = raw.get("dry_run") or {}
    dry = DryRun(
        run.get("session"), [], int(run.get("rows") or 0), run.get("no_value_rate"),
        run.get("minimum"), run.get("maximum"), run.get("criterion_pass"),
        [SampleValue(str(s["instrument_id"]), s["value"]) for s in run.get("sample") or ()],
    )  # fmt: skip
    criterion = raw.get("criterion")
    return DraftFormula(
        str(raw["name"]), str(raw["expr"]), str(raw["dtype"]), str(raw["unit"]),
        str(raw["description"]), str(raw["null_meaning"]), tuple(raw.get("inputs") or ()),
        dict(criterion) if criterion else None, str(raw["fingerprint"]), dry,
        bool(raw.get("pending", True)),
    )  # fmt: skip


def _missing(raw: Mapping[str, Any]) -> MissingFeature:
    return MissingFeature(
        raw.get("key"), raw.get("new_key_slug"), str(raw["span"]), str(raw["description"]),
        str(raw["why_needed"]), tuple(raw.get("closest") or ()), str(raw["feasibility"]),
    )  # fmt: skip


def _unresolved(raw: Mapping[str, Any]) -> Unresolved:
    alternatives = tuple(
        Alternative(str(a["text"]), dict(a["criterion"])) for a in raw.get("alternatives") or ()
    )
    index = int(raw.get("default_index") or 0)
    if not 0 <= index < len(alternatives):
        raise ConfigurationError(f"unresolved {raw.get('term')!r}: default_index is not a reading")
    return Unresolved(str(raw["term"]), str(raw["span"]), index, alternatives)


def missing_ref(item: MissingFeature) -> str:
    """How a part names a missing request: its backlog key, else its new slug."""
    return item.key or str(item.new_key_slug)


def _refs(screener_id: str, prior: ScreenDraft) -> None:
    """Every id a part names is an item of ``prior`` and belongs to one part (a missing request
    may be named by two); a criterion the document no longer has is left to the merge, which
    drops it from the part."""
    held: dict[str, Iterable[str]] = {
        "dropped": [d.id for d in prior.dropped],
        "formulas": [f.name for f in prior.formulas],
        "unresolved": [u.term for u in prior.unresolved],
        "missing": [missing_ref(m) for m in prior.missing],
        "suggestions": [s.id for s in prior.suggestions],
    }
    for group in ("criteria", *held):
        seen: set[str] = set()
        for part in prior.parts or ():
            for ref in getattr(part, group):
                if group in held and ref not in set(held[group]):
                    raise ConfigurationError(
                        f"{screener_id}: part {part.id!r} names {group} {ref!r}, which the "
                        "draft does not have"
                    )
                if ref in seen and group not in SHARED:
                    raise ConfigurationError(f"{screener_id}: {group} {ref!r} belongs to two parts")
                seen.add(ref)
    if sum(p.rank for p in prior.parts or ()) > 1:
        raise ConfigurationError(f"{screener_id}: the tie-break belongs to two parts")
