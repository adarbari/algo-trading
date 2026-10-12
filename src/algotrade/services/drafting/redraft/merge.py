"""Merge the re-draft of one part into the draft the browser holds (ADR 0041, amended 2026-10-12).
``sub`` is the draft of the new words alone (every item in its one part); the result is the whole
draft again, the browser swaps it in whole:

- the part's own criteria (the ids it names) are replaced as a whole by the new ones, and so are
  its dropped criteria, formulas, readings to choose, missing requests, suggestions and tie-break;
- the other parts win: a new criterion on the same field and operator as a criterion of another
  part (or of the Builder's hand-added ones) is dropped with the reason ``OTHER_PART``; a
  suggestion that repeats or rewrites one of them is not offered; a formula or term another part
  already offers is not offered twice; the document's tie-break stays when another part owns it;
- what the Builder's document holds that no part names (the trader added it by hand) is the
  ``kept`` part, the other parts keep their ids, words and readings, and the offsets of the words
  after the replaced ones move with them (in UTF-16 units, as before);
- ids stay unique (a new criterion, dropped criterion or suggestion that takes an id another
  part holds is renamed) and the document is validated as finalise does; a new criterion the
  validator refuses is dropped with its message, but one of the trader's own that it refuses is
  an error (the merge never drops what the trader has).

The reading of the new part is the model's only while nothing it said was dropped by the merge.
Pure but for the validator and the dry run of formulas, which were done already."""

from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import replace
from typing import Any

from algotrade.core.model.errors import ConfigurationError
from algotrade.services.drafting.formulas import DroppedFormula
from algotrade.services.drafting.gaps import Unresolved
from algotrade.services.drafting.parts.build import kind_of
from algotrade.services.drafting.parts.model import KEPT_ID, UNPLACED_ID, Part
from algotrade.services.drafting.parts.spans import utf16
from algotrade.services.drafting.redraft.request import MAX_ITEMS, PartRequest, missing_ref
from algotrade.services.drafting.screens import (
    MAX_TEXT,
    DroppedCriterion,
    ScreenDraft,
    reading_of,
    validated,
)
from algotrade.services.drafting.suggestions import rewrites
from algotrade.services.read.context import ReadContext

OTHER_PART = "set by another part"
TAKEN_FORMULA = "already offered for another part"
OVER_CAP = "over the number a draft may carry"


def merge_part(ctx: ReadContext, req: PartRequest, sub: ScreenDraft) -> ScreenDraft:
    """``req.prior`` with ``req.part`` re-drafted as ``sub``, in ``req.merged``'s words."""
    old, prior = req.part, req.prior
    notes = list(prior.notes)
    others = _others(req)
    mine = _Mine()
    document = _document(ctx, req, sub, mine)
    criteria = document["criteria"]
    dropped = [d for d in prior.dropped if d.id not in old.dropped] + mine.dropped
    # formulas: one name, one part
    offered = {f.name for f in prior.formulas if f.name not in old.formulas}
    formulas = [f for f in prior.formulas if f.name not in old.formulas]
    formulas_dropped = [*prior.formulas_dropped, *sub.formulas_dropped]
    for formula in sub.formulas:
        if formula.name in offered or len(formulas) >= MAX_ITEMS:
            reason = TAKEN_FORMULA if formula.name in offered else OVER_CAP
            formulas_dropped.append(DroppedFormula(formula.name, reason))
            mine.lost = True  # its reading may have described it
            continue
        formulas.append(replace(formula, part=None))
        mine.formulas.append(formula.name)
    # readings to choose: one term, one part; the default must be one the document holds
    asked = {u.term for u in prior.unresolved if u.term not in old.unresolved}
    unresolved = [u for u in prior.unresolved if u.term not in old.unresolved]
    fresh: list[Unresolved] = []
    for term in sub.unresolved:
        if term.term in asked or len(unresolved) + len(fresh) >= MAX_ITEMS:
            notes.append(f"{term.term}: not offered again (another part has it, or too many)")
            mine.lost = True
            continue
        fresh.append(term)
    held_readings = {reading_of(c) for c in criteria.values()}
    for n, term in enumerate(fresh):
        if reading_of(_default(term)) in held_readings:
            continue
        index = next(
            (
                i
                for i, a in enumerate(term.alternatives)
                if reading_of(a.criterion) in held_readings
            ),
            term.default_index,
        )
        notes.append(f"{term.term}: its default reading was not applied (another part sets it)")
        fresh[n] = replace(term, default_index=index)
    unresolved += fresh
    mine.unresolved += [t.term for t in fresh]
    # missing requests: another part may name the same one
    elsewhere = {r for p in others for r in p.missing}
    missing = [
        m for m in prior.missing if missing_ref(m) not in old.missing or missing_ref(m) in elsewhere
    ]
    have = {missing_ref(m) for m in missing}
    missing += [m for m in sub.missing if missing_ref(m) not in have][: MAX_ITEMS - len(missing)]
    present = {missing_ref(m) for m in missing}
    mine.missing += [missing_ref(m) for m in sub.missing if missing_ref(m) in present]
    # suggestions: ids stay unique, the other parts' thresholds are never rewritten
    suggestions = [s for s in prior.suggestions if s.id not in old.suggestions]
    shown = [c for c in criteria.values() if isinstance(c, Mapping)]
    for suggestion in sub.suggestions:
        if rewrites(suggestion.criterion, shown) or len(suggestions) >= MAX_ITEMS:
            continue
        fresh_id = _unique("s", {s.id for s in suggestions}, numbered=True)
        suggestions.append(replace(suggestion, id=fresh_id, part=None))
        mine.suggestions.append(fresh_id)
    suggestions_dropped = [*prior.suggestions_dropped, *sub.suggestions_dropped]
    notes += [*mine.notes, *(n for n in sub.notes if n not in notes)]
    parts = _parts(req, sub, document, mine, others)
    return ScreenDraft(
        req.screener_id, document, tuple(dropped), _newest(dict.fromkeys(_clip(n) for n in notes)),
        call_id=sub.call_id, formulas=tuple(formulas), formulas_dropped=_newest(formulas_dropped),
        missing=tuple(missing), unresolved=tuple(unresolved), suggestions=tuple(suggestions),
        suggestions_dropped=_newest(suggestions_dropped), sentence=req.merged, parts=parts,
    )  # fmt: skip


