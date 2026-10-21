"""``MemoryReleaseStore``: a draft's age counts from its last write, as the local store's does."""

from datetime import date

import pyarrow as pa

from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.backends.release.memory import MemoryReleaseStore

S1 = date(2026, 10, 1)


def test_a_write_renews_the_age_of_a_draft() -> None:
    backend = MemoryBackend()
    store = MemoryReleaseStore(backend.tables, draft_ttl_s=1000)
    draft = store.begin(S1, 0, 1)
    key = (draft.release_id, draft.token)
    store.state.drafts[key] = (store.state.drafts[key][0], store.state.drafts[key][1] - 5000)
    store.write(draft, "picks", pa.table({"instrument_id": ["EQ:A"]}))  # a build still going
    store.prune(sessions=1)
    assert key in store.state.drafts
    store.state.drafts[key] = (store.state.drafts[key][0], store.state.drafts[key][1] - 5000)
    store.prune(sessions=1)
    assert key not in store.state.drafts
