"""``GoldenCsvSource``: the committed golden CSVs exposed through the standard source contract.

A fixture source (``sources.base.FixtureSource``): besides ``fetch`` / ``normalize`` it lists
its datasets, verifies the files against their checksums and regenerates them from the
catalogue. Only the source registry builds it (``registry.fixture_source``).

Request key: ``<dataset>/<SYMBOL>``; the request's ``instrument_id`` (resolved by the golden
task) keys the rows. Payloads are whole price histories, so normalised frames carry a ``ts``
per row and ``session_date`` is ``None``.
"""

from collections.abc import Mapping
from pathlib import Path

from algotrade_ingestion.sources.base import FetchRequest, Normalized
from algotrade_ingestion.sources.synthetic.catalog import build_golden
from algotrade_ingestion.sources.synthetic.files import GoldenDataset, GoldenFiles, parse_csv

BARS_TABLE = "bars/1d"
GOLDEN_DIR = Path("datasets/golden")


class GoldenCsvSource:
    name = "synthetic"
    dataset = "golden_csv"

    def __init__(self, files: GoldenFiles) -> None:
        self.files = files

    def datasets(self) -> Mapping[str, GoldenDataset]:
        return self.files.manifest()

    def verify(self) -> list[str]:
        return self.files.verify()

    def build(self) -> list[str]:
        """Regenerate every golden CSV from the catalogue; returns the dataset names."""
        return build_golden(self.files)

    def fetch(self, request: FetchRequest) -> bytes | None:
        dataset, _, symbol = request.key.partition("/")
        path = self.files.path(dataset, symbol)
        return path.read_bytes() if symbol and path.exists() else None

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        if not request.instrument_id:
            raise ValueError(f"{request.key}: golden bars need the request's instrument_id")
        bars = parse_csv(payload, request.key)
        bars.insert(0, "instrument_id", request.instrument_id)
        return Normalized(session_date=None, tables={BARS_TABLE: bars})


def golden_source(directory: Path | None = None) -> GoldenCsvSource:
    return GoldenCsvSource(GoldenFiles(directory or GOLDEN_DIR))
