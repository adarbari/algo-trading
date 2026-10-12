"""``draft_screen``: a sentence to a draft rule screen (ADR 0041). The prompt is the task, an
index of the caller's catalogue and, for the sentence's slice of it (``retrieval``), the
fields in detail, the site phrasebook (``config/site/phrasebook.toml``) entries and the site
field guide (``config/site/field_guide/*.toml``: thresholds and caveats per field). The
model's JSON is parsed strictly (ids, fields, ops, modes, values, tolerances); a criterion on
a field outside the caller's catalogue, or one the validator rejects, is dropped with the
reason (never saved, never silently kept); the rest is validated with ``resolve_rule_draft``
as finalise does. The model is asked with the answer schema (``answer_schema.py``) and the
draft's own check as ``accept``: an answer that is not JSON, has no criteria list or is a draft
the validator refuses is repaired once and then handed to the next provider by the chain
(ADR 0041, amended 2026-10-11). The answer also carries the A / B / C contract (same
amendment): ``formulas`` (B1,
``formulas.py``: checked, deduplicated by fingerprint and dry-run, pending until the trader
accepts), ``missing`` and ``unresolved`` (``gaps.py``). The document holds only A criteria (the
existing-field rewrite of a duplicate formula and the default reading of each unresolved term
among them); a pending formula and its criterion travel beside it and are never auto-applied.
Reads the catalogue, the configs and, for the dry run of a formula, the request's session;
writes nothing."""

import json
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from algotrade.config.site.drafting.backlog import open_keys
from algotrade.config.site.settings import (
    load_feature_backlog,
    load_field_guide,
    load_phrasebook,
)
from algotrade.core.model.completion import CallTag
from algotrade.core.model.errors import (
    ConfigurationError,
    InvalidAnswerError,
    ModelUnavailableError,
)
from algotrade.core.model.predicates import NO_VALUE_OPS, OPS
from algotrade.services.configs import resolve_rule_draft
from algotrade.services.drafting.answer_schema import ANSWER_SCHEMA, check_answer, check_criterion
from algotrade.services.drafting.formulas import (
    DraftFormula,
    DroppedFormula,
    check_formulas,
    dry_run_all,
)
from algotrade.services.drafting.gaps import MissingFeature, Unresolved, missing_of, unresolved_of
from algotrade.services.drafting.prompt import PROMPT_VERSION, sliced_system_prompt, user_prompt
from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments.catalogue import feature_infos
from algotrade.services.text_model.model import TextModel, reject_answer

MODES = ("hard", "soft", "score")
MISSES = ("WATCH", "LIQUIDITY_RISK", "EVENT_RISK")
MAX_TEXT = 1000  # characters of sentence (one request, synchronous: never a job)
_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_NAMED_CRITERION = re.compile(r"\.criteria\.([A-Za-z0-9_-]+)")
_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")
type Scalar = str | int | float | bool

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DroppedCriterion:
    """A criterion the model proposed that the draft does not keep, and why."""

    id: str
    field: str
    reason: str


@dataclass(frozen=True)
class ScreenDraft:
    """What the Builder loads: the document (``id``, ``kind``, ``impl``, ``criteria``, maybe
    ``rank``), the criteria dropped with their reasons, and the model's notes (what it could
    not map or assumed)."""

    screener_id: str
    document: dict[str, Any]
    dropped: tuple[DroppedCriterion, ...]
    notes: tuple[str, ...]
    call_id: str | None = None  # the text-model call that made it (usage/llm_calls, ADR 0066)
    formulas: tuple[DraftFormula, ...] = ()  # B1: pending, not in the document
    formulas_dropped: tuple[DroppedFormula, ...] = ()
    missing: tuple[MissingFeature, ...] = ()  # B2 / C: asked for, not buildable here
    unresolved: tuple[Unresolved, ...] = ()  # ambiguous terms; the document has the default


