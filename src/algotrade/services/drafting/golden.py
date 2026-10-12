"""The golden set of the drafting prompt (docs/drafting/describe-it-plan.md, "Learning from
iteration"): read the cases under ``tests/fixtures/drafting/golden/`` and score a parsed draft
against a case's expectation, structurally (fields, operators, values within a tolerance, nothing
extra). Pure: reads files it is given a root for, calls no model, writes nothing.

Layout (``root`` = ``tests/fixtures/drafting/golden``):

- ``cases/<id>.json``: ``{id, sentence, split: "train" | "held_out", expect: {parts: [...],
  scope_fields: [...]}}``. A part is ``{span, bucket: "A" | "B" | "C" | "ask", fields, op, value,
  tolerance}``: an ``A`` part wants one criterion on one of ``fields`` (alternatives) with an
  ``op`` (one, or a list of acceptable ones) and a ``value`` within ``tolerance`` (a fraction of
  the expected value; absolute when that is 0); a ``B`` / ``C`` / ``ask`` part wants no criterion
  of its own, so any criterion that matches no ``A`` part is extra. The A / B / C contract
  (ADR 0041, amended 2026-10-11) adds expectations a part may carry: a ``B`` part with ``expr``
  wants a kept formula with that fingerprint (``features.expressions.fingerprint``, so a
  rewriting of it passes; any other kept formula is extra), a ``C`` part with ``key`` wants a
  missing item of that backlog key or slug, an ``ask`` part with ``term`` wants that term
  unresolved. A part without these keys expects nothing of the new buckets, and a score given no
  ``formulas`` / ``missing`` / ``unresolved`` leaves them unchecked (an answer of the old shape).
  ``scope_fields`` are tolerated scaffolding (status, security type). ``"contract": true`` in
  ``expect`` marks a case written for the contract: CI replays its answer through the whole
  ``draft_screen``.
- ``answers/<model-slug>/<id>.json``: the model's raw answer text for that case, replayed in CI.

To add a case: write ``cases/<id>.json``, record the model's raw answer into
``answers/<slug>/<id>.json`` (the owner CLI will do both later), run the replay test; a
``held_out`` sentence must appear in neither the prompt examples nor the phrasebook (fitness test
``tests/architecture/drafting``)."""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from algotrade.config.site.features.definitions import FeatureDefinition
from algotrade.core.model.errors import ConfigurationError
from algotrade.features.expressions.fingerprint import fingerprint

SPLITS = ("train", "held_out")


@dataclass(frozen=True)
class GoldenCase:
    """One golden case: a sentence and what a correct draft of it contains."""

    id: str
    sentence: str
    split: str
    parts: tuple[Mapping[str, Any], ...]
    scope_fields: frozenset[str]
    contract: bool = False  # the whole draft is replayed (formulas checked, gaps resolved)


@dataclass(frozen=True)
class GoldenScore:
    """How a draft measures against a case: spans of parts with no matching criterion
    (``missing``), parts whose criterion has the wrong op or value (``wrong``), and fields (and
    formulas) kept or dropped that no part asked for (``extra``)."""

    missing: tuple[str, ...]
    wrong: tuple[str, ...]
    extra: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not (self.missing or self.wrong or self.extra)


def load_cases(root: Path) -> tuple[GoldenCase, ...]:
    """Every case under ``root/cases``, by id."""
    cases = []
    for path in sorted((root / "cases").glob("*.json")):
        raw = json.loads(path.read_text())
        if raw["split"] not in SPLITS:
            raise ValueError(f"{path.name}: split must be one of {SPLITS}")
        expect = raw["expect"]
        cases.append(
            GoldenCase(
                raw["id"],
                raw["sentence"],
                raw["split"],
                tuple(expect["parts"]),
                frozenset(expect.get("scope_fields", ())),
                bool(expect.get("contract", False)),
            )
        )
    return tuple(cases)


def recorded_answers(root: Path, case_id: str) -> dict[str, str]:
    """The recorded raw answers for a case, by model slug."""
    return {
        path.parent.name: path.read_text()
        for path in sorted((root / "answers").glob(f"*/{case_id}.json"))
    }


def score(
    case: GoldenCase,
    kept: Mapping[str, Mapping[str, Any]],
    dropped_fields: Sequence[str] = (),
    formulas: Sequence[str] | None = None,
    missing_keys: Sequence[str] | None = None,
    terms: Sequence[str] | None = None,
) -> GoldenScore:
    """Score the kept criteria (``criteria_of``'s table) and the fields it dropped as invented.
    ``formulas``: the kept formulas' ``expr``; ``missing_keys``: each missing item's key or new
    slug; ``terms``: the unresolved terms (``None``: that bucket is not scored)."""
    missing: list[str] = []
    wrong: list[str] = []
    used: set[str] = set()
    for part in case.parts:
        if part["bucket"] != "A":
            continue
        found = [
            cid for cid, crit in kept.items() if cid not in used and crit["field"] in part["fields"]
        ]
        if not found:
            missing.append(part["span"])
            continue
        hit = next((cid for cid in found if _fits(part, kept[cid])), None)
        if hit is None:
            wrong.append(part["span"])
            used.add(found[0])
        else:
            used.add(hit)
    extra = [
        crit["field"]
        for cid, crit in kept.items()
        if cid not in used and crit["field"] not in case.scope_fields
    ]
    extra += _bucket_scores(case, formulas, missing_keys, terms, missing)
    return GoldenScore(tuple(missing), tuple(wrong), tuple(extra) + tuple(dropped_fields))


def _bucket_scores(
    case: GoldenCase,
    formulas: Sequence[str] | None,
    missing_keys: Sequence[str] | None,
    terms: Sequence[str] | None,
    missing: list[str],
) -> list[str]:
    """Score the B, C and unresolved buckets; spans not found are added to ``missing``, the
    kept formulas nothing asked for returned."""
    extra: list[str] = []
    if formulas is not None:
        wanted = {_print(p["expr"]): p for p in case.parts if p["bucket"] == "B" and "expr" in p}
        got = {_print(e): e for e in formulas}
        missing += [str(p["span"]) for h, p in wanted.items() if h not in got]
        extra += [f"formula {e}" for h, e in got.items() if h not in wanted]
    if missing_keys is not None:
        missing += [
            str(p["span"]) for p in case.parts if "key" in p and p["key"] not in missing_keys
        ]
    if terms is not None:
        said = {t.lower() for t in terms}
        missing += [
            str(p["span"]) for p in case.parts if "term" in p and p["term"].lower() not in said
        ]
    return extra


def _print(expr: str) -> str:
    """The fingerprint of ``expr`` (a formula that does not parse is its own text)."""
    try:
        definition = FeatureDefinition("golden", "golden", expr, "float", "ratio", "x", "x")
        return fingerprint(definition).hash
    except ConfigurationError:  # an invalid formula never matches an expected one
        return f"invalid:{expr}"


def _fits(part: Mapping[str, Any], crit: Mapping[str, Any]) -> bool:
    ops = part["op"] if isinstance(part["op"], list) else [part["op"]]
    if crit["op"] not in ops:
        return False
    return _close(crit.get("value"), part["value"], float(part.get("tolerance", 0)))


def _close(got: Any, want: Any, tolerance: float) -> bool:
    if isinstance(want, list) or isinstance(got, list):
        return isinstance(got, list) and isinstance(want, list) and set(got) == set(want)
    if isinstance(want, bool) or isinstance(got, bool) or isinstance(want, str):
        return bool(got == want)
    if not isinstance(got, (int, float)):
        return False
    return bool(abs(got - want) <= (tolerance * abs(want) if want else tolerance))
