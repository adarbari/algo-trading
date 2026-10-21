"""``TableSpec`` guards (``storage/tables/spec.py``)."""

import pytest

from algotrade.storage.tables.spec import fixed


@pytest.mark.parametrize(
    ("runs", "key"),
    [("snapshot", ("user_id", "config_id")), ("merge", ("instrument_id",))],
)
def test_whole_per_group_needs_a_merge_table_keyed_by_user_and_config(
    runs: str, key: tuple[str, ...]
) -> None:
    with pytest.raises(ValueError, match="whole_per_group"):
        fixed("t/x", "results", ("user_id",), "user_id string!", "config_id string!",
              "instrument_id string!", runs=runs, key=key, whole_per_group=True)  # fmt: skip
