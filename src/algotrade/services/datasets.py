"""The golden dataset catalogue as stored by the ingestion ``golden`` job."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from algotrade.core.model.errors import MissingDataError
from algotrade.core.model.instruments import Instrument
from algotrade.core.views.series import PriceSeries, align
from algotrade.data import StoreReader
from algotrade.data.prices import bars, frame_to_series
from algotrade.data.reference import instrument_terms, read_snapshot, snapshot

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
    frame, _ = read_snapshot(reader, CATALOG, None, HINT)  # the latest catalogue
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
    catalog = snapshot(reader, CATALOG)
    assert catalog is not None  # list_datasets raised otherwise
    first = catalog.snapshot_date
    instruments = sorted({i for n in wanted for i in catalogue[n].instruments})
    series = frame_to_series(bars(reader, "1d", first, FAR_FUTURE, instruments))
    terms = instrument_terms(reader, first, instruments)
    return {
        n: (
            align({i: series[i] for i in catalogue[n].instruments}),
            {i: terms[i] for i in catalogue[n].instruments},
        )
        for n in wanted
    }


def load_dataset(
    reader: StoreReader, name: str
) -> tuple[dict[str, PriceSeries], dict[str, Instrument]]:
    return load_datasets(reader, [name])[name]