def draft_screen(
    ctx: ReadContext,
    model: TextModel,
    screener_id: str,
    text: str,
    current: Mapping[str, Any] | None = None,
) -> ScreenDraft:
    """``text`` as ``screener_id``'s draft for ``ctx``'s user, over that user's catalogue;
    ``current``: the Builder's document, whose criteria the model keeps unless the sentence
    changes them. ``ConfigurationError`` for an empty or over-long sentence;
    ``ModelUnavailableError`` when the model cannot answer or answers with no draft."""
    sentence = " ".join(text.split())
    if not sentence:
        raise ConfigurationError(f"{screener_id}: the sentence is empty")
    if len(sentence) > MAX_TEXT:
        raise ConfigurationError(f"{screener_id}: the sentence is over {MAX_TEXT} characters")
    infos = feature_infos(ctx.features)
    phrasebook = load_phrasebook(ctx.configs).phrases
    guide = load_field_guide(ctx.configs)
    backlog = load_feature_backlog(ctx.configs)
    system = sliced_system_prompt(
        infos.values(), sentence, phrasebook, guide, open_keys(backlog, limit=len(backlog.items))
    )
    user = user_prompt(screener_id, sentence, current)
    tag = CallTag("screener-draft", ctx.user.user_id, PROMPT_VERSION)
    drafted: list[tuple[str, ScreenDraft]] = []  # the answers accepted: text and its draft

    def check(text: str) -> None:
        drafted.append((text, _draft(ctx, screener_id, text, infos)))

    def accept(text: str) -> None:
        """The chain's check of an answer: a draft we can use, else ``InvalidAnswerError``."""
        try:
            check(text)
        except ConfigurationError as exc:  # a draft the validator refuses
            raise InvalidAnswerError(str(exc)) from exc

    completion = model.complete(system, user, tag=tag, schema=ANSWER_SCHEMA, accept=accept)
    try:
        if not drafted or drafted[-1][0] != completion.text:  # a model that did not check
            check(completion.text)
    except (ModelUnavailableError, ConfigurationError) as exc:  # an answer we cannot use
        reject_answer(model, tag, completion, str(exc), user, len(system) + len(user))
        raise
    final = drafted[-1][1]
    formulas, dry_notes = dry_run_all(ctx, final.formulas)  # once, on the draft we keep
    return replace(
        final, formulas=formulas, notes=(*final.notes, *dry_notes), call_id=completion.call_id
    )  # one id: every attempt of the call


def _draft(ctx: ReadContext, screener_id: str, text: str, infos: Mapping[str, Any]) -> ScreenDraft:
    proposal = parse_answer(text)
    catalogue = set(infos)
    criteria, dropped = criteria_of(proposal, catalogue)
    formulas = check_formulas(
        ctx, proposal, lambda raw, name: _criterion(raw, name, catalogue | {name})
    )
    unresolved, unresolved_notes = unresolved_of(
        proposal, catalogue, lambda raw, name: _alternative(ctx, screener_id, raw, name, catalogue)
    )
    missing, missing_notes = missing_of(proposal, load_feature_backlog(ctx.configs), catalogue)
    for criterion in formulas.rewritten.values():  # a duplicate formula: the existing field
        criteria[_criterion_id(None, criterion["field"], len(criteria) + 1, criteria)] = criterion
    placed: dict[str, str] = {}  # unresolved term -> the id of its default in the criteria
    for term in unresolved:  # the reading the draft starts with
        default = term.alternatives[term.default_index].criterion
        same = [k for k, c in criteria.items() if _reading(c) == _reading(default)]
        if same:  # the model also listed it in criteria: not twice
            placed[term.term] = same[0]
            continue
        key = _criterion_id(term.term.lower().replace(" ", "_"), default["field"], 0, criteria)
        criteria[key] = default
        placed[term.term] = key
    document: dict[str, Any] = {
        "id": screener_id,
        "kind": "screener",
        "impl": "rules",
        "criteria": criteria,
    }
    rank = rank_of(proposal, set(infos))
    if rank:
        document["rank"] = rank
    document, dropped = validated(ctx, screener_id, document, dropped)
    unresolved, reset_notes = _defaults_kept(unresolved, placed, document["criteria"])
    notes = (
        *notes_of(proposal), *formulas.notes, *unresolved_notes, *missing_notes, *reset_notes
    )  # fmt: skip
    return ScreenDraft(
        screener_id, document, dropped, notes,
        formulas=formulas.formulas, formulas_dropped=formulas.dropped,
        missing=missing, unresolved=unresolved,
    )  # fmt: skip