def _newest[T](items: Iterable[T]) -> tuple[T, ...]:
    """The last ``MAX_ITEMS`` of ``items``: what only grows (notes, what was dropped) is kept to
    the bound the next request's body may carry, the oldest going first."""
    return tuple(items)[-MAX_ITEMS:]


def _clip(note: str) -> str:
    return note if len(note) <= MAX_TEXT else note[: MAX_TEXT - 1] + "…"


class _Mine:
    """What the new part holds once merged: the ids of its items in the merged draft."""

    def __init__(self) -> None:
        self.criteria: list[str] = []
        self.dropped: list[DroppedCriterion] = []
        self.formulas: list[str] = []
        self.unresolved: list[str] = []
        self.missing: list[str] = []
        self.suggestions: list[str] = []
        self.rank = False
        self.notes: list[str] = []
        self.lost = False  # the merge dropped something the model said (its reading may lie)


def _others(req: PartRequest) -> list[Part]:
    return [p for p in req.prior.parts or () if p.id != req.part.id]


def _default(term: Unresolved) -> Mapping[str, Any]:
    return term.alternatives[term.default_index].criterion


def _unique(base: str, taken: Collection[str], numbered: bool = False) -> str:
    """``base`` if free, else ``base_2``, ``base_3``...; ``numbered``: ``base1``, ``base2``..."""
    if numbered:
        n = 1
        while f"{base}{n}" in taken:
            n += 1
        return f"{base}{n}"
    name, k = base, 2
    while name in taken:
        name, k = f"{base}_{k}", k + 1
    return name


def _document(ctx: ReadContext, req: PartRequest, sub: ScreenDraft, mine: _Mine) -> dict[str, Any]:
    """The Builder's document without the part's criteria, with the new ones that no other part
    sets and the validator accepts (what it refuses is dropped, noted in ``mine``)."""
    old = req.part
    criteria = {cid: c for cid, c in req.criteria.items() if cid not in old.criteria}
    held = {(c.get("field"), c.get("op")) for c in criteria.values() if isinstance(c, Mapping)}
    taken_dropped = {d.id for d in req.prior.dropped if d.id not in old.dropped}
    added: dict[str, str] = {}  # the id in ``sub`` -> the id in the merged document
    for sid, criterion in sub.document["criteria"].items():
        if (criterion["field"], criterion["op"]) in held:
            did = _unique(sid, taken_dropped)
            taken_dropped.add(did)
            mine.dropped.append(
                DroppedCriterion(did, criterion["field"], OTHER_PART, "other_part",
                                 "merge: another part sets this field and operator")
            )  # fmt: skip
            mine.lost = True
            continue
        cid = _unique(sid, criteria)
        criteria[cid] = criterion
        added[sid] = cid
    for dropped in sub.dropped:  # what the model's own draft dropped, ids kept unique
        did = _unique(dropped.id, taken_dropped)
        taken_dropped.add(did)
        mine.dropped.append(replace(dropped, id=did))
    document = {k: v for k, v in req.prior.document.items() if k not in ("criteria", "rank")}
    document["criteria"] = criteria
    own = req.prior.document.get("rank")  # the document's tie-break: the part's, or another's
    new = sub.document.get("rank")
    if own is not None and not old.rank:
        document["rank"] = own
        if new is not None:  # the other part wins; the reading may have described this one
            mine.notes.append("rank: the tie-break another part sets stays")
            mine.lost = True
    elif new is not None:
        document["rank"] = new
        mine.rank = True
    document, refused = validated(ctx, req.screener_id, document, ())
    for gone in refused:
        if gone.id not in added.values():
            raise ConfigurationError(
                f"{req.screener_id}: the criterion {gone.id!r} of your screen is not valid: "
                f"{gone.reason}; fix it before retyping a part"
            )
        mine.dropped.append(replace(gone, id=_unique(gone.id, taken_dropped)))
        taken_dropped.add(mine.dropped[-1].id)
        mine.lost = True
    if "rank" not in document:
        if mine.rank:
            mine.notes.append("rank: the validator refused the tie-break of the new words")
            mine.lost = True
        mine.rank = False
    mine.criteria = [cid for cid in added.values() if cid in document["criteria"]]
    return document


