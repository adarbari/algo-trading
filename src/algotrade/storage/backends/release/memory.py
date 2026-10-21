"""In-memory release store for tests: the rules of ``base.py`` over dictionaries. One process
only; ``state`` can be handed to a second store to share its releases, drafts and CURRENT."""

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from algotrade.storage.backends.release.base import DRAFT_TTL_S, ReleaseStoreBase
from algotrade.storage.backends.release.interfaces import Draft, ReleaseNotFoundError
from algotrade.storage.backends.release.manifest import MAX_RELEASE_BYTES, Manifest
from algotrade.storage.tables.interfaces import TableStore


@dataclass
class MemoryReleaseState:
    releases: dict[str, tuple[Manifest, dict[str, bytes]]] = field(default_factory=dict)
    drafts: dict[tuple[str, str], tuple[dict[str, bytes], float]] = field(default_factory=dict)
    current: tuple[str, str] | None = None


class MemoryReleaseStore(ReleaseStoreBase):
    def __init__(
        self,
        tables: TableStore,
        max_bytes: int = MAX_RELEASE_BYTES,
        draft_ttl_s: float = DRAFT_TTL_S,
        free: Callable[[], int] | None = None,
        state: MemoryReleaseState | None = None,
    ) -> None:
        super().__init__(tables, max_bytes, draft_ttl_s, free)
        self.state = state if state is not None else MemoryReleaseState()

    def _disk_free(self) -> int:
        return 1 << 62  # memory: no volume to fill

    def _draft_open(self, draft: Draft) -> None:
        self.state.drafts[draft.release_id, draft.token] = ({}, time.monotonic())

    def _draft_put(self, draft: Draft, name: str, data: bytes) -> None:
        self.state.drafts[draft.release_id, draft.token][0][name] = data

    def _draft_files(self, draft: Draft) -> dict[str, bytes]:
        return dict(self.state.drafts[draft.release_id, draft.token][0])

    def _draft_delete(self, release: str, token: str) -> None:
        self.state.drafts.pop((release, token), None)

    def _drafts(self) -> list[tuple[str, str, float]]:
        now = time.monotonic()
        return [(r, t, now - made) for (r, t), (_, made) in self.state.drafts.items()]

    def _publish(self, draft: Draft, manifest: Manifest) -> None:
        files = self.state.drafts.pop((draft.release_id, draft.token))[0]
        self.state.releases[draft.release_id] = (manifest, files)

    def _delete_release(self, release: str) -> None:
        self.state.releases.pop(release, None)

    def _sealed(self) -> tuple[dict[str, Manifest], list[str]]:
        return {r: m for r, (m, _) in self.state.releases.items()}, []

    def _manifest(self, release: str) -> Manifest | None:
        held = self.state.releases.get(release)
        return None if held is None else held[0]

    def _loader(self, release: str) -> Callable[[str], bytes]:
        def load(name: str) -> bytes:
            held = self.state.releases.get(release)
            if held is None:
                raise ReleaseNotFoundError(release)
            return held[1][name]

        return load

    def _read_current(self) -> tuple[str, str] | None:
        return self.state.current

    def _write_current(self, release: str, manifest_hash: str) -> None:
        self.state.current = (release, manifest_hash)