def _reading(criterion: Mapping[str, Any]) -> tuple[Any, Any, Any]:
    value = criterion.get("value")
    return criterion["field"], criterion["op"], tuple(value) if isinstance(value, list) else value


def _defaults_kept(
    unresolved: tuple[Unresolved, ...], placed: Mapping[str, str], criteria: Mapping[str, Any]
) -> tuple[tuple[Unresolved, ...], tuple[str, ...]]:
    """``unresolved`` with ``default_index`` pointing at a reading the document still has: when
    the validator dropped the default, the first alternative the document holds, else the first
    (and a note)."""
    out: list[Unresolved] = []
    notes: list[str] = []
    for term in unresolved:
        if placed.get(term.term) in criteria:
            out.append(term)
            continue
        held = {_reading(c) for c in criteria.values()}
        index = next(
            (n for n, a in enumerate(term.alternatives) if _reading(a.criterion) in held), 0
        )
        notes.append(f"{term.term}: the validator dropped its default reading")
        out.append(replace(term, default_index=index))
    return tuple(out), tuple(notes)


def _alternative(
    ctx: ReadContext, screener_id: str, raw: Mapping[str, Any], name: str, catalogue: set[str]
) -> dict[str, Any]:
    """An unresolved term's alternative as a criterion the validator accepts (``ConfigurationError``
    otherwise), so the trader's pick never fails to save."""
    criterion = _criterion(raw, name, catalogue)
    document = {
        "id": screener_id,
        "kind": "screener",
        "impl": "rules",
        "criteria": {"alt": criterion},
    }
    resolve_rule_draft(ctx.configs, screener_id, ctx.user, document)
    return criterion


def parse_answer(answer: str) -> Mapping[str, Any]:
    """The model's JSON object (a code fence around it is tolerated)."""
    text = _FENCE.sub("", answer.strip())
    try:
        parsed = json.loads(text)
    except ValueError as exc:
        raise InvalidAnswerError("the model's answer is not JSON") from exc
    if not isinstance(parsed, Mapping) or not isinstance(parsed.get("criteria"), list):
        raise InvalidAnswerError("the model's answer has no criteria list")
    if (why := check_answer(parsed)) is not None:
        raise InvalidAnswerError(f"the model's answer does not fit the schema ({why})")
    return parsed


def criteria_of(
    proposal: Mapping[str, Any], catalogue: set[str]
) -> tuple[dict[str, dict[str, Any]], tuple[DroppedCriterion, ...]]:
    """The proposed criteria as the draft's ``criteria`` table, and the ones dropped (a field
    outside the catalogue, an unknown op or mode, a value of the wrong shape)."""
    kept: dict[str, dict[str, Any]] = {}
    dropped: list[DroppedCriterion] = []
    for n, raw in enumerate(proposal["criteria"], 1):
        item = raw if isinstance(raw, Mapping) else {}
        raw_field = item.get("field")
        field_name: str = raw_field if isinstance(raw_field, str) else ""
        cid = _criterion_id(item.get("id"), field_name, n, kept)
        why = f" ({item['why']})" if isinstance(item.get("why"), str) and item["why"] else ""
        try:
            if (shape := check_criterion(item)) is not None:
                raise ConfigurationError(f"not the criterion shape ({shape})")
            kept[cid] = _criterion(item, field_name, catalogue)
        except ConfigurationError as exc:
            dropped.append(DroppedCriterion(cid, field_name, f"{exc}{why}"))
    return kept, tuple(dropped)


def _criterion_id(given: Any, field_name: str, n: int, taken: Mapping[str, Any]) -> str:
    base = given if isinstance(given, str) and _ID.match(given) else ""
    if not base:
        column = field_name.rsplit(".", 1)[-1] if field_name else f"criterion_{n}"
        base = re.sub(r"[^A-Za-z0-9_-]", "_", column)[:64] or f"criterion_{n}"
    cid, k = base, 2
    while cid in taken:
        cid, k = f"{base}_{k}", k + 1
    return cid


