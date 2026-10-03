"""The golden dataset catalogue as stored by the ingestion ``golden`` job."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from algotrade.core.errors import MissingDataError
from algotrade.core.instruments import Instrument
from algotrade.core.series import PriceSeries, align
from algotrade.services.market_data import frame_to_series
from algotrade.storage.readers import StoreReader

CATALOG = "catalog/golden_datasets"
HINT = "make golden-store (algotrade-ingest golden load into the fixture store)"
FAR_FUTURE = date(9999, 12, 31)


@dataclass(frozen=True)
class DatasetInfo:
    name: str
    description: str
    instruments: tuple[str, ...]
    symbols: tuple[str, ...]
    tags: tuple[str, ...]


def list_datasets(reader: StoreReader) -> dict[str, DatasetInfo]:
    snapshot = reader.latest_date(CATALOG)
    if snapshot is None:
        raise MissingDataError(CATALOG, "no golden catalogue in this store", HINT)
    frame = reader.require(CATALOG, snapshot, HINT)
    out: dict[str, DatasetInfo] = {}
    for name, group in frame.groupby("dataset", sort=True):
        rows = group.sort_values("instrument_id")
        out[str(name)] = DatasetInfo(
            name=str(name),
            description=str(rows["description"].iloc[0]),
            instruments=tuple(rows["instrument_id"]),
            symbols=tuple(rows["symbol"]),
            tags=tuple(t for t in str(rows["tags"].iloc[0]).split(",") if t),
        )
    return out


def load_datasets(
    reader: StoreReader, names: Iterable[str] | None = None
) -> dict[str, tuple[dict[str, PriceSeries], dict[str, Instrument]]]:
    """Aligned series and contract terms per dataset, reading the bars only once."""
    catalogue = list_datasets(reader)
    wanted = list(names) if names is not None else list(catalogue)
    unknown = [n for n in wanted if n not in catalogue]
    if unknown:
        raise MissingDataError(
            CATALOG, f"unknown dataset(s) {unknown}; have {sorted(catalogue)}", HINT
        )
    snapshot = reader.latest_date(CATALOG)
    assert snapshot is not None
    instruments = sorted({i for n in wanted for i in catalogue[n].instruments})
    bars = frame_to_series(reader.bars("1d", snapshot, FAR_FUTURE, instruments))
    terms = reader.instrument_terms(snapshot, instruments)
    return {
        n: (
            align({i: bars[i] for i in catalogue[n].instruments}),
            {i: terms[i] for i in catalogue[n].instruments},
        )
        for n in wanted
    }


def load_dataset(
    reader: StoreReader, name: str
) -> tuple[dict[str, PriceSeries], dict[str, Instrument]]:
    return load_datasets(reader, [name])[name]
