"""Fitness tests for the feature store, steps 1-3 (ADR 0023):

- every stored column of every group is a declared ``Feature`` with a description, a unit and
  a null meaning; its stored type is its ``dtype``, on real (golden) output too;
- valid ranges and categories are sane, and golden output stays inside them;
- feature inputs resolve: another feature, or a raw field of a table the group reads; an
  expression feature a group reads is materialised and computed before it; a ``series:<KEY>``
  input is a series of ``config/site/macro.toml`` the group reads (ADR 0048), and a feature
  over a personal-use series is personal itself;
- every expression feature is documented like a stored one, and golden output of both
  (materialised and virtual) has the declared types, ranges and categories;
- a null explained by a status column (ADRs 0042, 0046) names statuses that are ``NullReason``
  values and that the status column declares as categories;
- the generated catalogue (``docs/data/features.md``) is up to date;
- the site field guide (``config/site/field_guide/*.toml``, ADR 0041) names only catalogue fields,
  in its entries, its situations and its prose, with values that fit each field's type,
  categories and range, and its generated page (``docs/data/field-guide.md``) is up to date;
- inputs come only through ``algotrade.data.feature_inputs``: no module under ``features/``
  imports storage or a domain reader, and the framework has no loaders of its own.
"""

import ast
import re
from pathlib import Path

import pandas as pd
import pytest

from algotrade.config.site.field_guide import GuideUse
from algotrade.config.site.settings import MacroSettings, load_field_guide, load_macro
from algotrade.data import StoreReader
from algotrade.data.macro.series import TABLE as MACRO_SERIES
from algotrade.features.catalogue import PATH, render
from algotrade.features.framework.declaration import FeatureGroup, Input
from algotrade.features.framework.feature import (
    SERIES_REF,
    Feature,
    NullReason,
    in_range,
    is_feature_ref,
    is_series_ref,
)
from algotrade.features.framework.graph import dependencies
from algotrade.features.framework.runner import compute_in_memory
from algotrade.features.guide import PATH as GUIDE_PATH
from algotrade.features.guide import render as render_guide
from algotrade.features.registry import GROUPS, feature
from algotrade.features.site import site_features
from algotrade.services.read.instruments.catalogue import feature_infos
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT

SITE = site_features(FileConfigStore(REPO_ROOT / "config"))
MACRO = load_macro(FileConfigStore(REPO_ROOT / "config"))
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
            elif not is_series_ref(ref):
                assert ref.rpartition(".")[0] in reads, f"{f.key}: {ref} is not a table it reads"
    assert not series_input_problems(group, MACRO)


def series_input_problems(group: FeatureGroup, macro: MacroSettings) -> list[str]:
    """Why the group's ``series:<KEY>`` inputs do not resolve (empty: they do)."""
    read = next((i for i in group.inputs if i.table == MACRO_SERIES), None)
    declared = {s.instrument_id for s in macro.series}
    unknown = sorted(set(read.ids) - declared) if read else []
    problems = (
        [f"{group.key}: {MACRO_SERIES} ids {unknown} are not in macro.toml"] if unknown else []
    )
    for f in group.features:
        for ref in filter(is_series_ref, f.inputs):
            key = ref.removeprefix(SERIES_REF)
            if key not in macro.keys:
                problems.append(f"{f.key}: {ref} is not a series of config/site/macro.toml")
                continue
            series = macro.by_key(key)
            if read is None or (read.ids and series.instrument_id not in read.ids):
                problems.append(f"{f.key}: {ref} is not an input ({MACRO_SERIES} ids)")
            if series.licence == "personal" and f.licence != "personal":
                problems.append(f"{f.key}: {ref} is for personal use; so is the feature")
    return problems


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


# ----------------------------------------------------------------------- the field guide

GUIDE = load_field_guide(FileConfigStore(REPO_ROOT / "config"))
CATALOGUE = feature_infos(SITE)  # name -> FeatureInfo, every field of the site catalogue
FIELD_REF = re.compile(r"\b(?:feature|rollup|instrument)\.[A-Za-z0-9_@.]+")
NUMERIC_OPS = {"gt", "gte", "lt", "lte", "between", "eq", "ne"}
CATEGORY_OPS = {"eq", "ne", "in", "not_in"}


def _mentioned(text: str) -> set[str]:
    return {m.rstrip(".,;:)") for m in FIELD_REF.findall(text)}


