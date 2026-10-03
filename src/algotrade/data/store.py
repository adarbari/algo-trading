"""On-disk dataset layout and integrity checks.

Layout::

    <root>/manifest.json   # {"datasets": {name: {description, tags, files: {SYM: sha256}}}}
    <root>/<dataset>/<SYMBOL>.csv
"""

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from algotrade.core.errors import ConfigurationError, DataValidationError
from algotrade.core.series import PriceSeries
from algotrade.data.alignment import align
from algotrade.data.frames import frame_to_series, series_to_frame
from algotrade.data.validation import validate_ohlcv

MANIFEST = "manifest.json"


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class DatasetInfo:
    name: str
    description: str
    symbols: tuple[str, ...]
    checksums: dict[str, str] = field(default_factory=dict)
    tags: tuple[str, ...] = ()


class DatasetStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    # ------------------------------------------------------------------ reading
    def manifest(self) -> dict[str, DatasetInfo]:
        path = self.root / MANIFEST
        if not path.exists():
            raise ConfigurationError(f"No dataset manifest at {path}")
        raw: dict[str, Any] = json.loads(path.read_text())
        return {
            name: DatasetInfo(
                name=name,
                description=entry["description"],
                symbols=tuple(entry["files"]),
                checksums=dict(entry["files"]),
                tags=tuple(entry.get("tags", [])),
            )
            for name, entry in sorted(raw["datasets"].items())
        }

    def names(self) -> list[str]:
        return list(self.manifest())

    def load(self, name: str) -> dict[str, PriceSeries]:
        """Load, validate and align every symbol in a dataset."""
        info = self._info(name)
        series: dict[str, PriceSeries] = {}
        for symbol in info.symbols:
            path = self.root / name / f"{symbol}.csv"
            frame = pd.read_csv(path)
            validate_ohlcv(frame, source=str(path))
            series[symbol] = frame_to_series(symbol, frame)
        return align(series)

    def verify(self) -> list[str]:
        """Return a list of integrity problems (empty means all checksums match)."""
        problems: list[str] = []
        for info in self.manifest().values():
            for symbol, expected in info.checksums.items():
                path = self.root / info.name / f"{symbol}.csv"
                if not path.exists():
                    problems.append(f"{path}: missing")
                elif sha256_of(path) != expected:
                    problems.append(f"{path}: checksum mismatch")
        return problems

    # ------------------------------------------------------------------ writing
    def write(
        self, name: str, description: str, series: dict[str, PriceSeries], tags: tuple[str, ...]
    ) -> None:
        directory = self.root / name
        directory.mkdir(parents=True, exist_ok=True)
        files: dict[str, str] = {}
        for symbol, s in sorted(series.items()):
            frame = series_to_frame(s)
            validate_ohlcv(frame, source=f"{name}/{symbol}")
            path = directory / f"{symbol}.csv"
            frame.to_csv(path, index=False, float_format="%.6f", date_format="%Y-%m-%dT%H:%M:%SZ")
            files[symbol] = sha256_of(path)
        self._update_manifest(
            name, {"description": description, "tags": list(tags), "files": files}
        )

    def _update_manifest(self, name: str, entry: dict[str, Any]) -> None:
        path = self.root / MANIFEST
        raw: dict[str, Any] = json.loads(path.read_text()) if path.exists() else {"datasets": {}}
        raw["datasets"][name] = entry
        raw["datasets"] = dict(sorted(raw["datasets"].items()))
        path.write_text(json.dumps(raw, indent=2) + "\n")

    def _info(self, name: str) -> DatasetInfo:
        manifest = self.manifest()
        if name not in manifest:
            raise DataValidationError(str(self.root), [f"unknown dataset {name!r}"])
        return manifest[name]
