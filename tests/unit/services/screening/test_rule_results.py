"""Rule-screen result frames: with boolean groups (ADR 0071) a group is a ``mode = "group"``
row, a member row names its parent in ``group_id``, and ``failed`` / ``near_missed`` /
``missing`` list gate ids, never a member's."""

from datetime import UTC, date, datetime
from typing import Any

import pandas as pd

from algotrade.config.strategy.screen_spec import parse_screen_spec
from algotrade.core.views.feature_view import FeatureView
from algotrade.services.screening.rule_results import Stamp, rule_frames
from algotrade.strategies.screeners.rules import evaluate_screen

DAY = date(2026, 10, 2)
STAMP = Stamp(DAY, "run1", datetime(2026, 10, 2, tzinfo=UTC), "site", "s", "h", None)


def frames(groups: dict[str, object], values: dict[str, float]) -> dict[str, pd.DataFrame]:
    criteria = {n: {"field": n, "op": "gt", "value": 1} for n in ("a", "b", "c")}
    spec = parse_screen_spec("s", {"criteria": criteria, "groups": groups}, "s")
    result = evaluate_screen(spec, FeatureView(DAY, {"EQ:X": values}))
    return rule_frames(result, STAMP)


def rows(frame: pd.DataFrame, mode: str) -> dict[str, Any]:
    mine = frame[frame["mode"] == mode]
    return {r["criterion_id"]: r for r in mine.to_dict("records")}


def test_a_screen_without_groups_is_framed_as_before() -> None:
    out = frames({}, {"a": 2, "b": 0, "c": 2})
    values = out["rule_screen_values"]
    assert set(out) == {"rule_screen", "rule_screen_values"}
    assert not (values["mode"] == "group").any()
    assert values["group_id"].isna().all()
    assert out["rule_screen"].iloc[0]["failed"] == "b"


def test_a_group_is_a_row_and_its_members_name_it() -> None:
    out = frames({"g": {"any": ["a", "b"]}}, {"a": 0, "b": 2, "c": 2})
    values = out["rule_screen_values"]
    group = rows(values, "group")["g"]
    assert (group["field"], group["outcome"], group["value_str"]) == ("any", "PASS", "b")
    members = rows(values, "hard")
    assert (members["a"]["group_id"], members["b"]["group_id"]) == ("g", "g")
    assert pd.isna(members["c"]["group_id"])
    assert members["a"]["outcome"] == "FAIL"  # the member's own result stays visible


def test_a_failing_group_is_listed_as_the_gate_not_its_members() -> None:
    screen = frames({"g": {"any": ["a", "b"]}}, {"a": 0, "b": 0, "c": 0}).pop("rule_screen")
    row = screen.iloc[0]
    assert row["failed"] == "g,c"
    assert row["near_missed"] == "" and row["missing"] == ""


def test_nested_groups_name_their_parent_and_none_stores_the_original_members() -> None:
    out = frames(
        {"top": {"any": ["inner", "c"]}, "inner": {"none": ["a"]}},
        {"a": 2, "b": 2, "c": 0},
    )
    values = out["rule_screen_values"]
    groups = rows(values, "group")
    assert pd.isna(groups["top"]["group_id"]) and groups["inner"]["group_id"] == "top"
    assert groups["inner"]["field"] == "none"
    members = rows(values, "hard")
    assert members["a"]["group_id"] == "inner"
    assert members["a"]["outcome"] == "PASS"  # the criterion as written, not its negation
    assert members["a"]["value_num"] == 2.0
