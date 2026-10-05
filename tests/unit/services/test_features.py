"""Expression features on read: a range series, selections on ``feature.<name>`` fields,
``FeatureView`` columns, and the selection catalogue of a config store's features."""

import tomllib
from datetime import UTC, date, datetime

import pytest

from algotrade.config.strategy.schema import Group, Rule, Selection
from algotrade.core.model.errors import ConfigurationError
from algotrade.data import StoreReader
from algotrade.services.configs import field_catalog
from algotrade.services.features import read_expressions, site_features
from algotrade.services.selection import select
from algotrade.services.views import feature_view
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.maintenance.golden import load_golden
from algotrade_sources.framework.registry import fixture_source
from tests.conftest import GOLDEN_DIR, REPO_ROOT
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.rollup_store import write_rows

D1, D2 = date(2020, 3, 2), date(2020, 3, 3)
PS = "rollups/instrument/price_stats@v2"


def _row(iid: str, close: float) -> dict[str, object]:
    return {"instrument_id": iid, "close": close, "high_52w": 100.0, "low_52w": 50.0}


@pytest.fixture(scope="module")
def reader() -> StoreReader:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    load_golden(task_ctx(writer), fixture_source("synthetic", GOLDEN_DIR))
    write_rows(writer, PS, D1, [_row("EQ:BULL", 95.0), _row("EQ:BEAR", 52.0)])
    write_rows(writer, PS, D2, [_row("EQ:BULL", 80.0), _row("EQ:BEAR", 54.0)])
    return StoreReader(backend)


def test_a_series_over_a_range_and_an_instrument_filter(reader: StoreReader) -> None:
    rows = read_expressions(reader, ["near_52w", "pct_from_high_52w"], D1, D2)
    labels = {(r.session_date, r.instrument_id): r.near_52w for r in rows.frame.itertuples()}
    assert labels == {
        (D1, "EQ:BEAR"): "LOW", (D1, "EQ:BULL"): "HIGH",
        (D2, "EQ:BEAR"): "LOW", (D2, "EQ:BULL"): "NONE",
    }  # fmt: skip
    assert rows.missing == ()
    only = read_expressions(reader, ["near_52w"], D1, instruments=["EQ:BULL"])
    assert only.frame["instrument_id"].tolist() == ["EQ:BULL"]
    no_iv = read_expressions(reader, ["iv_hv_spread"], D1)
    assert no_iv.frame["iv_hv_spread"].isna().all()
    assert no_iv.missing == ("rollups/instrument/iv_history@v2",)


def test_narrowed_reads_tell_no_rows_from_no_partition(reader: StoreReader) -> None:
    rowless = read_expressions(reader, ["near_52w"], D1, instruments=["EQ:NONE"])
    assert rowless.missing == ()  # the partition exists: just no row for this instrument
    absent = read_expressions(reader, ["near_52w"], date(2020, 3, 4), instruments=["EQ:BULL"])
    assert absent.missing == (PS,)
    before = read_expressions(
        reader, ["near_52w"], D1, instruments=["EQ:NONE"], as_of=datetime(2000, 1, 1, tzinfo=UTC)
    )
    assert before.missing == (PS,)  # nothing of it was known then


def test_selections_and_feature_views_name_expression_features(reader: StoreReader) -> None:
    near_high = Selection("t", Group("all", (Rule("feature.near_52w", "eq", "HIGH"),)))
    assert select(reader, near_high, D1).instruments == ("EQ:BULL",)
    result = select(reader, near_high, D2)
    assert result.instruments == () and result.missing_tables == ()
    view = feature_view(reader, [PS], D1, ["EQ:BULL", "EQ:CHOP"], expressions=["near_52w"])
    assert view.get("EQ:BULL", "near_52w") == "HIGH" and view.get("EQ:BULL", "close") == 95.0
    assert view.get("EQ:CHOP", "near_52w") is None  # no price_stats row: unknown
    with pytest.raises(KeyError, match="unknown expression feature"):
        read_expressions(reader, ["nope"], D1)


def test_the_selection_catalogue_follows_the_store() -> None:
    doc = {"twice": {"expr": "price_stats.close * 2", "dtype": "float", "unit": "usd_per_share",
                     "description": "d", "null_meaning": "n"}}  # fmt: skip
    site = {
        ("site", "features", p.stem): tomllib.loads(p.read_text())
        for p in (REPO_ROOT / "config" / "site" / "features").glob("*.toml")
    }
    custom = MemoryConfigStore({**site, ("site", "features", "mine"): doc})
    assert field_catalog(custom).fields["feature.twice"] == "float"
    assert "feature.twice" not in field_catalog().fields  # default: the site's config
    assert site_features() is site_features()  # built once
    with pytest.raises(ConfigurationError, match="superseded feature group"):
        field_catalog().check_field("rollup.dividends@v1.div_yield", "x")