def test_field_guide_names_catalogue_fields_everywhere() -> None:
    names = set(CATALOGUE)
    for e in GUIDE.fields:
        assert e.name in names, f"field guide: {e.name} is not a catalogue field"
        prose = " ".join([e.reads, *e.caveats, *(u.note for u in e.uses)])
        unknown = _mentioned(prose) - names
        assert not unknown, (
            f"field guide {e.name}: names fields the catalogue lacks: {sorted(unknown)}"
        )
    for s in GUIDE.situations:
        unknown = (set(s.affects) | _mentioned(s.signs + " " + s.do)) - names
        assert not unknown, (
            f"situation {s.name!r}: names fields the catalogue lacks: {sorted(unknown)}"
        )


def _check_numeric(name: str, use: GuideUse, lo: float | None, hi: float | None) -> None:
    values = use.value if use.op == "between" else [use.value]
    if use.op == "between":
        assert isinstance(use.value, list) and len(use.value) == 2, (
            f"{name} {use.intent}: between takes two"
        )
    for v in values:
        assert isinstance(v, int | float) and not isinstance(v, bool), f"{name} {use.intent}: {v!r}"
        assert lo is None or v >= lo, f"{name} {use.intent}: {v} is below the field's range"
        assert hi is None or v <= hi, f"{name} {use.intent}: {v} is above the field's range"


def test_field_guide_values_fit_their_fields() -> None:
    for e in GUIDE.fields:
        info = CATALOGUE[e.name]
        lo, hi = info.range or (None, None)
        for use in e.uses:
            where = f"{e.name} {use.intent!r}"
            if use.op in ("is_null", "not_null"):
                continue
            if info.categories:
                assert use.op in CATEGORY_OPS, f"{where}: {use.op} on a category"
                chosen = use.value if isinstance(use.value, list) else [use.value]
                assert set(chosen) <= set(info.categories), (
                    f"{where}: {chosen} not in {info.categories}"
                )
            elif info.dtype == "bool":
                assert use.op == "eq" and isinstance(use.value, bool), (
                    f"{where}: a flag takes eq true/false"
                )
            else:
                assert use.op in NUMERIC_OPS, f"{where}: {use.op} on a number"
                _check_numeric(e.name, use, lo, hi)
            if isinstance(use.tolerance, dict):
                assert use.op in NUMERIC_OPS, f"{where}: a relative tolerance needs a number"


def test_field_guide_page_is_up_to_date() -> None:
    committed = (REPO_ROOT / GUIDE_PATH).read_text()
    assert committed == render_guide(GUIDE), f"{GUIDE_PATH} is out of date: run `make features-doc`"


def test_series_inputs_are_checked_against_the_macro_registry() -> None:
    def feature(name: str, ref: str, licence: str = "open") -> Feature:
        return Feature(name, "float", "decimal", "d", "n", inputs=(ref,), licence=licence)  # type: ignore[arg-type]

    def group(ids: tuple[str, ...], *features: Feature) -> FeatureGroup:
        reads = (Input(MACRO_SERIES, ids=ids),)
        return FeatureGroup("toy", 1, "toy", reads, features, lambda i, s, p: pd.DataFrame())

    ok = group(("MACRO:T10Y3M",), feature("slope", "series:T10Y3M"))
    assert series_input_problems(ok, MACRO) == []
    assert series_input_problems(group((), feature("vix", "series:VIX", "personal")), MACRO) == []
    problems = series_input_problems(
        group(
            ("MACRO:T10Y3M",),
            feature("nope", "series:NOPE"),
            feature("unread", "series:UNRATE"),
            feature("hy", "series:BAMLH0A0HYM2"),
        ),
        MACRO,
    )
    assert [p.split(":")[0] for p in problems] == [
        "toy.nope@v1",
        "toy.unread@v1",
        "toy.hy@v1",
        "toy.hy@v1",
    ]
    assert (
        series_input_problems(group((), feature("hy", "series:BAMLH0A0HYM2", "personal")), MACRO)
        == []
    )
    typo = group(("MACRO:T10Y3N",), feature("slope", "series:T10Y3M"))
    assert series_input_problems(typo, MACRO)[0] == (
        "toy@v1: macro/series ids ['MACRO:T10Y3N'] are not in macro.toml"
    )
