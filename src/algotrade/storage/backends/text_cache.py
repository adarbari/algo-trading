"""The text cache backends (ADR 0041, amended 2026-10-06): a text answer kept by key, so the
first click of a session pays the model and the rest read the file. ``LocalTextCache`` writes
one JSON file per key under its root (``var/cache/explanations/``, next to the data root), each
written to a temp file and renamed into place so a reader never sees half a file;
``MemoryTextCache`` is the same in a dict. A derived cache: losing a file costs one model call,
and an unreadable file is a miss, never an error. Keys are file names (no ``/``)."""

import json
import threading
from pathlib import Path

from algotrade.storage.backends.local_index import atomic_write, safe


class LocalTextCache:
    def __init__(self, root: Path) -> None:
        self.root = root

    @classmethod
    def beside(cls, data_root: Path) -> "LocalTextCache":
        """The cache next to the data root: ``<data root>/../cache/explanations``."""
        return cls(data_root.parent / "cache" / "explanations")

    def _path(self, key: str) -> Path:
        return self.root / f"{safe(key)}.json"

    def get(self, key: str) -> str | None:
        try:
            text = json.loads(self._path(key).read_text()).get("text")
        except (OSError, ValueError, AttributeError):
            return None
        return text if isinstance(text, str) else None

    def put(self, key: str, text: str) -> None:
        atomic_write(self._path(key), json.dumps({"text": text}).encode())


class MemoryTextCache:
    def __init__(self) -> None:
        self._items: dict[str, str] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> str | None:
        with self._lock:
            return self._items.get(safe(key))

    def put(self, key: str, text: str) -> None:
        with self._lock:
            self._items[safe(key)] = text
