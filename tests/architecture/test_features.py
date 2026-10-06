"""Fitness tests for the feature store, steps 1-3 (ADR 0023):

- every stored column of every group is a declared ``Feature`` with a description, a unit and
  a null meaning; its stored type is its ``dtype``, on real (golden) output too;
- valid ranges and categories are sane, and golden output stays inside them;
- feature inputs resolve: another feature, or a raw field of a table the group reads; an
  expression feature a group reads is materialised and computed before it;
- every expression feature is documented like a stored one, and golden output of both
  (materialised and virtual) has the declared types, ranges and categories;
- a null explained by a status column (ADRs 0042, 0046) names statuses that are ``NullReason``
  values and that the status column declares as categories;
- the generated catalogue (``docs/data/features.md``) is up to date;
- inputs come only through ``algotrade.data.feature_inputs``: no module under ``features/``
  imports storage or a domain reader, and the framework has no loaders of its own.
"""

import ast
from pathlib import Path

import pandas as pd
import pytest

from algotrade.data import StoreReader
from algotrade.features.catalogue import PATH, render
from algotrade.features.framework.feature import NullReason, in_range, is_feature_ref
from algotrade.features.framework.graph import dependencies
from algotrade.features.framework.runner import compute_in_memory
from algotrade.features.registry import GROUPS, feature
from algotrade.features.site import site_features
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT

SITE = site_features(FileConfigStore(REPO_ROOT / "config"))
FEATURES = SITE.features  # stored + expression features, by key

FEATURES_SRC = REPO_ROOT / "src" / "algotrade" / "features"
# The pandas dtype each field type is stored from (framework.columns.conform).
STORED = {
    "float": "float64",
    "float32": "float32",
    "int": "int64[pyarrow]",
    "bool": "bool[pyarrow]",
    "str": "string",
    "date": "date32[day][pyarrow]",
}


@pytest.mark.parametrize("key", sorted(GROUPS))
def test_every_column_is_a_documented_feature(key: str) -> None:
    group = GROUPS[key]
    assert list(group.columns) == [f.name for f in group.features]
    for f in group.features:
        assert f.description and f.unit and f.null_meaning, f.key
        assert (f.group, f.version, f.entity) == (key, group.version, "instrument")
        assert feature(f.key) is f and feature(f.field) is f
        assert f.field == f"rollup.{key}.{f.name}"


def test_feature_keys_are_unique_and_complete() -> None:
    stored = sum(len(g.features) for g in GROUPS.values())
    assert len(FEATURES) == stored + len(SITE.expressions)
    for name, e in SITE.expressions.items():
        f = e.feature
        assert (f.key, f.field, f.group) == (f"{name}@v{f.version}", f"feature.{name}", "")
        assert f.kind in ("expression", "label") and SITE.feature(f.field) is f


@pytest.mark.parametrize("key", sorted(GROUPS))
def test_inputs_resolve(key: str) -> None:
    group = GROUPS[key]
    reads = {i.table for i in group.inputs}
    upstream = {*dependencies(group), key}
    for f in group.features:
        for ref in f.inputs:
            if is_feature_ref(ref):
                assert ref in FEATURES, f"{f.key}: unknown feature {ref}"
                source = FEATURES[ref].group or ref  # a materialised expression: its own key
                assert source in upstream, f"{f.key}: {ref} is not an input"
                if not FEATURES[ref].group:
                    assert SITE.expressions[FEATURES[ref].name].materialise, ref
            else:
                assert ref.rpartition(".")[0] in reads, f"{f.key}: {ref} is not a table it reads"


