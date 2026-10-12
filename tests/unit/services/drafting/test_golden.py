"""The golden scorer: a part with its criterion passes within tolerance; a missing, wrong or
extra criterion, or a field invented for a part that must stay empty, fails."""

import json
from pathlib import Path

from algotrade.services.drafting.golden import GoldenCase, load_cases, mark_recorded, score

A = {
    "span": "p",
    "bucket": "A",
    "fields": ["f.x", "f.y"],
    "op": ["gt", "gte"],
    "value": 100,
    "tolerance": 0.1,
}
C = {"span": "q", "bucket": "C", "fields": []}


def case(*parts: dict) -> GoldenCase:
    return GoldenCase("c", "s", "train", parts, frozenset({"scope"}))


def crit(field: str, op: str = "gt", value: object = 100) -> dict:
    return {"field": field, "op": op, "value": value}


def test_a_matching_criterion_within_tolerance_passes_with_scope_tolerated() -> None:
    kept = {"a": crit("f.y", "gte", 95), "s": crit("scope", "eq", "ACTIVE")}
    assert score(case(A), kept).passed


def test_missing_wrong_and_extra_are_named() -> None:
    assert score(case(A), {}).missing == ("p",)
    assert score(case(A), {"a": crit("f.x", "lt")}).wrong == ("p",)
    assert score(case(A), {"a": crit("f.x", value=150)}).wrong == ("p",)
    assert score(case(A), {"a": crit("f.x"), "b": crit("f.z")}).extra == ("f.z",)


def test_a_c_part_wants_nothing_and_invented_fields_count_as_extra() -> None:
    assert score(case(C), {}).passed
    assert score(case(C), {"a": crit("f.x")}).extra == ("f.x",)
    assert score(case(C), {}, ("made.up",)).extra == ("made.up",)


def test_a_curated_case_loads_the_criteria_in_force_and_its_recording_state(
    tmp_path: Path,
) -> None:
    force = {"criteria": {"c1": {"field": "f.a", "op": "gt", "value": 1}}, "rank": None}
    raw = {"id": "c", "sentence": "two", "sentences": ["one", "two"], "split": "train",
           "criteria_in_force": [{"criteria": {}}, force], "recorded": False,
           "curated": "2026-10-11", "expect": {"parts": []}}  # fmt: skip
    (tmp_path / "cases").mkdir()
    (tmp_path / "cases" / "c.json").write_text(json.dumps(raw))
    (loaded,) = load_cases(tmp_path)
    assert loaded.sentences == ("one", "two") and loaded.current == force
    assert (loaded.recorded, loaded.curated) == (False, "2026-10-11")
    mark_recorded(tmp_path, "c")
    assert "recorded" not in json.loads((tmp_path / "cases" / "c.json").read_text())
    assert load_cases(tmp_path)[0].recorded is True
    mark_recorded(tmp_path, "missing")  # no case file: nothing to do


def test_an_old_case_has_one_sentence_and_nothing_in_force() -> None:
    old = case(A)
    assert old.sentences == () and old.current is None and old.recorded