def _criterion(item: Mapping[str, Any], field_name: str, catalogue: set[str]) -> dict[str, Any]:
    if field_name not in catalogue:
        raise ConfigurationError(f"field {field_name!r} is not in the catalogue")
    op = item.get("op")
    if op not in OPS:
        raise ConfigurationError(f"unknown op {op!r}")
    mode = item.get("mode", "hard") or "hard"
    if mode not in MODES:
        raise ConfigurationError(f"unknown mode {mode!r}")
    out: dict[str, Any] = {"field": field_name, "op": op}
    if op not in NO_VALUE_OPS:
        out["value"] = _value(item.get("value"), op)
    if mode != "hard":
        out["mode"] = mode
        tolerance = item.get("tolerance")
        if tolerance is not None:
            out["tolerance"] = _tolerance(tolerance)
        if mode == "soft" and item.get("on_miss") in MISSES:
            out["on_miss"] = item["on_miss"]
    return out


def _scalar(value: Any) -> Scalar:
    if isinstance(value, (str, int, float, bool)):
        return value
    raise ConfigurationError(f"value {value!r} is not a number, text or boolean")


def _value(value: Any, op: str) -> Scalar | list[Scalar]:
    if op in ("in", "not_in"):
        values = value if isinstance(value, list) else [value]
        return [_scalar(v) for v in values]
    if op == "between":
        if not isinstance(value, list) or len(value) != 2:
            raise ConfigurationError("between needs a list of two numbers")
        return [_scalar(v) for v in value]
    if isinstance(value, list):
        raise ConfigurationError(f"{op} takes one value, not a list")
    return _scalar(value)


def _tolerance(raw: Any) -> float | dict[str, float]:
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    if isinstance(raw, Mapping) and isinstance(raw.get("relative"), (int, float)):
        return {"relative": float(raw["relative"])}
    raise ConfigurationError(f"tolerance {raw!r} is not a number or {{relative = ...}}")


def rank_of(proposal: Mapping[str, Any], catalogue: set[str]) -> dict[str, Any]:
    """``rank`` for the proposed tie-break (dropped silently when not a catalogue field)."""
    tie = proposal.get("tie_break")
    if not isinstance(tie, Mapping) or tie.get("field") not in catalogue:
        return {}
    rank: dict[str, Any] = {"tie_break": tie["field"]}
    if tie.get("descending") is False:
        rank["tie_break_order"] = "asc"
    return rank


def notes_of(proposal: Mapping[str, Any]) -> tuple[str, ...]:
    notes = proposal.get("notes")
    if not isinstance(notes, list):
        return ()
    return tuple(" ".join(n.split()) for n in notes if isinstance(n, str) and n.strip())


def validated(
    ctx: ReadContext,
    screener_id: str,
    document: dict[str, Any],
    dropped: tuple[DroppedCriterion, ...],
) -> tuple[dict[str, Any], tuple[DroppedCriterion, ...]]:
    """``document`` validated as finalise would; a criterion the validator names is dropped
    with its message and the rest re-validated, a bad ``rank`` is removed, until the document
    is valid or has no criteria left (an empty draft: the Builder shows it as such)."""
    out = dict(document)
    gone = list(dropped)
    for _ in range(len(out["criteria"]) + 2):
        if not out["criteria"]:
            return out, tuple(gone)
        try:
            resolve_rule_draft(ctx.configs, screener_id, ctx.user, out)
            return out, tuple(gone)
        except ConfigurationError as exc:
            named = _NAMED_CRITERION.search(str(exc))
            if named and named.group(1) in out["criteria"]:
                cid = named.group(1)
                criterion = out["criteria"].pop(cid)
                gone.append(DroppedCriterion(cid, criterion["field"], _reason(str(exc))))
            elif ".rank" in str(exc) and "rank" in out:
                del out["rank"]
            else:
                raise
    return out, tuple(gone)  # pragma: no cover - every round removes something


def _reason(message: str) -> str:
    """The validator's message after its path (``<user>/<id>.criteria.<cid>.value: ...``)."""
    return message.split(": ", 1)[1] if ": " in message else message