@pytest.mark.parametrize(
    ("key", "lo", "hi"),
    [
        ("price_stats.hv20@v2", 0, 5),
        ("price_stats.hv30@v2", 0, 5),
        ("price_stats.hv20_yz@v2", 0, 5),
        ("div_yield@v1", 0, 1),
        ("iv30.iv30@v1", 0, 5),
        ("iv30.iv30_cboe@v1", 0, 5),
        ("iv_history.iv_rank_252d@v2", 0, 1),
        ("iv_history.iv_percentile_252d@v2", 0, 1),
        ("earnings.days_to_earnings@v1", 0, None),
        ("price_stats.ret_20d@v2", -1, None),
        ("market_cap@v1", 0, None),
        ("pct_from_high_52w@v1", -1, 0),
    ],
)
def test_ranges_are_sane(key: str, lo: float | None, hi: float | None) -> None:
    assert FEATURES[key].valid_range == (lo, hi)


def test_labels_and_units() -> None:
    for f in FEATURES.values():
        if f.categories:
            assert f.kind in ("label", "expression") and f.unit == "category", f.key
        if f.dtype == "date":
            assert f.unit == "date", f.key
        if f.dtype == "bool":
            assert f.unit == "flag", f.key
        if f.unit in ("decimal", "usd", "usd_per_share", "shares", "count", "sessions"):
            assert f.valid_range is not None, f"{f.key}: give a numeric feature a range"


def test_explained_and_illiquid_statuses_are_values_of_their_status_column() -> None:
    reasons = {r.value for r in NullReason}
    for f in FEATURES.values():
        if not f.null_status:
            continue
        status = SITE.feature(f.status_field)
        assert status is not None and status.categories, (
            f"{f.key}: {f.status_field} has no categories"
        )
        assert set(f.explained_statuses) <= reasons, f"{f.key}: explained statuses not NullReason"
        named = {*f.explained_statuses, *f.illiquid_statuses}
        assert named <= set(status.categories), f"{f.key}: {named - set(status.categories)}"


def test_catalogue_is_up_to_date() -> None:
    committed = (REPO_ROOT / PATH).read_text()
    assert committed == render(SITE), f"{PATH} is out of date: run `make features-doc`"
    for f in FEATURES.values():
        assert f"`{f.name}`" in committed


def test_golden_output_has_the_declared_types_and_stays_in_range(
    golden_reader: StoreReader,
) -> None:
    sessions = golden_reader.dates("bars/1d")[-20:]
    computed = 0
    stored: dict[str, pd.DataFrame | None] = {}
    groups = list(SITE.groups.values())
    for key, results in compute_in_memory(golden_reader, groups, sessions).items():
        frames = [r.frame.assign(session_date=r.session) for r in results if r.frame is not None]
        stored[SITE.groups[key].table] = pd.concat(frames) if frames else None
        if not frames:
            continue  # golden data has bars only: chain and earnings groups have no input
        _check(pd.concat(frames), SITE.groups[key].features)
        computed += 1
    assert computed >= 4  # price_stats, dividends, fundamentals, div_yield
    virtual = SITE.evaluate(stored, list(SITE.expressions))
    _check(virtual, [e.feature for e in SITE.expressions.values()])
    assert virtual["liquidity_class"].notna().any() and virtual["near_52w"].notna().any()


def _check(frame: pd.DataFrame, features: object) -> None:
    for f in features:  # type: ignore[attr-defined]
        assert str(frame[f.name].dtype) == STORED[f.dtype], f.key
        values = frame[f.name].dropna()
        if f.valid_range is not None:
            outside = [v for v in values if not in_range(f, float(v))]
            assert not outside, f"{f.key}: {outside[:3]} outside {f.valid_range}"
        if f.categories:
            assert set(values) <= set(f.categories), f.key


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
        elif isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
    return out


def test_features_read_only_through_data_feature_inputs() -> None:
    assert not (FEATURES_SRC / "framework" / "inputs.py").exists()
    allowed = {"algotrade.data", "algotrade.data.feature_inputs"}
    for path in FEATURES_SRC.rglob("*.py"):
        for module in _imports(path):
            assert not module.startswith("algotrade.storage"), f"{path.name} imports {module}"
            if module.startswith("algotrade.data"):
                assert module in allowed, f"{path.name}: ask data.feature_inputs, not {module}"