def _parts(
    req: PartRequest,
    sub: ScreenDraft,
    document: Mapping[str, Any],
    mine: _Mine,
    others: Sequence[Part],
) -> tuple[Part, ...]:
    """The parts of the merged draft: words parts in sentence order (the retyped one rebuilt
    from what it now holds), then ``kept`` (every criterion no part names), then ``unplaced``."""
    old = req.part
    start, end = req.spans[old.id]
    shift = len(req.new_words) - (end - start)
    criteria = document["criteria"]
    ranked = "rank" in document
    out: list[Part] = []
    claimed: set[str] = set()
    for part in req.prior.parts or ():
        if part.origin in ("kept", "unplaced"):
            continue
        if part.id == old.id:
            built = _retyped(req, sub, mine, start)
        else:
            s, e = req.spans[part.id]
            moved = shift if s >= end else 0
            built = _pruned(
                part, criteria, ranked, utf16(req.merged, s + moved), utf16(req.merged, e + moved)
            )
        claimed.update(built.criteria)
        out.append(built)
    catch_alls = {p.id: p for p in req.prior.parts or () if p.origin in ("kept", "unplaced")}
    unplaced = catch_alls.get(UNPLACED_ID)
    unplaced = None if unplaced is None else _pruned(unplaced, criteria, ranked, 0, 0)
    claimed.update(unplaced.criteria if unplaced is not None else ())
    base = catch_alls.get(KEPT_ID) or Part(KEPT_ID, "", 0, 0, None, "server", "applied", "kept")
    kept = _pruned(base, criteria, ranked, 0, 0)
    kept = replace(kept, criteria=tuple(cid for cid in criteria if cid not in claimed))
    kept = replace(kept, kind=kind_of(_groups(kept)))
    out += [p for p in (kept, unplaced) if p is not None and _has_refs(p)]
    return tuple(out)


def _groups(part: Part) -> dict[str, Sequence[str]]:
    refs: dict[str, Sequence[str]] = {
        "criteria": part.criteria, "dropped": part.dropped, "formulas": part.formulas,
        "unresolved": part.unresolved, "missing": part.missing, "suggestions": part.suggestions,
    }  # fmt: skip
    return {k: v for k, v in refs.items() if v} | ({"rank": ["rank"]} if part.rank else {})


def _has_refs(part: Part) -> bool:
    return bool(_groups(part))


def _pruned(part: Part, criteria: Mapping[str, Any], ranked: bool, start: int, end: int) -> Part:
    """``part`` without the criteria the document no longer has (the trader deleted them) and
    without the tie-break when the document has none, at its new offsets, its kind decided
    again from what it holds."""
    held = replace(
        part,
        start=start,
        end=end,
        rank=part.rank and ranked,
        criteria=tuple(c for c in part.criteria if c in criteria),
    )
    return replace(held, kind=kind_of(_groups(held)))


def _retyped(req: PartRequest, sub: ScreenDraft, mine: _Mine, start: int) -> Part:
    """The part whose words were retyped: the new words at their place, what it now holds, the
    model's reading when nothing it described was dropped by the merge."""
    old = req.part
    refs = Part(
        old.id, req.new_words, 0, 0, None, "server", "", old.origin,
        tuple(mine.criteria), tuple(d.id for d in mine.dropped), tuple(mine.formulas),
        tuple(mine.unresolved), tuple(mine.missing), tuple(mine.suggestions), mine.rank,
    )  # fmt: skip
    kind = kind_of(_groups(refs))
    model = sub.parts[0] if sub.parts else None
    reading, source = (None, "server")
    if model is not None and model.reading and not mine.lost and kind != "not_understood":
        reading, source = model.reading, model.reading_source
    origin = "gap" if old.origin == "gap" and kind == "not_understood" else "words"
    return replace(
        refs, start=utf16(req.merged, start), end=utf16(req.merged, start + len(req.new_words)),
        reading=reading, reading_source=source, kind=kind, origin=origin,
    )  # fmt: skip
